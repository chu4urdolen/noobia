#!/bin/sh
# Entity: Rose. Entity: Rose. Search YouTube using the official Data API. Returns video IDs, titles, channels and links. Requires a YouTube Data API key saved in Settings; browser login is separate.
ROSE_CHAT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/../chatbot" && pwd)" || exit 1
case "${1:-}" in --help|-h) exec /usr/bin/python3 "$ROSE_CHAT_DIR/wrapper_help.py" "$0" ;; esac
exec "$ROSE_CHAT_DIR/.venv/bin/python" "$ROSE_CHAT_DIR/tool_dispatch.py" rose_youtube_search
