#!/bin/sh
# Entity: Lolth. Preview or explicitly apply a saved pose. Targets are calibration candidates; servo 8 default is provisional. Execute only after an agreed physical move.
ROSE_CHAT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/../chatbot" && pwd)" || exit 1
case "${1:-}" in --help|-h) exec /usr/bin/python3 "$ROSE_CHAT_DIR/wrapper_help.py" "$0" ;; esac
exec "$ROSE_CHAT_DIR/.venv/bin/python" "$ROSE_CHAT_DIR/tool_dispatch.py" lolth_program
