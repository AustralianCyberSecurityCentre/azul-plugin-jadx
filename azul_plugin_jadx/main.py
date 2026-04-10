"""Decompiles Android APK/DEX files using JADX."""

import os
import tempfile
import zipfile

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

from azul_plugin_jadx import jadx
from azul_plugin_jadx.apk_processor import java_analyser, source_extractor

# APKs are zip files; libmagic often identifies them as application/zip rather than
# application/vnd.android. filter_data_types limits which files reach this point.
_APK_MAGIC_PREFIXES = ("application/vnd.android", "application/zip")
_DEX_MIME = "application/x-dex"


def _prepare_jadx_input(file_path: str, temp_dir: str, mime: str) -> str:
    """Return the path jadx should receive as input.

    JADX needs a .xapk extension to recognise XAPK bundles. If the input is a zip
    containing manifest.json (the XAPK bundle descriptor), create a symlink with
    the correct extension.
    """
    if mime != "application/zip":
        return file_path
    try:
        with zipfile.ZipFile(file_path, "r") as zf:  # noqa: S202
            if "manifest.json" in zf.namelist():
                xapk_path = os.path.join(temp_dir, "input.xapk")
                os.symlink(os.path.abspath(file_path), xapk_path)
                return xapk_path
    except Exception:  # noqa: BLE001,S110
        pass  # noqa: S110
    return file_path


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

    VERSION = "2026.04.01"
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

    def execute(self, job: Job):
        """Run the plugin."""
        file_path = job.get_data().get_filepath()

        # Pre-check: verify the file is an APK or DEX via libmagic.
        try:
            mime = magic.from_file(file_path, mime=True)
        except Exception:  # noqa: BLE001
            return State(State.Label.OPT_OUT, message="Could not determine file type.")

        if not any(mime.startswith(p) for p in _APK_MAGIC_PREFIXES) and mime != _DEX_MIME:
            return State(State.Label.OPT_OUT, message="Not a valid APK/DEX file.")

        with tempfile.TemporaryDirectory() as temp_dir:
            # Resolve the correct input path for jadx (XAPK needs a .xapk extension).
            jadx_input = _prepare_jadx_input(file_path, temp_dir, mime)
            # --- Run JADX ---
            try:
                output_dir = jadx.run_jadx_decompile(jadx_input, temp_dir)
            except jadx.NotApkFileError:
                return self.is_malformed("JADX could not process the file as an APK/DEX.")
            except jadx.MissingOutDirError:
                return self.is_malformed("JADX did not produce a sources directory.")
            except jadx.NoJadxFoundError as e:
                return self.is_malformed(f"JADX binary not found: {e}")
            except (jadx.UnknownJadxError, FileNotFoundError) as e:
                return self.is_malformed(f"JADX failed with unknown error: {e}")

            resources_dir = os.path.join(output_dir, "resources")
            sources_dir = os.path.join(output_dir, "sources")

            # --- Parse AndroidManifest.xml ---
            package_name = ""
            manifest_path = _find_manifest(resources_dir)
            if manifest_path:
                try:
                    tree = ElementTree.parse(manifest_path)
                    package_name = tree.getroot().get("package", "")
                except Exception:  # noqa: BLE001
                    self.logger.warning("Failed to parse AndroidManifest.xml.")
            else:
                self.logger.warning("AndroidManifest.xml not found in JADX output.")

            # --- Add decompiled source files ---
            if package_name and os.path.isdir(sources_dir):
                java_files = source_extractor.get_user_source_files(sources_dir, package_name)
                for java_file in java_files:
                    try:
                        with open(java_file, "rb") as f:
                            self.add_data_file(DataLabel.DECOMPILED_CS, {}, f)
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
                self.logger.warning("No package name or sources directory — skipping source analysis.")


def main():
    """Entry point for the azul-plugin-jadx CLI."""
    cmdline_run(plugin=AzulPluginJadx)
