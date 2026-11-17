#!/bin/sh
# Entity: Rose. Entity: Rose. Open Google’s YouTube sign-in in the private display browser. Noob signs in directly; never ask for or type passwords in chat. The browser keeps the session across launches. This does not create the Data API search key.
ROSE_CHAT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/../chatbot" && pwd)" || exit 1
case "${1:-}" in --help|-h) exec /usr/bin/python3 "$ROSE_CHAT_DIR/wrapper_help.py" "$0" ;; esac
exec "$ROSE_CHAT_DIR/.venv/bin/python" "$ROSE_CHAT_DIR/tool_dispatch.py" rose_youtube_login
