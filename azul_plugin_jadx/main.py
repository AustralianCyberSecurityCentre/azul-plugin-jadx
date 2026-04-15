"""Decompiles Android APK/DEX files using JADX."""

import os
import shutil
import subprocess  # nosec B404
import tempfile

import magic
from azul_runner import (
    BinaryPlugin,
    DataLabel,
    Feature,
    FeatureType,
    Job,
    State,
    add_settings,
    cmdline_run,
)
from defusedxml import ElementTree

from azul_plugin_jadx.apk_processor import java_analyser, source_extractor

# Accepted MIME types for the libmagic pre-check.
# APKs are zip files so libmagic often reports application/zip instead of
# application/vnd.android. JAR files (application/java-archive) are valid
# JADX inputs when they contain Android bytecode.
_ACCEPTED_MIME_PREFIXES = ("application/vnd.android", "application/zip", "application/java-archive")
_JADX_TIMEOUT = 300
_DEX_MIME = "application/x-dex"


def _find_manifest(resources_dir: str) -> str | None:
    """Walk resources_dir to find AndroidManifest.xml, returning the shallowest match so split-APK config manifests don't shadow the primary app manifest."""
    if not os.path.isdir(resources_dir):
        return None
    candidates = []
    for dirpath, _, filenames in os.walk(resources_dir):
        if "AndroidManifest.xml" in filenames:
            candidates.append(os.path.join(dirpath, "AndroidManifest.xml"))
    if not candidates:
        return None
    return min(candidates, key=lambda p: p.count(os.sep))


class AzulPluginJadx(BinaryPlugin):
    """Decompiles Android APK/DEX files using JADX."""

    VERSION = "2026.04.15"
    SETTINGS = add_settings(
        filter_max_content_size=(int, 100 * 1024 * 1024),
        filter_data_types={
            "content": [
                "android/apk",
                "android/dex",
                # Some file managers report these with the executable/ prefix
                "executable/android/apk",
                "executable/android/dex",
                # XAPK bundles and many APKs that libmagic/file-managers label as generic zip
                "archive/zip",
            ]
        },
    )
    FEATURES = [
        # --- Code features ---
        Feature(
            "package_class_methods",
            desc="Fully-pathed methods in user-package source: com.example.MyClass::method.",
            type=FeatureType.String,
        ),
        Feature(
            "class_methods",
            desc="Class-level methods in user-package source: MyClass::method.",
            type=FeatureType.String,
        ),
        Feature(
            "package_methods",
            desc="Package-level methods in user-package source: com.example::method.",
            type=FeatureType.String,
        ),
        Feature("classes", desc="All class names found in user-package source.", type=FeatureType.String),
        Feature(
            "package_classes",
            desc="Fully-qualified class names found in user-package source.",
            type=FeatureType.String,
        ),
        Feature("packages", desc="All package levels found in user-package source.", type=FeatureType.String),
        Feature("enums", desc="All enum type names found in user-package source.", type=FeatureType.String),
        Feature("interfaces", desc="All interface type names found in user-package source.", type=FeatureType.String),
    ]

    def _run_jadx_decompile(self, file_path: str, output_dir: str) -> str:
        """Decompile an APK/DEX file with JADX (deobfuscation always enabled) and return output_dir."""
        jadx_bin = shutil.which("jadx")
        if not jadx_bin:
            raise FileNotFoundError("JADX binary not found on PATH.")

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Could not find the file to run JADX on: '{file_path}'")

        try:
            result = subprocess.run(  # noqa: S603
                [jadx_bin, "--output-dir", output_dir, "--deobf", file_path],
                capture_output=True,
                text=True,
                timeout=_JADX_TIMEOUT,
            )
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f"JADX timed out after {_JADX_TIMEOUT} seconds.") from e

        if result.returncode != 0 and result.returncode not in (1, 3):
            self.logger.error(f"JADX failed with return code {result.returncode}. Stderr: {result.stderr}")
            raise RuntimeError(result.stderr)

        sources_dir = os.path.join(output_dir, "sources")
        if not os.path.isdir(sources_dir):
            self.logger.error(f"JADX did not produce a sources directory at: {sources_dir}")
            raise RuntimeError(f"JADX did not produce a sources directory at: {sources_dir}")

        return output_dir

    def execute(self, job: Job):
        """Run the plugin."""
        file_path = job.get_data().get_filepath()

        # Pre-check: verify the file is an APK or DEX via libmagic.
        try:
            mime = magic.from_file(file_path, mime=True)
        except Exception:  # noqa: BLE001
            return State(State.Label.OPT_OUT, message="Could not determine file type.")

        if not any(mime.startswith(p) for p in _ACCEPTED_MIME_PREFIXES) and mime != _DEX_MIME:
            return State(State.Label.OPT_OUT, message="Not a valid APK/DEX file.")

        with tempfile.TemporaryDirectory() as temp_dir:
            # --- Run JADX ---
            try:
                output_dir = self._run_jadx_decompile(file_path, temp_dir)
            except (RuntimeError, FileNotFoundError) as e:
                return self.is_malformed(f"JADX failed: {e}")

            resources_dir = os.path.join(output_dir, "resources")
            sources_dir = os.path.join(output_dir, "sources")

            # --- Parse AndroidManifest.xml ---
            user_packages: list[str] = []
            manifest_path = _find_manifest(resources_dir)
            if manifest_path:
                try:
                    tree = ElementTree.parse(manifest_path)
                    manifest_package = tree.getroot().get("package", "")
                    user_packages = source_extractor.get_user_packages(tree, manifest_package)
                except Exception:  # noqa: BLE001
                    self.logger.warning("Failed to parse AndroidManifest.xml.")
            else:
                self.logger.warning("AndroidManifest.xml not found in JADX output.")

            # TODO: Should we add AndroidManifest.xml as a data file here?

            # --- Add decompiled source files ---
            if user_packages and os.path.isdir(sources_dir):
                java_files = source_extractor.get_user_source_files(sources_dir, user_packages)
                for java_file in java_files:
                    try:
                        with open(java_file, "rb") as f:
                            self.add_data_file(DataLabel.DECOMPILED_JAVA, {}, f)
                    except OSError:
                        self.logger.warning(f"Could not read source file: {java_file}")

                # --- Extract code features ---
                if java_files:
                    try:
                        features = java_analyser.analyse_files(java_files)
                        for feat_key, feat_values in features.items():
                            if feat_values:
                                self.add_feature_values(feat_key, feat_values)
                        self.logger.info(f"Successfully analysed {len(java_files)} source files.")
                    except Exception:  # noqa: BLE001
                        self.logger.warning("Failed to analyse Java source files.")
            else:
                self.logger.warning("No user packages identified from manifest -- skipping source analysis.")


def main():
    """Entry point for the azul-plugin-jadx CLI."""
    cmdline_run(plugin=AzulPluginJadx)
