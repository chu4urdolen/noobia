#!/bin/sh
# Entity: Rose. Execute commands using the C shell launcher.
ROSE_SHELL_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/../shell" && pwd)" || exit 1
case "${1:-}" in --help|-h) exec /usr/bin/python3 "$ROSE_SHELL_DIR/../chatbot/wrapper_help.py" "$0" ;; esac
exec "$ROSE_SHELL_DIR/rose-shell" "$@"
