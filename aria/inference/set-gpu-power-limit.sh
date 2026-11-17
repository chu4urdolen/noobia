#!/bin/sh
# Reapply the attended RTX 5090 trial limit before local inference starts.
set -eu
attempt=0
while [ "$attempt" -lt 30 ]; do
    if /usr/bin/nvidia-smi -L >/dev/null 2>&1; then
        /usr/bin/nvidia-smi -pl 600
        exit 0
    fi
    attempt=$((attempt + 1))
    sleep 1
done
echo 'RTX 5090 unavailable; power limit was not set' >&2
exit 1
