#!/usr/bin/env bash
# nexus_vision.sh - YOLO11x + Florence-2 on CPU for nexus_detect (:5051, localhost)
set -euo pipefail
export NOOBIA="${NOOBIA:-/noobia}"
export HF_HOME="$NOOBIA/common/runtime/models/hf"
export HF_HUB_OFFLINE=1          # weights are pre-fetched by install.sh vision
cd "$NOOBIA/common/autonomy/services/vision"
exec "$NOOBIA/common/runtime/vision-venv/bin/python" service.py --port 5051 --bind 127.0.0.1
