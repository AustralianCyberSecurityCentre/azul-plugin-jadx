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

from azul_plugin_jadx import jadx
from azul_plugin_jadx.apk_processor import java_analyser, manifest_parser, source_extractor

# MIME types / magic signatures accepted as APK or DEX input.
# NOTE: APKs are zip files and libmagic often reports them as application/zip.
# application/vnd.android covers cases where libmagic correctly identifies the APK.
# application/zip is the fallback for APKs and XAPK bundles that appear as generic zip.
# In production the filter_data_types pre-filter limits which files reach this point.
_APK_MAGIC_PREFIXES = ("application/vnd.android", "application/zip")
_DEX_MIME = "application/x-dex"


def _prepare_jadx_input(file_path: str, temp_dir: str, mime: str) -> str:
    """Return the path jadx should receive as input.

    JADX uses the file extension to recognise XAPK bundles.  When azul-runner
    provides the input as a temp file with no extension, XAPK inputs are not
    identified and the per-APK ``AndroidManifest.xml`` is never decoded.
    Detect the XAPK format by checking for ``manifest.json`` at the zip root
    (the XAPK bundle descriptor) and create a symlink with the correct
    ``.xapk`` extension so jadx handles it properly.
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
    """Walk the JADX resources directory to locate AndroidManifest.xml.

    For XAPK and split-APK inputs the manifest may be nested in a subdirectory
    rather than at the top of the resources tree.  Returns the shallowest match
    so that split-APK config manifests do not shadow the primary app manifest.
    """
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
        # --- Manifest metadata ---
        Feature("package_name", desc="The Android package name from AndroidManifest.xml.", type=FeatureType.String),
        Feature("version_code", desc="The versionCode from AndroidManifest.xml.", type=FeatureType.String),
        Feature("version_name", desc="The versionName from AndroidManifest.xml.", type=FeatureType.String),
        Feature("min_sdk_version", desc="The minSdkVersion from AndroidManifest.xml.", type=FeatureType.String),
        Feature("target_sdk_version", desc="The targetSdkVersion from AndroidManifest.xml.", type=FeatureType.String),
        Feature(
            "compile_sdk_version", desc="The compileSdkVersion from AndroidManifest.xml.", type=FeatureType.String
        ),
        Feature(
            "permissions",
            desc="Android permissions declared in AndroidManifest.xml.",
            type=FeatureType.String,
        ),
        Feature(
            "features_used",
            desc="Hardware/software features declared via <uses-feature> in AndroidManifest.xml.",
            type=FeatureType.String,
        ),
        Feature(
            "activities",
            desc="User-defined Activity class names declared in AndroidManifest.xml.",
            type=FeatureType.String,
        ),
        Feature(
            "services",
            desc="User-defined Service class names declared in AndroidManifest.xml.",
            type=FeatureType.String,
        ),
        Feature(
            "receivers",
            desc="User-defined BroadcastReceiver class names declared in AndroidManifest.xml.",
            type=FeatureType.String,
        ),
        Feature(
            "providers",
            desc="User-defined ContentProvider class names declared in AndroidManifest.xml.",
            type=FeatureType.String,
        ),
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

        is_apk = any(mime.startswith(prefix) for prefix in _APK_MAGIC_PREFIXES)
        is_dex = mime == _DEX_MIME
        if not is_apk and not is_dex:
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
                    manifest = manifest_parser.parse_manifest(manifest_path)
                    package_name = manifest.get("package_name", "")

                    for scalar_key in (
                        "package_name",
                        "version_code",
                        "version_name",
                        "min_sdk_version",
                        "target_sdk_version",
                        "compile_sdk_version",
                    ):
                        value = manifest.get(scalar_key, "")
                        if value:
                            self.add_feature_values(scalar_key, value)

                    for list_key in (
                        "permissions",
                        "features_used",
                        "activities",
                        "services",
                        "receivers",
                        "providers",
                    ):
                        values = manifest.get(list_key, [])
                        if values:
                            self.add_feature_values(list_key, values)
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
