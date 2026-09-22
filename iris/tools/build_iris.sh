#!/usr/bin/env bash
set -euo pipefail
IRIS_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
CONFIG="$IRIS_ROOT/tools/iris-build.conf"
BUILD_DIR=
OPT_JOBS=
OPT_FQBN=
OPT_EXTRA_FLAGS=
while (( $# )); do
  case $1 in
    --config) CONFIG=$2; shift 2 ;;
    --build-dir) BUILD_DIR=$2; shift 2 ;;
    --jobs) OPT_JOBS=$2; shift 2 ;;
    --fqbn) OPT_FQBN=$2; shift 2 ;;
    --extra-flags) OPT_EXTRA_FLAGS=$2; shift 2 ;;
    --help|-h) echo "usage: $0 [--config FILE] [--build-dir DIR] [--jobs N] [--fqbn FQBN] [--extra-flags FLAGS]"; exit 0 ;;
    *) [[ -z $BUILD_DIR ]] && BUILD_DIR=$1 && shift || { echo "unexpected argument: $1" >&2; exit 2; } ;;
  esac
done
[[ ! -r $CONFIG ]] || source "$CONFIG"
LOCAL_CONFIG="$IRIS_ROOT/tools/iris-build.local.conf"
[[ ! -r $LOCAL_CONFIG || $CONFIG == "$LOCAL_CONFIG" ]] || source "$LOCAL_CONFIG"
BUILD_DIR=${BUILD_DIR:-"$IRIS_ROOT/build/iris-default"}
CLI=${IRIS_ARDUINO_CLI:-arduino-cli}
ARDUINO_CONFIG=${IRIS_ARDUINO_CONFIG:-"$IRIS_ROOT/.arduino-cli/arduino-cli.yaml"}
NM=${IRIS_NM:-xtensa-esp-elf-nm}
FQBN=${OPT_FQBN:-${IRIS_FQBN:-'esp32:esp32:esp32s3:FlashSize=16M,PartitionScheme=huge_app,PSRAM=enabled,FlashMode=qio,CDCOnBoot=default,USBMode=hwcdc,UploadSpeed=921600'}}
JOBS=${OPT_JOBS:-${IRIS_BUILD_JOBS:-4}}
EXTRA_FLAGS=${OPT_EXTRA_FLAGS:-${IRIS_BUILD_EXTRA_FLAGS:-'-DNOOB_ENABLE_EXTERNAL_I2C=0 -DNOOB_ENABLE_SH1107=0 -DNOOB_ENABLE_SOFT_I2C_DIAGNOSTICS=0'}}

mkdir -p "$BUILD_DIR"
# A second build must not clean files used by the first.
exec 9>"$IRIS_ROOT/build/.compile.lock"
flock -n 9 || { echo 'Another Iris build is running' >&2; exit 1; }
"$CLI" compile --jobs "$JOBS" \
  --config-file "$ARDUINO_CONFIG" \
  --fqbn "$FQBN" --build-path "$BUILD_DIR" \
  --build-property "compiler.cpp.extra_flags=$EXTRA_FLAGS" \
  "$IRIS_ROOT/sketchbook/iris_noob"
test -s "$BUILD_DIR/iris_noob.ino.elf"
test -s "$BUILD_DIR/iris_noob.ino.bin"
test -s "$BUILD_DIR/iris_noob.ino.partitions.bin"
"$NM" --defined-only -C "$BUILD_DIR/iris_noob.ino.elf" > "$BUILD_DIR/symbols.txt"
if rg -q 'Esp32I2cService::|Esp32SoftI2cDiagnostics::|Esp32Sh1107Service::|u8g2_' "$BUILD_DIR/symbols.txt"; then
  echo 'Unexpected external-I2C/OLED code linked' >&2
  exit 1
fi
rg -q 'MonotonicTimeService::now' "$BUILD_DIR/symbols.txt" || {
  echo 'Common TIME_NOW service is missing' >&2; exit 1;
}
echo "Verified firmware: $BUILD_DIR/iris_noob.ino.bin"
