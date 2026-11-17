#!/bin/sh
# Entity: Rose. Play a YouTube video immediately on the HDMI screen with autoplay enabled. Replaces the current video; there is no queue. Confirms that this video is playing, or returns a startup error within 20 seconds. Does not wait for the video to finish; continue the conversation and other tools.
ROSE_CHAT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/../chatbot" && pwd)" || exit 1
case "${1:-}" in --help|-h) exec /usr/bin/python3 "$ROSE_CHAT_DIR/wrapper_help.py" "$0" ;; esac
exec "$ROSE_CHAT_DIR/.venv/bin/python" "$ROSE_CHAT_DIR/tool_dispatch.py" rose_youtube_play
