#!/usr/bin/env bash
# Build the Catalyst Kodi repository and install the plugin into the local
# Windows Kodi (WSL -> /mnt/c). Thin wrapper around build.py so the zip/md5
# and addons.xml logic lives in one place.
#
# Usage:
#   ./build.sh              # build + copy addon to this Windows PC's Kodi
#   ./build.sh --no-install # build only, don't touch Kodi
set -euo pipefail

cd "$(dirname "$0")"
exec python3 build.py "$@"
