# Iris restoration — 2026-09-15

> Historical restoration record. Later sections describe temporary I2C/OLED
> firmware that is no longer current. As of 2026-09-22 Iris registers no
> external I2C or OLED capability.

Firmware: `0.2.1-no-external-i2c`, flashed and tested over UART.
Build: `bash /noobia/iris/tools/build_iris.sh`.
Artifact: `build/iris-restored-no-external-i2c/iris_noob.ino.bin`.
Application: 1,349,443 bytes, 42% of the 3 MB app partition.
Profile: physical 16 MB flash, QSPI PSRAM enabled. The chosen partition table
uses the first 4 MB; it does not allocate the entire flash or provide dual-app OTA.

External Wire/I2C, software-I2C diagnostics and SH1107/OLED are excluded from
the linked image (symbol check in build script). Camera SCCB is retained.

## Live verification

- `restore_smoke.nrp`: PING/INFO/CAPS; VM arithmetic; SD capacity (237760 MB)
  and microphone RMS via SYS; WAIT, STOP, replacement and RUN; follow-up PINGs.
- `restore_media_radio.nrp`: VM photo capture (sequence 19), one-second WAV
  (16000 samples), two-frame MJPEG; SD directory listings; Wi-Fi connected to
  Noobia at 192.168.100.10; four Wi-Fi networks and seven BLE devices scanned.
- `restore_vm_store.nrp`: saved 17-byte arithmetic VM to
  `/programs/restore_check_20260915.nvm`, reset/replaced memory, loaded from SD,
  ran and obtained r2=12. This is an SD readback test, not a power-cycle test.
- Wi-Fi disconnect passed. Immediate reconnect with a 10-second deadline timed
  out, but subsequent PING passed. A bounded retry with `WIFI_CONNECT 30000`
  succeeded at 192.168.100.10, RSSI -74 dBm. Do not interpret the first timeout
  as a firmware hang. Set `NOOB_SERIAL_TIMEOUT_MS=45000` for this longer call.
- BLE command transport remains unverified in this restoration run: the
  configured Nexus peer was disconnected. Scanning is not a connection test.
- RSSI VM start/wait/automatic stop passed in `restore-rssi-poll-20260915.log`:
  WAITING became HALTED at pc=14; repeated PINGs passed. The batch client filters
  non-reply frames, so this test does not verify delivery of RSSI event payloads.
  The first short observation ended while WAITING; the longer polling run
  established completion. RSSI gathering was explicitly left off.

Raw responses are in `results/restore-*-20260915.log`. Media and the named
diagnostic VM were left on SD; existing user files were not deleted.

## Host reliability

Serial clients now disable HUPCL/CRTSCTS, deassert modem lines, settle for three
seconds, and allow a bounded 15-second reply deadline. Short outer timeouts used
previously could expire before a valid reply. Batch tests keep one port open.
Hardware-free C pseudo-terminal tests passed: fragmented/delayed replies,
continuous-log timeout, and three consecutive batch requests.

Earlier timeouts did not establish a GPIO fault or an I2C-induced firmware hang.
Build configuration and serial handling were corrected together; these tests
do not isolate a single cause for all historical failures.

Next host-tool improvement: an opt-in event stream with persistent framing
across reads/replies, allowing RSSI event verification without reopening UART.

## Follow-up: BLE and RSSI verified

Host-only changes; firmware remains unchanged. `NOOB_SERIAL_EVENTS=1` exposes
unsolicited serial events, trailing bytes are no longer discarded after a reply,
and NRP errors return failure status. The C pseudo-terminal regression suite
passes, including an event sent immediately after a reply.

`tools/noob_rssi_test` received seven RSSI samples over UART; the ten-second VM
halted and explicit RSSI_OFF/STOP/PING succeeded. See
`results/restore-rssi-events-20260915.log`.

Repaired literal newline escapes in the shell BLE tools and replaced the stalled
raw btmgmt advertising invocation with application-scoped BlueZ advertising.
Reference: https://github.com/bluez/bluez/blob/master/doc/bluetoothctl.rst
Iris connected automatically to Nexus and acquired the command notification
channel. `restore_ble.sh` passed PING/INFO, SD and mic native calls, arithmetic
(r2=12), WAIT/STOP, replacement arithmetic (r2=8), and final PING over BLE.
See `results/restore-ble-20260915.log`.

The RSSI VM was then uploaded/run over BLE; actual RSSI event payloads arrived
through `irisctl watch`, including Noobia. See
`results/restore-ble-events-20260915.log`. The watcher uses a bounded timeout;
exit 124 at the end of that observation is expected, not a transport failure.

Bridge remains a local diagnostic harness, not an authenticated production
service. Peer MAC filtering is not cryptographic authentication. No external
I2C/GPIO changes or firmware flashes were made in this follow-up.

## Follow-up: lazy hardware I2C

Current firmware is `0.2.2-lazy-i2c`, artifact
`build/iris-lazy-i2c/iris_noob.ino.bin`, flashed with verified hashes. It uses
1,361,027 bytes (43%) and 62,288 bytes static RAM (19%). Hardware I2C is linked;
SH1107/U8g2 and software bit-bang I2C are excluded by build-time symbol checks.

The bus is dormant at boot. Iris-specific registration fixes SDA=GPIO15 and
SCL=GPIO16; the reusable ESP32 service does not know those pins. Remote callers
may select 10–400 kHz, but cannot redirect I2C onto camera, SD or other pins.
`I2C_CLOSE` explicitly releases the controller and pins. Scan no longer closes
the bus implicitly, so a configured session can perform subsequent operations.

`restore_lazy_i2c.sh` ran over BLE and established:

- PING before I2C passed; scan before config returned `I2C unavailable`.
- `I2C_CONFIG 100000` opened GPIO15/16; the complete scan finished with zero
  responding devices, consistent with no powered/responding peripheral.
- PING after scan passed; close succeeded; scan after close again returned
  unavailable.
- Microphone RMS=19, camera capture sequence 20, and final PING all passed after
  the I2C session. The bus was left closed.

Raw replies: `results/restore-lazy-i2c-20260915.log`. No display writes were
attempted because the scan found no device. A later `CAPS` request exceeded the
current shell BLE diagnostic parser's practical reply handling and timed out;
short BLE commands remained the validated path. This is a host parser issue to
fix separately, not evidence of an I2C or firmware failure.

### Attached OLED line check

Firmware `0.2.3-lazy-i2c` adds read-only `I2C_LINES`; it calls `digitalRead`
without changing modes or starting the controller. With the reported OLED
wiring attached, idle GPIO15/16 both read low while I2C was closed. After
`I2C_CONFIG 100000`, both read high (`sda=1 scl=1 ready=1`), remained high after
a full scan, and no address ACKed. Earlier address-only scans at 100, 50 and
10 kHz also found zero devices. No OLED commands/data were sent. `I2C_CLOSE`
and final PING passed; the bus was left closed.

This establishes that Iris can release both lines and complete transactions,
but not why the module fails to ACK. If the OLED breakout has normal pull-ups,
both closed-bus lows point toward missing module power/ground, wrong connector
order, or the OLED not being electrically connected to GPIO15/16. Verify actual
voltages at the OLED pins before any display writes.
