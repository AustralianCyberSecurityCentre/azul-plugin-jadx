"""Install jadx decompiler at build time."""

# hatch_build.py
import hashlib
import logging
import os
import shutil
import sys
import urllib.request
import zipfile

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

JADX_VERSION = "1.5.5"
# NOTE: Keep the values below in sync with azul_plugin_jadx/_constants.py.
# hatch_build.py runs before the package is installed and cannot import the module.
JADX_VERSION_SHA256 = "38a5766d3c8170c41566b4b13ea0ede2430e3008421af4927235c2880234d51a"
# Preferred system-wide install location (used in Docker / CI).
# Falls back to a user-local directory when not writable (local dev).
_JADX_SYSTEM_DIR = "/usr/local/lib/jadx"
_JADX_USER_DIR = os.path.join(os.path.expanduser("~"), ".local", "lib", "jadx")
JADX_DOWNLOAD_URL = f"https://github.com/skylot/jadx/releases/download/v{JADX_VERSION}/jadx-{JADX_VERSION}.zip"


def _get_install_dir() -> str:
    """Return the directory to install jadx into, preferring the system location."""
    if os.path.isdir(_JADX_SYSTEM_DIR) or os.access(os.path.dirname(_JADX_SYSTEM_DIR), os.W_OK):
        return _JADX_SYSTEM_DIR
    return _JADX_USER_DIR


def _verify_sha256(path: str, expected: str) -> None:
    """Raise ValueError if the SHA-256 of *path* does not match *expected*."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    actual = digest.hexdigest()
    if actual != expected:
        raise ValueError(f"SHA-256 mismatch for {path}: expected {expected}, got {actual}")


class CustomBuildHook(BuildHookInterface):
    """Build hook for running actions at build time."""

    def initialize(self, version, build_data):
        """Download and install jadx."""
        # If jadx is already on PATH, nothing to do.
        if shutil.which("jadx"):
            logging.info("jadx already on PATH, skipping download.")
            return

        install_dir = _get_install_dir()
        jadx_bin = os.path.join(install_dir, "bin", "jadx")
        if os.path.isfile(jadx_bin):
            logging.info(f"jadx already installed at {jadx_bin}, skipping download.")
            return

        zip_path = f"/tmp/jadx-{JADX_VERSION}.zip"  # noqa: S108
        try:
            logging.info(f"Downloading jadx {JADX_VERSION} from {JADX_DOWNLOAD_URL}")
            urllib.request.urlretrieve(JADX_DOWNLOAD_URL, zip_path)  # noqa: S310
            _verify_sha256(zip_path, JADX_VERSION_SHA256)
        except Exception as e:
            logging.error(f"Failed to download jadx: {e}")
            sys.exit(-1)

        try:
            os.makedirs(install_dir, exist_ok=True)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(install_dir)
            os.chmod(jadx_bin, 0o755)  # noqa: S103
            logging.info(f"jadx installed to {install_dir}")
        except Exception as e:
            logging.error(f"Failed to extract jadx: {e}")
            sys.exit(-1)
        finally:
            if os.path.exists(zip_path):
                os.remove(zip_path)
