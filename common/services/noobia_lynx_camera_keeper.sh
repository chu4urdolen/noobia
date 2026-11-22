#!/usr/bin/env bash
# noobia_lynx_camera_keeper.sh - prepare Lynx's camera after every Lynx boot
# (lynx/tools/camera/lynx_camera_keeper.py; boot-loop safe, see its docstring).
set -euo pipefail
export NOOBIA="${NOOBIA:-/noobia}"
cd "$NOOBIA/lynx/tools"
exec /usr/bin/python3 "$NOOBIA/lynx/tools/camera/lynx_camera_keeper.py" --every 30
