# Native interface cleanup — 2026-10-04

Iris is the ESP32 plus Neo. ESP native functions are registered by `iris.cpp`;
reusable services live in `esp/common/src/services`. Neo now exposes a native
registry with `CALL NAME [numbers]` and `CALL_MIXED NAME [numbers] "ASCII"`.
Unused ASCII is `""`. Legacy Neo wire calls remain for installed ESP images.
Neo's registry is a Linux adapter, not another VM or an Arduino class hierarchy.

## ESP source changes

- CAMERA_VIDEO removed from registration. Camera sequence steps save JPEGs;
  Neo must assemble them to make a video file. A 10 ms requested period is not
  a guarantee of 100 fps: capture and SD writes take time.
- CAPTURE_LIST, CAPTURE_READ_CHUNK and CAPTURE_DELETE removed from registration.
  Use generic SD_LIST, SD_READ and SD_DELETE. Old numeric IDs are not reassigned.
- RSSI_ON/OFF and their separate background runner removed from registration.
  CLI rssi-on/off now use RSSI_THREAD_START/STOP. The common sampling thread
  calls RSSI_SNAPSHOT, refreshes scans and saves rssi_*.csv on SD.
- WIFI_RSSI returns a structured record: value, time_ms, index, channel.
  It reads cached WIFI_SCAN results; repeated calls alone are not fresh scans.
- LED_EXTERNAL remains a compatibility wrapper: channel 0 is red GPIO47,
  channel 2 is blue GPIO17. Prefer LED_RED and LED_BLUE.
- SD_READ receives offset/length plus an ASCII path; its hex chunk reply uses
  the calling transport (BLE or USB). It neither streams a whole file nor
  deletes the original. Clients must request successive chunks.

## BLE primitives

- BLE_SCAN: nearby BLE advertisements (addresses and RSSI).
- BLE_PEER_SET: persist the command peer address, not Wi-Fi credentials.
- BLE_STATUS: report the command transport's connection state.

## Channels

Currently a program channel binds a native function ID and arguments. Each
binding owns its result queue and busy bit; threads/sequences have additional
execution-level busy state. A function is not automatically assigned one
permanent global channel. Multiple programs can bind the same function.
Therefore busy bits alone are not a universal per-hardware ownership lock.
Changing to globally shared per-function channels would need explicit rules
for queue consumers so one thread cannot consume another thread's results.

## OLED on Neo

The existing `iris-gif-oled` tool draws images, text, or both using one bitmap:

```sh
sudo /home/noob/iris-gif-oled --text 'IRIS'
sudo /home/noob/iris-gif-oled /home/noob/iris-photo-check.gif --text 'IRIS' --text-y 112
```

White letters have a black backing by default. Use
`--text-background transparent` to leave the image unchanged behind letters.
The tool retains the validated SH1107 initialization and complete page writes.
Neo's native registry exposes IMAGE_FORMAT, OLED_DRAW, OLED_TEXT and
DISPLAY_START/STOP/STATUS. ESP forwards them through the matching NEO_ functions.
See `neo/tools/DISPLAY.md` for the mascot/status thread and black text overlays.

## Verification/deployment

Neo dispatcher compiled with -Wall -Wextra -Werror and was installed with a
backup at /usr/local/sbin/noob-neod.before-native-registry-20261004.
Native argument tests: neo/tests/native-registry.c. Live numeric/ASCII calls,
argument rejection, legacy calls and VM_READ passed. BLE -> ESP -> Neo CAPS
still works. User visually confirmed the standalone letters.

ESP firmware was flashed and hash-verified on 2026-10-04. The 138-byte
police-on-all VM is active with stored startup autorun. With Neo USB reconnected,
read-only boot checks completed with 38 ready, zero failed, zero pending and four
physical outputs untested. The Neo display worker is running; recent logs show
successful complete OLED page writes.
