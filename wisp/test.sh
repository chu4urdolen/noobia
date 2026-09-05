#!/bin/sh
set -eu
port=18089
WISP_PASSWORD=test-password ./wisp-web --host 127.0.0.1 --port "$port" --web-dir . >/tmp/wisp-web-test.log 2>&1 &
pid=$!
trap 'kill "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true' EXIT INT TERM
i=0
while ! wget -qO /dev/null "http://127.0.0.1:$port/"; do i=$((i+1)); [ "$i" -lt 30 ] || exit 1; sleep .1; done
cookie=$(mktemp)
trap 'rm -f "$cookie"; kill "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true' EXIT INT TERM
wget -qO- --save-cookies "$cookie" --keep-session-cookies --header="Content-Type: application/json" --post-data='{"password":"test-password"}' "http://127.0.0.1:$port/api/login" | grep -q '"ok":true'
wget -qO- --load-cookies "$cookie" "http://127.0.0.1:$port/api/cwd" | grep -q '"cwd"'
wget -qO- --load-cookies "$cookie" --header="Content-Type: application/json" --post-data='{"cmd":"printf wisp-test"}' "http://127.0.0.1:$port/api/run" | grep -q '"ok":true'
if wget -qO /dev/null "http://127.0.0.1:$port/api/cwd"; then echo 'unauthorized request unexpectedly succeeded' >&2; exit 1; fi
echo 'wisp-web smoke test: ok'
