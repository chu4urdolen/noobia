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
script=$(wget -qO- --load-cookies "$cookie" "http://127.0.0.1:$port/api/connector/download")
printf "%s" "$script" | grep -q "Wisp Connector is running"
token=$(printf "%s" "$script" | sed -n "s/.*\$t='\([^']*\)'.*/\1/p")
[ "${#token}" -eq 64 ]
wget -qO- "http://127.0.0.1:$port/connector/poll?token=$token" | grep -q '"job":false'
wget -qO- --load-cookies "$cookie" --header="Content-Type: application/json" --post-data='{"prompt":"hello connector"}' "http://127.0.0.1:$port/api/codex/run" | grep -q '"ok":true'
job=$(wget -qO- "http://127.0.0.1:$port/connector/poll?token=$token")
printf "%s" "$job" | grep -q '"job":true'
wget -qO- --header="Content-Type: application/json" --post-data="{\"token\":\"$token\",\"id\":\"1\",\"output\":\"connector-ok\"}" "http://127.0.0.1:$port/connector/result" | grep -q '"ok":true'
wget -qO- --load-cookies "$cookie" "http://127.0.0.1:$port/api/codex/result" | grep -q connector-ok
echo 'wisp-web smoke test: ok'
