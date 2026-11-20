#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
temporary=$(mktemp -d)
cc -O2 -Wall -Wextra -Werror "$root/tests/noob-file-fixture.c" -o "$temporary/fixture"
mkdir "$temporary/esp" "$temporary/img" "$temporary/vm" "$temporary/audio"
"$temporary/fixture" >"$temporary/port" &
fixture_pid=$!
trap 'kill "$fixture_pid" 2>/dev/null || true' EXIT
for (( i=0; i<50; ++i )); do
  [[ -s $temporary/port ]] && break
  sleep 0.02
done
export NOOB_FILES_CONFIG=/dev/null IRIS_USB_HOST=127.0.0.1
export IRIS_USB_PORT=$(<"$temporary/port")
export NOOB_ESP_DIR=$temporary/esp NOOB_IMG_DIR=$temporary/img
export NOOB_VM_DIR=$temporary/vm NOOB_AUDIO_DIR=$temporary/audio
"$temporary/fixture" --emit >"$temporary/expected"
for mapping in 'jpg img' 'WAV audio' 'nvm vm' 'txt esp'; do
  read -r extension directory <<<"$mapping"
  bash "$root/tools/noob-files" fetch "/test/fixture.$extension"
  cmp "$temporary/expected" "$temporary/$directory/fixture.$extension"
done
if bash "$root/tools/noob-files" fetch /test/fixture.jpg; then exit 1; fi
if bash "$root/tools/noob-files" fetch /test/../bad.jpg; then exit 1; fi
if bash "$root/tools/noob-files" play ../bad.wav; then exit 1; fi
echo 'routing, multi-chunk binary integrity, no-overwrite, and path checks passed'
