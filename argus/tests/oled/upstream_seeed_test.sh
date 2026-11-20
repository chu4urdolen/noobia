#!/bin/bash
# Run Seeed Studio's SH1107G example directly from its upstream repository.
# Nothing from the example is copied, translated, or patched by this test.

set -eu

UPSTREAM_URL="https://github.com/Seeed-Studio/grove.py.git"
CHECKOUT="${SEEED_GROVE_CHECKOUT:-/tmp/seeed-grove-py}"

cleanup() {
    sudo systemctl start argononed.service 2>/dev/null || true
}

if [ ! -d "$CHECKOUT/.git" ]; then
    git clone --depth 1 "$UPSTREAM_URL" "$CHECKOUT"
fi

echo "Upstream commit: $(git -C "$CHECKOUT" rev-parse HEAD)"

sudo systemctl stop argononed.service
trap cleanup EXIT INT TERM

cd "$CHECKOUT"
PYTHONPATH=. python3 grove/display/sh1107g.py
