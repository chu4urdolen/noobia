#!/usr/bin/env bash
# nexus_detect.sh — Nexus Object Detection Service (:5050)
set -euo pipefail

export NOOBIA="${NOOBIA:-/noobia}"
cd "$NOOBIA/common/autonomy/services/detect"

exec "$NOOBIA/common/runtime/forge-venv/bin/python" "$NOOBIA/common/autonomy/services/detect/service.py"
