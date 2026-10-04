#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
build_dir=$(mktemp -d /tmp/noob-channel-calls.XXXXXX)
c++ -std=c++17 -Wall -Wextra -Wno-sign-compare -Wno-missing-field-initializers \
  -Wno-misleading-indentation -I"$root/tests/host" -I"$root/src" \
  "$root/tests/channel_calls.cpp" "$root/src/syscalls/noob_native_registry.cpp" \
  "$root/src/services/SequenceService.cpp" \
  "$root/src/core/noob_sampling_thread.cpp" "$root/src/core/noob_thread_program.cpp" \
  -o "$build_dir/channel-calls"
"$build_dir/channel-calls"
