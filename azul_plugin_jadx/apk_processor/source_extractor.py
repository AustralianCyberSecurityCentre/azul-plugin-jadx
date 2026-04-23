"""Finds user-authored Java source files in a JADX output directory."""

import pathlib

import pygentree
from defusedxml import ElementTree

_EXCLUDED_FILENAMES = ["R.java", "BuildConfig.java"]
_ANDROID_NS = "http://schemas.android.com/apk/res/android"


class ExtractorError(Exception):
    """Raised when source file extraction fails."""


class SourceExtractor:
    """Extracts user-authored Java source files from JADX output, excluding auto-generated and third-party code."""

    def __init__(self, jadx_output_dir: str):
        self.output_dir: pathlib.Path = pathlib.Path(jadx_output_dir)

        self.source_dir: pathlib.Path = self.output_dir / "sources"
        if not self.source_dir.is_dir():
            raise ExtractorError(f"Sources directory not found in JADX output: {self.source_dir}")

        self.resources_dir: pathlib.Path = self.output_dir / "resources"
        if not self.resources_dir.is_dir():
            raise ExtractorError(f"Resources directory not found in JADX output: {self.resources_dir}")

        self.manifest_path: pathlib.Path = self._find_manifest()
        self._root = ElementTree.parse(self.manifest_path).getroot() if self.manifest_path else None
        self.launcher_activity = self._get_launcher_activity() if self._root else ""
        self.package_name = self._get_package_name() if self._root else ""
        self.app_name = self._get_app_name() if self._root else ""
        self._fqn_to_path_map = self._generate_fqn_to_path_map()

    def _generate_fqn_to_path_map(self) -> dict[str, pathlib.Path]:
        """Generate a mapping of fully qualified names to their corresponding directory paths in the sources directory.

        De-duplicates FQNs: if one FQN is a parent of another, the longer (more specific) FQN is removed.
        """
        result: dict[str, pathlib.Path] = {}
        for fqn in [self.launcher_activity, self.package_name, self.app_name]:
            if fqn:
                directory = self._get_deepest_valid_directory_from_fqn(fqn)
                if directory:
                    result[fqn] = directory

        print(f"FQN to path map before pruning: {result}")

        # De-duplicate: if one FQN is a parent of another, remove the longer (more specific) FQN
        fqns_to_remove: set[str] = set()
        fqn_list: list[str] = list(result.keys())
        for i in range(len(fqn_list)):
            for j in range(i + 1, len(fqn_list)):
                fqn_a = fqn_list[i]
                fqn_b = fqn_list[j]

                path_a = result[fqn_a]
                path_b = result[fqn_b]
                if path_b.is_relative_to(path_a):
                    fqns_to_remove.add(fqn_b)
                elif path_a.is_relative_to(path_b):
                    fqns_to_remove.add(fqn_a)

        for fqn in fqns_to_remove:
            del result[fqn]

        print(f"FQN to path map after pruning: {result}")

        return result

    def _get_deepest_valid_directory_from_fqn(self, fqn: str) -> pathlib.Path | None:
        """Given a fqn name and the sources directory, return the deepest valid directory that corresponds to it."""
        components = fqn.split(".")
        fqn_dir = self.source_dir

        for c in components:
            candidate_dir = fqn_dir / c
            if candidate_dir.is_dir() and candidate_dir != self.source_dir:
                fqn_dir = candidate_dir
                print(fqn_dir)
            else:
                break

        return fqn_dir

    def _find_manifest(self) -> pathlib.Path:
        """Walk resources_dir to find AndroidManifest.xml, returning the shallowest match so split-APK config manifests don't shadow the primary app manifest."""
        if not self.resources_dir.is_dir():
            raise ExtractorError(f"Resources directory not found in JADX output: {self.resources_dir}")

        candidates = []
        for dirpath, _, filenames in self.resources_dir.walk():
            if "AndroidManifest.xml" in filenames:
                candidates.append(pathlib.Path(dirpath) / "AndroidManifest.xml")
        if not candidates:
            raise ExtractorError(f"AndroidManifest.xml not found in resources directory: {self.resources_dir}")
        return min(candidates, key=lambda p: len(p.parts))

    def _get_launcher_activity(self):
        """Extract the launcher activity FQN from the manifest, if specified."""
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
        """Extract the main application FQN from the manifest."""
        return self._root.get("package", "")

    def _get_app_name(self) -> str:
        """Extract the application name FQN from the manifest, if specified."""
        application = self._root.find("application")
        if application is not None:
            return application.get(f"{{{_ANDROID_NS}}}name", "")
        return ""

    def get_user_source_files(self) -> dict[str, list[pathlib.Path]]:
        """Return all user-defined .java files associated with the application.

        Walks the FQN's subtree and collects all .java files except auto-generated ones
        in ``_EXCLUDED_FILENAMES``.
        """
        result = {}
        for fqn, base_dirpath in self._fqn_to_path_map.items():
            for dirpath, _, filenames in base_dirpath.walk():
                for filename in filenames:
                    if filename.endswith(".java") and filename not in _EXCLUDED_FILENAMES:
                        file_path = pathlib.Path(dirpath) / filename
                        result[fqn] = result.get(fqn, []) + [file_path]

        return result

    def combine_src_files(self, java_src_files: dict[str, list[pathlib.Path]], output_file) -> None:
        """Combine multiple .java source files into a single output file, with separators and a directory tree."""
        output_file.write(f"\n// NOTE: {_EXCLUDED_FILENAMES} files and third-party code are excluded from output.\n")

        with open(self.manifest_path, "rb") as f:
            output_file.write(f"\n// Manifest: {self.manifest_path.relative_to(self.resources_dir)}\n")
            output_file.write(f.read().decode(errors="replace"))

        for fqn, _ in java_src_files.items():
            output_file.write(f"\n// Package: {fqn}\n")
            output_file.write(
                f"{pygentree.DirectoryTreeGenerator(str(self._fqn_to_path_map[fqn]), sort_order='ascending').get_tree()}\n\n"
            )

        for _, java_files in java_src_files.items():
            for java_file in java_files:
                with open(java_file, "rb") as f:
                    rel_path = java_file.relative_to(self.source_dir)
                    output_file.write(f"\n// Source file: {rel_path}\n")
                    output_file.write(f.read().decode(errors="replace"))
