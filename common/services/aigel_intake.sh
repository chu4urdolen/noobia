#!/usr/bin/env bash
# aigel_intake.sh — Aigel autonomous intake & web dashboard service (:112)
set -euo pipefail

export NOOBIA="${NOOBIA:-/noobia}"
cd "$NOOBIA/aigel/service"

PRIVATE_DIR="$NOOBIA/aigel/private"
mkdir -p "$PRIVATE_DIR"
chmod 0700 "$PRIVATE_DIR"

CHAT_TOKEN_FILE="$PRIVATE_DIR/chat_token"
if [[ ! -f "$CHAT_TOKEN_FILE" ]]; then
    python3 -c "import secrets; print(secrets.token_hex(24))" > "$CHAT_TOKEN_FILE"
    chmod 0600 "$CHAT_TOKEN_FILE"
fi

CHAT_TOKEN="$(cat "$CHAT_TOKEN_FILE")"
HOSTS_FILE="$PRIVATE_DIR/intake_hosts.json"
STATE_FILE="$PRIVATE_DIR/intake_state.json"

if [[ ! -f "$HOSTS_FILE" ]]; then
    echo "{}" > "$HOSTS_FILE"
    chmod 0600 "$HOSTS_FILE"
fi

exec /usr/bin/python3 "$NOOBIA/aigel/service/aigel_intake.py" \
    --bind 0.0.0.0 \
    --port 112 \
    --hosts "$HOSTS_FILE" \
    --state "$STATE_FILE" \
    --chat-token "$CHAT_TOKEN"
