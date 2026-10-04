#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
build_dir=$(mktemp -d /tmp/noob-self-test.XXXXXX)
c++ -std=c++17 -Wall -Wextra -Wno-sign-compare -Wno-missing-field-initializers \
  -I"$root/tests/host" -I"$root/src" "$root/tests/self_test.cpp" \
  "$root/src/core/noob_self_test.cpp" "$root/src/syscalls/noob_native_registry.cpp" \
  -o "$build_dir/self-test"
"$build_dir/self-test"
