#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
build_dir=$(mktemp -d /tmp/noob-mixed-calls.XXXXXX)
c++ -std=c++17 -Wall -Wextra -Wno-sign-compare -Wno-missing-field-initializers \
  -Wno-misleading-indentation -I"$root/tests/host" -I"$root/src" \
  "$root/tests/mixed_calls.cpp" "$root/src/syscalls/noob_native_registry.cpp" \
  "$root/src/commands/noob_command_dispatcher.cpp" "$root/src/vm/noob_vm.cpp" \
  "$root/src/protocol/noob_protocol.cpp" "$root/src/core/noob_capability_registry.cpp" \
  -o "$build_dir/mixed-calls"
"$build_dir/mixed-calls"
