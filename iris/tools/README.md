# Nexus Noob tools

`irisctl` derives paths from its own location and reads `iris-tools.conf`.
Portable VM programs are discovered in `../../esp/common/programs`; Iris-only
programs remain in `../programs`.

`build_iris.sh` compiles `../firmware/iris_noob` directly against the shared
Arduino library at `../../esp/common`. It accepts `--build-dir`, `--jobs`,
`--fqbn`, `--extra-flags`, `--common-library`, and `--sketch`; machine-specific
toolchain paths remain in ignored `iris-build.local.conf`.

Program controls include:

    irisctl thread-start police_lights
    irisctl thread-stop
    irisctl blue-blink 0
    irisctl police-sequence 0
    irisctl motion-police
    irisctl sensor-police
    irisctl light-change-start 200 250
    irisctl light-change-poll
    irisctl mic-rise-start 200 20
    irisctl mic-rise-status
    irisctl sound-police
    irisctl sequence-status
    irisctl sequence-pop 0
    irisctl sequence-busy 0
    irisctl ultrasonic-change-start 100 250
    irisctl ultrasonic-change-status
    irisctl ultrasonic-change-pop
    irisctl ultrasonic-change-stop

The final argument to the LED sequence commands is `0` for one pass or `1`
for repetition.

`motion-police` loads and runs the VM that starts the 250 ms ultrasonic
change thread and triggers one two-second police-light sequence for each new
motion episode.

The light-change commands use a runtime baseline. Their first argument is an
ADC delta sensitivity, not an absolute light level.

`mic-rise-start` keeps only ten one-second integer buckets. The first argument
is a percentage ratio and the second is a minimum new-half RMS. `sound-police`
uses 200% and RMS 20, then runs the finite police sequence on each event.
`sensor-police` combines both detectors. Light sampling pauses for the
entire LED sequence while the detector thread keeps running, avoiding feedback.

`noobctl` is a native C utility for serial NRP/1 commands. It deasserts DTR
and RTS, disables hangup-on-close and hardware flow control, and waits through
possible USB-UART reset:

    ./noobctl /dev/ttyUSB0 1 PING
    ./noobctl /dev/ttyUSB0 2 CAPS
    ./noobctl /dev/ttyUSB0 3 LOAD 01000700000000

The default is 3 seconds of startup settling plus up to 15 seconds for a reply
after transmission. An external `timeout 5` or `timeout 6` cuts this short and
does not establish that firmware is hung. Use the client's bounded wait, or at
least `timeout 22`. Set `NOOB_SERIAL_SETTLE_MS` and `NOOB_SERIAL_TIMEOUT_MS` to
override these intervals (milliseconds, 0–120000).

For VM/native tests, keep one connection open and put `PING` after the operation:

    printf 'PING\nCALL STORAGE_STATUS\nPING\n' | ./noobctl_batch /dev/ttyUSB0

Reopening a USB bridge may still pulse reset, depending on its driver and wiring.
A reply followed by silence on a new connection alone is not proof of a native
service failure.

Hardware-free regression tests use pseudo-terminals:

    cc -O2 -Wall -Wextra -Werror noobctl.c -o noobctl
    cc -O2 -Wall -Wextra -Werror noobctl_batch.c -o noobctl_batch
    cc -O2 -Wall -Wextra -Werror test_noob_serial.c -o /tmp/test_noob_serial -lutil
    /tmp/test_noob_serial ./noobctl ./noobctl_batch

These check fragmented replies under log traffic, a real wall-clock timeout,
multiple commands on one connection, and clearing inherited serial flags.

Set `NOOB_SERIAL_EVENTS=1` to print unsolicited events while waiting for replies.
Replies reporting `ERR` now return a nonzero process status. The client reads
only through the matching reply, preserving following event bytes for the next
request. This favors simple framing over bulk-transfer throughput.

For a bounded live RSSI test (loads/replaces the current VM, leaves RSSI off):

    cc -O2 -Wall -Wextra -Werror noob_rssi_test.c -o noob_rssi_test
    ./noob_rssi_test /dev/ttyUSB0

This starts the ten-second RSSI VM, polls on one serial connection, counts
received RSSI samples, checks status, then explicitly stops collection and VM.
Full Wi-Fi scans take time: the native one-second pause is between scans, not
a guarantee of one complete all-channel scan each second.

`nexus_ble_bridge.sh` creates the native BlueZ GATT application sought by
outbound BLE Noobs. `noob_ble_fd` is a small diagnostic helper that writes one
NRP/1 frame into the notification socket acquired by bluetoothctl. No Python
runtime or packages are used.

The bridge now registers advertising through the same `bluetoothctl`
application; stopping it releases that application's GATT service/advertisement.
It preserves the existing log and prevents duplicate bridge instances. The
privileged notification helper is still a diagnostic mechanism, not a secured
production daemon. A peer MAC is not cryptographic authentication.

Run `bash /noobia/iris/diagnostics/restore_ble.sh` with the bridge connected to
test PING, native SD/mic calls, and VM load/run/stop/replacement over BLE.

The Nexus HCI controller is the Realtek 0bda:8771 adapter at
`00:E0:4C:23:99:87`.
