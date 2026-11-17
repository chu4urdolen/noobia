#!/bin/sh
# Entity: Rose. Capture a camera image with IMX500 object detection. Returns the saved image path and detected objects, labels, confidence and boxes. The photo is also shown on HDMI. No arguments. Initial model loading may take several minutes.
ROSE_CHAT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/../chatbot" && pwd)" || exit 1
case "${1:-}" in --help|-h) exec /usr/bin/python3 "$ROSE_CHAT_DIR/wrapper_help.py" "$0" ;; esac
exec "$ROSE_CHAT_DIR/.venv/bin/python" "$ROSE_CHAT_DIR/tool_dispatch.py" rose_camera
