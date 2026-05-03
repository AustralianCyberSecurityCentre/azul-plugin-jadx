#!/usr/bin/env bash

if [ "$EUID" -ne 0 ]; then
    echo "Must be run as root to install JADX to /opt and create symlink in /usr/local/bin."
    exit 1
fi

set -e

JADX_VERSION="1.5.5"
JADX_VERSION_SHA256="38a5766d3c8170c41566b4b13ea0ede2430e3008421af4927235c2880234d51a"
JADX_DOWNLOAD_URL="https://github.com/skylot/jadx/releases/download/v${JADX_VERSION}/jadx-${JADX_VERSION}.zip"
JADX_INSTALL_DIR="/opt/jadx"

# Create installation directory if it doesn't exist
echo "Downloading JADX version ${JADX_VERSION} from ${JADX_DOWNLOAD_URL}..."
curl -L -o "jadx.zip" "${JADX_DOWNLOAD_URL}"

DOWNLOADED_SHA256=$(sha256sum "jadx.zip" | awk '{print $1}')
if [ "${DOWNLOADED_SHA256}" != "${JADX_VERSION_SHA256}" ]; then
    echo "SHA256 checksum verification failed!"
    echo "Expected: ${JADX_VERSION_SHA256}"
    echo "Got:      ${DOWNLOADED_SHA256}"
    rm -f "jadx.zip"
    exit 1
fi

unzip -o "jadx.zip" -d "$JADX_INSTALL_DIR"

rm -f "jadx.zip"

# Make jadx executable
chmod +x "${JADX_INSTALL_DIR}/bin/jadx"

# Create a symlink to put jadx on PATH
ln -sf "${JADX_INSTALL_DIR}/bin/jadx" /usr/local/bin/jadx

echo "JADX version ${JADX_VERSION} installed successfully to ${JADX_INSTALL_DIR} and symlinked to /usr/local/bin/jadx."
