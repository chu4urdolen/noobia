#!/bin/sh
# Entity: Rose. Read current player mode, video ID, player state, position and errors. State 1 means playing, 2 paused, 3 buffering, 0 ended. No video queue exists.
ROSE_CHAT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/../chatbot" && pwd)" || exit 1
case "${1:-}" in --help|-h) exec /usr/bin/python3 "$ROSE_CHAT_DIR/wrapper_help.py" "$0" ;; esac
exec "$ROSE_CHAT_DIR/.venv/bin/python" "$ROSE_CHAT_DIR/tool_dispatch.py" rose_display_status
