"""Shared JADX install path and version constants.

``hatch_build.py`` is a hatchling build hook that runs before the package is installed and
cannot reliably import from this module at build time, so it duplicates these values locally.
Any change here **must** be mirrored in ``hatch_build.py``.
"""

import os

JADX_VERSION = "1.5.5"
JADX_VERSION_SHA256 = "38a5766d3c8170c41566b4b13ea0ede2430e3008421af4927235c2880234d51a"
JADX_DOWNLOAD_URL = f"https://github.com/skylot/jadx/releases/download/v{JADX_VERSION}/jadx-{JADX_VERSION}.zip"

JADX_BIN_NAME = "jadx"
JADX_SYSTEM_DIR = "/usr/local/lib/jadx"
JADX_USER_DIR = os.path.join(os.path.expanduser("~"), ".local", "lib", "jadx")
JADX_SYSTEM_BIN = os.path.join(JADX_SYSTEM_DIR, "bin", JADX_BIN_NAME)
JADX_USER_BIN = os.path.join(JADX_USER_DIR, "bin", JADX_BIN_NAME)

# Maximum seconds to wait for a jadx subprocess before treating it as a failure.
JADX_TIMEOUT = 300
