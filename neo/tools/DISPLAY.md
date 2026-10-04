# Iris display native functions

Source image: `/img/Iris.png`, copied from the downloaded mascot without
changing the original. OLED image: `/img/Iris_formatted.gif`.

`iris-photo-gif INPUT` produces `INPUT_STEM_formatted.gif`. It squares/resizes
to 128x128, stretches contrast and creates a two-color black/white GIF. The
image can be drawn alone or with a text overlay using `iris-gif-oled`.

Native functions on Neo use the same numeric + ASCII convention as ESP:

```sh
noob-neoctl image-format Iris.png
noob-neoctl display-status
noob-neoctl oled-draw Iris_formatted.gif
noob-neoctl oled-text 'Hello Iris'
noob-neoctl display-start Iris_formatted.gif 5000
noob-neoctl display-stop
```

Formatting refuses to overwrite an existing formatted file. Check DISPLAY_STATUS
for asynchronous completion/exit status. Draw/text commands cannot interfere
with an active display thread; stop it first. A matching DISPLAY_START request
is idempotent; changing its image/interval replaces the thread.

`hw_display.c` owns the display worker and busy state. `noob-display` implements
the fixed operations; `thread_display` composes them. The thread draws three
black-on-white status lines: ESP Wi-Fi IP; temperature/humidity/BLE; VM program
name and state. WAITING is shown as RUN. The name is matched against the exact
persisted bytecode using reference VMs in `/usr/local/share/noobia/vm`; unknown
programs are labelled VM rather than guessed from byte count.
The mascot occupies an 80x80 square at bottom right, separate from the text.
`NOOB_STATUS_MASCOT_SIZE` configures its size (16..88). Original images are not
changed. Iris uses `/img/Iris_80_formatted.gif`, generated from the original
`/img/Iris.png` by resizing to 80x80 before contrast/monochrome conversion.
`NOOB_STATUS_IMAGE` selects this separate thumbnail without changing the ESP VM.
It reads ESP's private USB command link, with five-second waits
between refreshes. Request/drawing time is additional; this is not a real-time
five-second deadline. `NOOB_OVERLAY_STATUS=0` disables Wi-Fi/BLE/VM queries.
Only the first frame initializes the panel; subsequent frames use `--skip-init`
to avoid repeated display-off/on flicker. Restart the thread after OLED power loss.
It does not capture
camera images, transmit IR or disturb the police detector threads. Sensor
failure displays missing values; a lost USB link displays "ESP link unavailable",
not stale readings. Wi-Fi IP is ESP's LAN address, not Neo's private USB address.

Install/configure using `noob-display.conf.example`; all tools are in
`/usr/local/bin`. The existing command service runs as noob, with its i2c group
added only to the service. It remains bound to the private USB subnet.

Build the daemon with both source files:

```sh
cc -O2 -Wall -Wextra -Werror noob-neod.c hw_display.c -o noob-neod
```

The ESP forwards `NEO_IMAGE_FORMAT`, `NEO_OLED_DRAW`, `NEO_OLED_TEXT`,
`NEO_DISPLAY_START/STOP/STATUS` through its native registry. The display startup
request retries every ten seconds, accommodating Neo's slow boot. If started
by a running VM, it requests DISPLAY_STOP when that VM stops, resets or faults.
A remotely started display has explicit stop control.

`iris/programs/vm_police_on_all.hex` is 138 bytes and starts this display thread
alongside the three detectors. Host execution tests exercise all three trigger
paths and STOP (`esp/common/tests/run-police-display.sh`). Firmware build passed.
The VM must not be run on old ESP firmware lacking native function 269.

Deployment status (2026-10-04): Neo functions, mascot and status overlay installed;
ESP firmware flashed and the 138-byte startup VM activated with persistent
autorun. With native USB reconnected, the display worker is running and recent
logs show complete 16-page OLED writes without errors. Live status reads confirm
temperature/humidity, Wi-Fi IP/RSSI and connected BLE. Physical screen appearance
still needs human confirmation. Host overlay tests cover available/missing data:
`bash neo/tests/test-thread-display.sh`.
