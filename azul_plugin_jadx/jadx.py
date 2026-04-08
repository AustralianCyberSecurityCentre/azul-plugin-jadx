"""Runs the subprocess calls to the JADX Android decompiler."""

import os
import shutil
import subprocess  # nosec B404

from azul_plugin_jadx._constants import JADX_BIN_NAME, JADX_SYSTEM_BIN, JADX_TIMEOUT, JADX_USER_BIN


class JadxError(Exception):
    """Base exception for JADX errors."""

    pass


class NotApkFileError(JadxError):
    """Exception raised when JADX cannot process the file as an APK/DEX."""

    pass


class MissingOutDirError(JadxError):
    """Exception raised when JADX was expected to create an output directory but didn't."""

    pass


class NoJadxFoundError(JadxError):
    """Exception raised when the JADX binary cannot be found."""

    pass


class UnknownJadxError(JadxError):
    """Exception raised when JADX fails for an unknown reason."""

    pass


def run_jadx_decompile(file_path: str, output_dir: str, deobfuscate: bool = True) -> str:
    """Decompile an APK/DEX file with JADX and return output_dir."""
    options = ["--output-dir", output_dir]
    if deobfuscate:
        options.append("--deobf")

    _run_jadx_and_process_errors(file_path, options)

    sources_dir = os.path.join(output_dir, "sources")
    if not os.path.isdir(sources_dir):
        raise MissingOutDirError(f"JADX did not produce a sources directory at: {sources_dir}")

    return output_dir


def _run_jadx_and_process_errors(file_path: str, options: list[str]) -> subprocess.CompletedProcess[str]:
    """Run JADX with the given options, raising typed exceptions on failure."""
    bin_abs_path = (
        shutil.which(JADX_BIN_NAME)
        or (JADX_SYSTEM_BIN if os.path.isfile(JADX_SYSTEM_BIN) else None)
        or (JADX_USER_BIN if os.path.isfile(JADX_USER_BIN) else None)
    )
    if not bin_abs_path:
        raise NoJadxFoundError("JADX binary not found. Ensure jadx is installed.")

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Could not find the file to run JADX on: '{file_path}'")

    try:
        result = subprocess.run(  # noqa: S603
            [bin_abs_path, *options, file_path], capture_output=True, text=True, timeout=JADX_TIMEOUT
        )
    except subprocess.TimeoutExpired as exc:
        raise UnknownJadxError(f"JADX timed out after {JADX_TIMEOUT} seconds.") from exc

    if result.returncode != 0:
        stderr = result.stderr
        if "not supported" in stderr.lower() or "input file not found" in stderr.lower():
            raise NotApkFileError(stderr)
        # Exit codes 1 and 3 indicate jadx finished with some decompilation errors but
        # still produced output.  The caller checks whether the sources directory exists
        # to determine whether the run was useful — so only raise here for truly fatal
        # failures where no output at all would have been written.
        if result.returncode not in (1, 3):
            raise UnknownJadxError(stderr)

    return result
