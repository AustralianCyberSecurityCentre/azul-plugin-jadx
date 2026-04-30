"""Finds user-authored Java source files in a JADX output directory."""

import pathlib
import shutil
import tempfile

import pygentree
from defusedxml import ElementTree

_EXCLUDED_FILENAMES = ["R.java", "BuildConfig.java"]
# Excluded path components for third-party/system libraries.
# When traversing source directories, any path containing these segments will be excluded, unless it is part of a path expected to contain user code.
# Rationale:
#   - androidx: Android Jetpack libraries (official Google Android extensions)
#   - com/google: Google libraries (Firebase, Google Play Services, etc.)
#   - com/bumptech: Glide image loading library
#   - com/airbnb: Airbnb Lottie animations library
#   - com/facebook: Facebook SDK libraries
#   - kotlin/kotlinx: Kotlin standard library and extensions
#   - org/jetbrains: JetBrains libraries (Kotlin, IntelliJ)
#   - dbuild: Build configuration (not user code)
#   - android/support: Legacy Android Support library (pre-Jetpack)
#   - android/arch: Android Architecture Components library
#   - android/databinding: Android Data Binding framework
#   - android/viewbinding: Android View Binding framework
_EXCLUDED_PATH_COMPONENTS = [
    "androidx",
    "com/google",
    "com/bumptech",
    "com/airbnb",
    "com/facebook",
    "kotlin",
    "kotlinx",
    "org/jetbrains",
    "dbuild",
    "android/support",
    "android/arch",
    "android/databinding",
    "android/viewbinding",
]
_ANDROID_NS = "http://schemas.android.com/apk/res/android"


class ExtractorError(Exception):
    """Raised when source file extraction fails."""


