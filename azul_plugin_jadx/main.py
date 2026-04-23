"""Decompiles Android APK/DEX files using JADX."""

import os
import pathlib
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

from azul_plugin_jadx.apk_processor import java_analyser, source_extractor

# Accepted MIME types for the libmagic pre-check.
# APKs are zip files so libmagic often reports application/zip instead of
# application/vnd.android. JAR files (application/java-archive) are valid
# JADX inputs when they contain Android bytecode.
_ACCEPTED_MIME_PREFIXES = ("application/vnd.android", "application/zip", "application/java-archive")
_DEX_MIME = "application/x-dex"


class AzulPluginJadx(BinaryPlugin):
    """Decompiles Android APK/DEX files using JADX."""

    VERSION = "2026.04.23"
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

        file_path_obj = pathlib.Path(file_path)
        if not file_path_obj.exists():
            raise FileNotFoundError(f"Could not find the file to run JADX on: '{file_path}'")

        result = subprocess.run(  # noqa: S603
            [jadx_bin, "--output-dir", output_dir, "--deobf", str(file_path_obj)],
            capture_output=True,
            text=True,
            env={
                "JADX_CACHE_DIR": tempfile.gettempdir(),
                "JADX_CONFIG_DIR": tempfile.gettempdir(),
                **os.environ,
            },  # Set HOME to temp to avoid read-only filesystem issues
        )

        if result.returncode != 0 and result.returncode not in (1, 3):
            self.logger.error(f"JADX failed with return code {result.returncode}. Stderr: {result.stderr}")
            raise RuntimeError(result.stderr)

        sources_dir = pathlib.Path(output_dir) / "sources"
        if not sources_dir.is_dir():
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
            print(temp_dir)
            # --- Run JADX ---
            try:
                output_dir = self._run_jadx_decompile(file_path, temp_dir)
            except (RuntimeError, FileNotFoundError) as e:
                return self.is_malformed(f"JADX failed: {e}")

            # --- Locate user source files ---
            try:
                extractor = source_extractor.SourceExtractor(output_dir)
                java_src_files = extractor.get_user_source_files()
            except source_extractor.ExtractorError as e:
                self.logger.warning(f"Source file extraction failed: {e}")
                java_src_files = {}

            # --- Combine and upload source files ---
            if java_src_files:
                with tempfile.NamedTemporaryFile(mode="w", delete=False) as f_java_src_files_combined:
                    combined_src_filepath = f_java_src_files_combined.name
                    extractor.combine_src_files(java_src_files, f_java_src_files_combined)

                with open(combined_src_filepath, "rb") as f:
                    self.logger.info(
                        f"Adding decompiled Java source file with {sum(len(files) for files in java_src_files.values())} user-code files combined."
                    )
                    self.add_data_file(DataLabel.DECOMPILED_JAVA, {}, f)
                    # with open("test_output.log", "wb") as f_out:
                    #     f_out.write(f.read())

                pathlib.Path(combined_src_filepath).unlink()

            # --- Extract features from source files ---
            for _, files in java_src_files.items():
                if files:
                    try:
                        features = java_analyser.analyse_files(files)
                        for feat_key, feat_values in features.items():
                            if feat_values:
                                self.add_feature_values(feat_key, feat_values)
                        self.logger.info(f"Successfully analysed {len(files)} source files.")
                    except Exception:  # noqa: BLE001
                        self.logger.warning("Failed to analyse Java source files.")


def main():
    """Entry point for the azul-plugin-jadx CLI."""
    cmdline_run(plugin=AzulPluginJadx)
