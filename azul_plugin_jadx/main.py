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
_ACCEPTED_MIME_PREFIXES = (
    "application/vnd.android",
    "application/zip",
    "application/java-archive",
    "application/x-dex",
)


class AzulPluginJadx(BinaryPlugin):
    """Decompiles Android APK/DEX files using JADX, extracts user-defined source files, and derives code features from them."""

    VERSION = "2026.04.28"
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
            [jadx_bin, "--output-dir", output_dir, str(file_path_obj)],
            capture_output=True,
            text=True,
            check=False,
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

    def _verify_file_type(self, file_path: str) -> State | None:
        """Verify the file is an APK or DEX via libmagic. Returns None if valid, else State."""
        try:
            mime = magic.from_file(file_path, mime=True)
        except Exception:  # noqa: BLE001
            return State(State.Label.OPT_OUT, message="Could not determine file type.")

        if not any(mime.startswith(p) for p in _ACCEPTED_MIME_PREFIXES):
            return State(State.Label.OPT_OUT, message="Not a valid APK/DEX file.")

        return None

    def _decompile_and_extract_sources(
        self, file_path: str, temp_dir: str
    ) -> tuple[dict, source_extractor.SourceExtractor] | State:
        """Run JADX and extract user source files. Returns (java_src_files, extractor) or State on error."""
        try:
            output_dir = self._run_jadx_decompile(file_path, temp_dir)
        except (RuntimeError, FileNotFoundError) as e:
            return self.is_malformed(f"JADX failed: {e}")

        try:
            extractor = source_extractor.SourceExtractor(output_dir)
            java_src_files = extractor.get_user_source_files()
        except source_extractor.ExtractorError as e:
            return State(State.Label.COMPLETED_EMPTY, message=f"Source file extraction failed: {e}")

        return java_src_files, extractor

    def _upload_source_files(self, java_src_files: dict, extractor: source_extractor.SourceExtractor) -> None:
        """Combine and upload source files as a single artifact."""
        if not java_src_files:
            return

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f_java_src_files_combined:
            combined_src_filepath = f_java_src_files_combined.name
            extractor.combine_src_files(java_src_files, f_java_src_files_combined)

        try:
            with open(combined_src_filepath, "rb") as f:
                file_count = sum(len(files) for files in java_src_files.values())
                self.logger.info(f"Adding decompiled Java source file with {file_count} user-code files combined.")
                self.add_data_file(DataLabel.DECOMPILED_JAVA, {}, f)
        finally:
            pathlib.Path(combined_src_filepath).unlink()

    def _extract_and_add_features(self, java_src_files: dict) -> None:
        """Extract code features from source files and add them as features."""
        for _, files in java_src_files.items():
            if not files:
                continue
            try:
                features = java_analyser.analyse_files(files)
                for feat_key, feat_values in features.items():
                    if feat_values:
                        self.add_feature_values(feat_key, feat_values)
                self.logger.info(f"Successfully analysed {len(files)} source files.")
            except Exception:  # noqa: BLE001
                self.logger.warning("Failed to analyse Java source files.")

    def execute(self, job: Job):
        """Run the plugin."""
        file_path = job.get_data().get_filepath()

        # Pre-check: verify the file is an APK or DEX via libmagic.
        file_type_error = self._verify_file_type(file_path)
        if file_type_error:
            return file_type_error

        with tempfile.TemporaryDirectory() as temp_dir:
            # --- Run JADX and extract sources ---
            result = self._decompile_and_extract_sources(file_path, temp_dir)
            if isinstance(result, State):
                return result
            java_src_files, extractor = result

            # --- Combine and upload source files ---
            self._upload_source_files(java_src_files, extractor)

            # --- Extract features from source files ---
            self._extract_and_add_features(java_src_files)


def main():
    """Entry point for the azul-plugin-jadx CLI."""
    cmdline_run(plugin=AzulPluginJadx)