class SourceExtractor:
    """Extracts user-authored Java source files from JADX output, excluding auto-generated and third-party code."""

    def __init__(self, jadx_output_dir: str) -> None:
        """Initialize extractor with JADX output directory.

        Validates directory structure, parses AndroidManifest.xml, and builds FQN-to-path mapping.

        Args:
            jadx_output_dir: Path to JADX output directory containing 'sources/' and 'resources/'.

        Raises:
            ExtractorError: If required directories missing, manifest unparseable, or no valid FQNs found.
        """
        self.output_dir: pathlib.Path = pathlib.Path(jadx_output_dir)

        self.source_dir: pathlib.Path = self.output_dir / "sources"
        if not self.source_dir.is_dir():
            raise ExtractorError(f"Sources directory not found in JADX output: {self.source_dir}")

        self.resources_dir: pathlib.Path = self.output_dir / "resources"
        if not self.resources_dir.is_dir():
            raise ExtractorError(f"Resources directory not found in JADX output: {self.resources_dir}")

        self.manifest_path: pathlib.Path = self._find_manifest()
        try:
            self._root = ElementTree.parse(self.manifest_path).getroot() if self.manifest_path else None
        except ElementTree.ParseError as e:
            raise ExtractorError(f"Failed to parse AndroidManifest.xml: {e}") from e

        self.launcher_activity: str = self._get_launcher_activity() if self._root else ""
        self.package_name: str = self._get_package_name() if self._root else ""
        self.app_name: str = self._get_app_name() if self._root else ""

        # Validate that at least one FQN was extracted; otherwise manifest is unusable.
        if self._root and not (self.launcher_activity or self.package_name or self.app_name):
            raise ExtractorError(
                "AndroidManifest.xml found but no usable FQNs extracted (package, launcher activity, or app name)."
            )

        self._fqn_to_path_map: dict[str, pathlib.Path] = self._generate_fqn_to_path_map()

    def _generate_fqn_to_path_map(self) -> dict[str, pathlib.Path]:
        """Generate mapping of fully qualified names (FQNs) to source directory paths.

        Three-step process:
        1. Collect FQNs: launcher activity, package name, app name from manifest.
        2. Resolve to directories: For each FQN, find deepest matching directory in sources/.
        3. Deduplicate: If one FQN's path is parent of another's, remove the child (more specific) FQN.

        Example:
            If launcher_activity="com.example.MainActivity" maps to sources/com/example/
            and package_name="com.example" also maps to sources/com/example/,
            keep only the more general (package_name) mapping.

        Returns:
            Dict mapping FQN string -> Path object for that FQN's directory.
            Empty dict if no valid directories found.
        """
        result: dict[str, pathlib.Path] = {}
        for fqn in [self.launcher_activity, self.package_name, self.app_name]:
            if fqn:
                directory = self._get_deepest_valid_directory_from_fqn(fqn)
                if directory:
                    result[fqn] = directory

        # Deduplicate: if parent_fqn's path is ancestor of child_fqn's path, remove child_fqn.
        # This keeps broader FQN mappings and discards more specific ones.
        fqns_to_remove: set[str] = set()
        fqn_keys: list[str] = list(result.keys())
        for i in range(len(fqn_keys)):
            for j in range(i + 1, len(fqn_keys)):
                parent_fqn = fqn_keys[i]
                child_fqn = fqn_keys[j]

                parent_path = result[parent_fqn]
                child_path = result[child_fqn]
                # Check if one path is relative to (contained within) the other.
                if child_path.is_relative_to(parent_path):
                    fqns_to_remove.add(child_fqn)  # Remove more specific FQN
                elif parent_path.is_relative_to(child_path):
                    fqns_to_remove.add(parent_fqn)  # Remove more specific FQN

        for fqn in fqns_to_remove:
            del result[fqn]

        return result

    def _get_deepest_valid_directory_from_fqn(self, fqn: str) -> pathlib.Path | None:
        """Find deepest valid directory in sources/ that corresponds to an FQN.

        Given FQN "com.example.foo", walks sources/com/example/foo and returns the
        deepest directory that exists. Returns None if no directory found.

        Args:
            fqn: Fully qualified name like "com.example.MainActivity" or "com.example.lib".

        Returns:
            Deepest valid Path in sources/ tree, or None if not found.
        """
        components = fqn.split(".")
        fqn_dir = self.source_dir

        for c in components:
            candidate_dir = fqn_dir / c
            if candidate_dir.is_dir() and candidate_dir != self.source_dir:
                fqn_dir = candidate_dir
            else:
                break

        return fqn_dir

    def _find_manifest(self) -> pathlib.Path:
        """Find AndroidManifest.xml in resources directory.

        Walks resources_dir to find AndroidManifest.xml, returning the shallowest match.
        (Shallowest prevents split-APK config manifests from shadowing the primary app manifest.)

        Returns:
            Path to AndroidManifest.xml file.

        Raises:
            ExtractorError: If no AndroidManifest.xml found in resources/.
        """
        if not self.resources_dir.is_dir():
            raise ExtractorError(f"Resources directory not found in JADX output: {self.resources_dir}")

        candidates = []
        for dirpath, _, filenames in self.resources_dir.walk():
            if "AndroidManifest.xml" in filenames:
                candidates.append(pathlib.Path(dirpath) / "AndroidManifest.xml")
        if not candidates:
            raise ExtractorError(f"AndroidManifest.xml not found in resources directory: {self.resources_dir}")
        return min(candidates, key=lambda p: len(p.parts))

    def _get_launcher_activity(self) -> str:
        """Extract launcher activity FQN from manifest.

        Looks for activity with MAIN action + LAUNCHER category intent-filter.
        Handles Android XML namespaces correctly via XPath.

        Returns:
            Fully qualified activity name (e.g., "com.example.MainActivity"), or empty string if not found.
        """
        name = ""
        # Android XML uses namespaces; we must extract them
        ns = {"android": _ANDROID_NS}
        for activity in self._root.findall(".//activity"):
            for intent_filter in activity.findall("intent-filter"):
                has_main = intent_filter.find("action[@android:name='android.intent.action.MAIN']", ns) is not None
                has_launcher = (
                    intent_filter.find("category[@android:name='android.intent.category.LAUNCHER']", ns) is not None
                )

                if has_main and has_launcher:
                    # Extract the activity class name
                    name = activity.get(f"{{{_ANDROID_NS}}}name")
                    break

        return name

    def _get_package_name(self) -> str:
        """Extract main application package name from manifest.

        Returns:
            Package attribute from <manifest> element (e.g., "com.example.app"), or empty string.
        """
        return self._root.get("package", "")

    def _get_app_name(self) -> str:
        """Extract application component name from manifest.

        Gets android:name attribute from <application> element.

        Returns:
            Application component FQN (e.g., "com.example.MyApplication"), or empty string if not found.
        """
        application = self._root.find("application")
        if application is not None:
            return application.get(f"{{{_ANDROID_NS}}}name", "")
        return ""

    def _should_exclude_directory(self, dirpath: pathlib.Path, base_dirpath: pathlib.Path) -> bool:
        """Check if a directory should be excluded based on excluded path components.

        Marks directory for exclusion if its path contains excluded library patterns
        (androidx, com/google, kotlin, etc.) UNLESS the base path also contains them.

        Args:
            dirpath: Directory path being checked.
            base_dirpath: Base FQN directory; if it contains excluded component, don't exclude subdirs.

        Returns:
            True if directory should be excluded and deleted, False otherwise.
        """
        dirpath_posix = dirpath.as_posix()
        base_dirpath_posix = base_dirpath.as_posix()

        # Exclude if directory contains excluded segments, unless base_dirpath itself contains them
        if any(seg in dirpath_posix for seg in _EXCLUDED_PATH_COMPONENTS):
            return not any(seg in base_dirpath_posix for seg in _EXCLUDED_PATH_COMPONENTS)
        return False

    def _process_source_file(
        self, filename: str, dirpath: pathlib.Path, fqn: str, result: dict[str, list[pathlib.Path]]
    ) -> None:
        """Process a single source file and add to result or delete if excluded.

        Filters out auto-generated files (R.java, BuildConfig.java) and non-.java files.
        Adds valid .java files to result dict under their FQN.

        Args:
            filename: Name of file being examined.
            dirpath: Directory containing the file.
            fqn: Fully qualified name this file belongs to.
            result: Accumulator dict mapping FQN -> list[Path] of .java files.
        """
        if not filename.endswith(".java"):
            return

        file_path = pathlib.Path(dirpath) / filename

        if filename in _EXCLUDED_FILENAMES:
            file_path.unlink(missing_ok=True)
        else:
            result[fqn] = result.get(fqn, []) + [file_path]

    def _process_directory(
        self,
        dirpath: pathlib.Path,
        filenames: list[str],
        fqn: str,
        base_dirpath: pathlib.Path,
        result: dict[str, list[pathlib.Path]],
    ) -> None:
        """Process all files in a directory.

        Checks if directory should be excluded (e.g., third-party library paths).
        If excluded, deletes it and returns early. Otherwise, processes each file.

        Args:
            dirpath: Current directory path.
            filenames: List of filenames in this directory.
            fqn: Fully qualified name for this directory.
            base_dirpath: Base FQN directory (for exclusion filtering context).
            result: Accumulator dict mapping FQN -> list[Path] of .java files.
        """
        if self._should_exclude_directory(dirpath, base_dirpath):
            shutil.rmtree(dirpath, ignore_errors=True)
            return

        for filename in filenames:
            self._process_source_file(filename, dirpath, fqn, result)

    def get_user_source_files(self) -> dict[str, list[pathlib.Path]]:
        """Return all user-defined .java files associated with the application.

        Walks each FQN's directory subtree in sources/, collecting .java files and excluding:
        - Auto-generated files: R.java, BuildConfig.java
        - Third-party libraries: paths matching _EXCLUDED_PATH_COMPONENTS
        - Non-.java files

        Returns:
            Dict mapping FQN string -> sorted list[Path] of user .java files.
            Example: {"com.example": [Path("sources/com/example/MainActivity.java"), ...]}
        """
        result = {}
        for fqn, base_dirpath in self._fqn_to_path_map.items():
            for dirpath, _, filenames in base_dirpath.walk():
                self._process_directory(dirpath, filenames, fqn, base_dirpath, result)

        for fqn in result:
            result[fqn].sort()  # Sort alphabetically so output matches the pygentree output order

        return result

    def combine_src_files(
        self, java_src_files: dict[str, list[pathlib.Path]], output_file: tempfile._TemporaryFileWrapper
    ) -> None:
        """Combine multiple .java source files into a single output file.

        Writes header comments with manifest info, directory trees, and concatenated
        source code. Output is readable and annotated with file paths.

        Args:
            java_src_files: Dict mapping FQN -> list[Path] of .java files.
            output_file: Open file object to write combined output to (should support .write()).
        """
        output_file.write(f"\n// NOTE: {_EXCLUDED_FILENAMES} files and third-party code are excluded from output.\n")

        if self.package_name:
            output_file.write(f"// Application package: {self.package_name}\n")
        if self.launcher_activity:
            output_file.write(f"// Launcher activity: {self.launcher_activity}\n")
        if self.app_name:
            output_file.write(f"// Application name: {self.app_name}\n")

        for fqn, _ in java_src_files.items():
            output_file.write(
                f"\n// {self._fqn_to_path_map[fqn].as_posix().removeprefix(self.source_dir.as_posix() + '/')}\n"
            )
            output_file.write(
                f"{pygentree.DirectoryTreeGenerator(str(self._fqn_to_path_map[fqn]), sort_order='ascending').get_tree()}\n\n"
            )

        for _, java_files in java_src_files.items():
            for java_file in java_files:
                with open(java_file, "rb") as f:
                    rel_path = java_file.relative_to(self.source_dir)
                    output_file.write(f"\n// {rel_path}\n")
                    output_file.write(f.read().decode(errors="replace"))
