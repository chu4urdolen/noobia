#!/usr/bin/env bash
# Build Noobia's local runtimes in this folder from the pinned recipes beside
# this script. Safe to re-run: each part is rebuilt to the same pinned versions.
#
#   common/runtime/install.sh            # everything
#   common/runtime/install.sh codex      # Dushich's and Aigel's Codex CLI
#   common/runtime/install.sh forge      # forge-db meaning search (fastembed)
#   common/runtime/install.sh web        # Playwright and its Chromium
#
# Needs: node/npm, uv (https://docs.astral.sh/uv/), /usr/bin/python3, network.
set -euo pipefail
NOOBIA="${NOOBIA:-/noobia}"
R="$NOOBIA/common/runtime"
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"

step() { printf '== %s\n' "$*"; }

codex() {
    step "Codex CLI (pinned in codex/package-lock.json)"
    npm ci --prefix "$R/codex" --no-audit --no-fund --loglevel=error
    "$R/codex/node_modules/.bin/codex" --version
}

venv() {  # venv NAME: build NAME-venv from NAME-requirements.txt
    step "$1-venv (pinned in $1-requirements.txt)"
    "$UV" venv --quiet --allow-existing --python /usr/bin/python3 "$R/$1-venv"
    "$UV" pip install --quiet --python "$R/$1-venv/bin/python" -r "$R/$1-requirements.txt"
    "$R/$1-venv/bin/python" -c "import sys; print(sys.prefix)"
}

forge() {
    venv forge
    # The embedding model downloads into models/ on first meaning search.
    mkdir -p "$R/models"
}

detect() {
    step "Object detection model (YOLOv8n ONNX for nexus_detect; AGPL-3.0 Ultralytics)"
    mkdir -p "$R/models"
    # YOLOv8n ONNX export (Ultralytics, AGPL-3.0), pinned by SHA-256:
    local MODEL_URL="https://huggingface.co/s1777/yolo-v8n-onnx/resolve/main/yolov8n.onnx"
    local MODEL_SHA="dd48a79dd7fec8ca25fde4eca742ff7bca23b27e2e903eb23bc1d9f83a459bd2"
    local MODEL_PATH="$R/models/yolov8n.onnx"
    if [ ! -f "$MODEL_PATH" ] || ! echo "$MODEL_SHA  $MODEL_PATH" | sha256sum --check --status 2>/dev/null; then
        step "Downloading $MODEL_PATH..."
        curl -s -L --fail --show-error --max-time 60 -o "$MODEL_PATH.tmp" "$MODEL_URL"
        if ! echo "$MODEL_SHA  $MODEL_PATH.tmp" | sha256sum --check --status; then
            echo "ERROR: Checksum mismatch for $MODEL_PATH.tmp" >&2
            rm -f "$MODEL_PATH.tmp"
            exit 1
        fi
        mv "$MODEL_PATH.tmp" "$MODEL_PATH"
    fi
    echo "yolov8n.onnx verified ($MODEL_SHA)"
}

web() {
    venv web
    step "Chromium for Playwright (into playwright/)"
    PLAYWRIGHT_BROWSERS_PATH="$R/playwright" "$R/web-venv/bin/python" -m playwright install chromium
}

vision() {  # Python 3.12: CPU PyTorch wheels; the 5090 stays reserved for Qwen
    step "vision-venv (pinned in vision-requirements.txt)"
    "$UV" venv --quiet --allow-existing --python 3.12 "$R/vision-venv"
    "$UV" pip install --quiet --python "$R/vision-venv/bin/python" -r "$R/vision-requirements.txt" \
        --index-strategy unsafe-best-match
    step "YOLO11x weights and Florence-2-large (into models/)"
    (cd "$R/models" && "$R/vision-venv/bin/python" -c "from ultralytics import YOLO; YOLO('yolo11x.pt')")
    HF_HOME="$R/models/hf" "$R/vision-venv/bin/python" -c \
        "from huggingface_hub import snapshot_download; snapshot_download('microsoft/Florence-2-large')"
}

case "${1:-all}" in
    codex) codex ;;
    forge) forge ;;
    detect) detect ;;
    web) web ;;
    vision) vision ;;
    all) codex; forge; detect; web; vision ;;
    *) echo "usage: install.sh [all|codex|forge|detect|web|vision]" >&2; exit 2 ;;
esac
step done
