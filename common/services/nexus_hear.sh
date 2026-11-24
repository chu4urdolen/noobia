#!/usr/bin/env bash
# nexus_hear.sh - AST sound classes + Whisper speech-to-text on CPU (:5052, LAN for Lynx)
set -euo pipefail
export NOOBIA="${NOOBIA:-/noobia}"
export HF_HOME="$NOOBIA/common/runtime/models/hf"
export HF_HUB_OFFLINE=1          # weights are pre-fetched by install.sh vision
cd "$NOOBIA/common/autonomy/services/hear"
exec "$NOOBIA/common/runtime/vision-venv/bin/python" service.py --port 5052 --bind 0.0.0.0
