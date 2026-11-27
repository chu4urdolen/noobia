#!/bin/sh
set -eu

DIR=$(mktemp -d)
trap 'rm -rf "$DIR"' EXIT

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
. "$SCRIPT_DIR/noob-install.sh"

echo "testing..." > "$DIR/src.txt"
EXPECTED_HASH=$(sha256sum "$DIR/src.txt" | cut -d" " -f1)

# Check hash
noob_check_hash "$DIR/src.txt" "$EXPECTED_HASH"

# Install file with backup
echo "old" > "$DIR/dst.txt"
noob_install_file "$DIR/src.txt" "$DIR/dst.txt" "0644" "$(id -u):$(id -g)" "pre-test"

[ -f "$DIR/dst.txt.pre-test" ]
[ "$(cat "$DIR/dst.txt.pre-test")" = "old" ]
[ "$(cat "$DIR/dst.txt")" = "testing..." ]

# Rollback
noob_rollback "$DIR/dst.txt" "pre-test"
[ "$(cat "$DIR/dst.txt")" = "old" ]

echo "test_noob_install.sh passed!"
