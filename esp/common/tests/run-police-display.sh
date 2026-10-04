#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
build_dir=$(mktemp -d /tmp/noob-police-display.XXXXXX)
c++ -std=c++17 -Wall -Wextra -Wno-sign-compare -Wno-missing-field-initializers \
  -Wno-misleading-indentation -I"$root/tests/host" -I"$root/src" \
  "$root/tests/police_display.cpp" "$root/src/syscalls/noob_native_registry.cpp" \
  "$root/src/vm/noob_vm.cpp" -o "$build_dir/police-display"
"$build_dir/police-display" "$root/../../iris/programs/vm_police_on_all.hex"
