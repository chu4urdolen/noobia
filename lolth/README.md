# Lolth: LAFVIN Spiderbot and NoobRuntime

Lolth is an ESP8266 Spiderbot. **A Noobia extension of LAFVIN's SpiderBot
firmware is installed now** and serves an HTTP API over its own access point. The NoobRuntime firmware
remains here for later restoration. It uses the shared `esp/common` runtime:
NRP/1 commands, native function registry, bounded VM, and common sequencer.
`lolth.cpp` is its composition root; pins and hardware policy live here, not
in `esp/common`.

The initial 4 MiB flash image is preserved as
`lolth-factory-backup-2026-09-25.bin`. `esptool image_info` recognizes a valid
ESP8266 image in it. The full Noob flash immediately before the LAFVIN restore
is `lolth-before-factory-restore-2026-09-27.bin`. Preserve both files; neither
has been pushed to GitHub.

## Hardware and connection

LAFVIN's servo order is:

| Servo | GPIO | Board label |
| --- | ---: | --- |
| 1 | 14 | G14 |
| 2 | 12 | G12 |
| 3 | 13 | G13 |
| 4 | 15 | G15 |
| 5 | 16 | G16 |
| 6 | 5 | G5 |
| 7 | 4 | G4 |
| 8 | 2 | G2 |

Noob mapped every joint and observed these normal positions on 2026-09-27.
Direction describes what happens when the commanded angle increases:

| Servo | Joint | Normal angle | Increasing angle moves |
| ---: | --- | ---: | --- |
| 1 | Front right lower | 90° | Up |
| 2 | Front right upper | 90° | Forward |
| 3 | Back right upper | 90° | Forward |
| 4 | Back right lower | 95° | Down |
| 5 | Front left lower | 75° | Down |
| 6 | Front left upper | 121° | Backward |
| 7 | Back left upper | 90° | Backward |
| 8 | Back left lower | 105° candidate | Up |

These are physical observations, not position feedback from the servos.
The Noob firmware initializes its command state to 90° on reboot; the
observed normal angles above are recorded here and in VM programs.

The ultrasonic module uses TX/GPIO1 for trigger and RX/GPIO3 for echo. This
prevents USB serial commands while it is connected. The Noob firmware, when
installed, creates a WPA2 access point named **Noobia-Lolth** using the local
password in `lolth_ap.h` and serves NRP/1 at **192.168.4.1:4242**. `lolthctl.py`
defaults to this address. That image does not join Noobia. Its previous
station image is kept
in `.build/noob/lolth_noob.ino.bin` for rollback. The AP settings are in
ignored `firmware/lolth_noob/src/lolth_ap.h`; copy its `.example` template
and set a private password before building.
The ESP8266 has Wi-Fi but no integrated Bluetooth; the shared runtime now has
a TCP transport alongside Iris's ESP32 BLE transport.
LAFVIN's packaged `0.SpiderBot/webserver.cpp` creates its own AP with
`WiFi.softAP(...)`: its SSID is `Robot - ` plus the uppercase hex of the last
two AP MAC bytes, and its password is `12345678`. It serves its web control
API on port 80. In `0.SpiderBot.ino`, factory setup starts that AP, attaches
all eight servos, and sends every servo to the zero pose. The source is in
LAFVIN's [Code and Libraries resource package](https://lafvin-quadruped-spider-robot.readthedocs.io/en/latest/Introduction.html).
LAFVIN's example reference pose is `135, 45, 135, 45, 45, 135, 45, 135`°
in that pin order. The Noob firmware reports it in servo state as a reference, not applied
automatically. Lolth's observed normal angles are in the table above.

The Nexus user service `lolth-wifi-reconnect.service` keeps adapter
`wlx20e017103ffb` on the saved `Lolth LAFVIN AP` profile. It checks every
3 seconds while connected and waits 3 seconds between retries for one minute
after a connection. After that it stops initiating connections and leaves
ordinary autoconnect to NetworkManager, checking quietly every 10 seconds
for a new successful Lolth connection. Its script and unit are in
`tools/`. Check it with `systemctl --user status lolth-wifi-reconnect.service`
or stop it with `systemctl --user stop lolth-wifi-reconnect.service`.

## Installed LAFVIN firmware

The LAFVIN-based Noobia build is installed. It exposes **Robot - EC36**
with password **12345678** and HTTP at **192.168.4.1:80**. The original USB
Wi-Fi adapter `wlx20e017103ffb` is connected through the NetworkManager
profile `Lolth LAFVIN AP`; the newer `wlx40a5ef5f66f1` stays on Noobia.

From `/noobia/lolth`, read-only commands are:

```sh
python3 tools/lafvinctl.py info
python3 tools/lafvinctl.py state
python3 tools/lafvinctl.py calibration
```

The client also supports explicit motion commands: `action NAME`,
`servo NUMBER ANGLE`, and `stop [standby|center|zero]`. Its servo numbers are
1–8 for humans; the LAFVIN API uses zero-based servo IDs 0–7 and absolute
angles of 1–180°. `stop` requests a target pose and can move joints. Do not
send any motion command without a specific physical move agreed with Noob.
LAFVIN's setup attaches all servos and moves them to its zero pose on boot;
turning on battery power may move all legs immediately.

### Noobia extension to LAFVIN firmware

The manufacturer source is preserved in `firmware/lafvin_stock/0.SpiderBot`.
`firmware/lafvin_noobia/0.SpiderBot` is a separate build that retains its AP,
actions, and absolute servo API while adding:

| Endpoint | Purpose |
| --- | --- |
| `GET /api/v1/servos` | Last commanded angles for all eight servos; these are not position feedback |
| `POST /api/v1/servo/step` | One servo, signed electrical angle delta of 1–20° |
| `GET /api/v1/distance` | Ultrasonic millimetres and a valid flag; no echo returns `valid:false` |

The updated client maps human servo numbers 1–8 to LAFVIN IDs 0–7. `up` and
`down` increase and decrease the electrical angle, respectively; physical
direction depends on the joint. For example, these are **commands to use only
after a specific move is agreed**, not a test sequence:

```sh
python3 tools/lafvinctl.py servos
python3 tools/lafvinctl.py distance
python3 tools/lafvinctl.py up 1 5
python3 tools/lafvinctl.py down 1 5
```

The old VM `default.asm` and `standby.asm` remain as historical programs. Their
LAFVIN pose candidates are `programs/lafvin/default.json` (all eight servos)
and `programs/lafvin/standby.json` (four lower servos). Previewing sends no
request:

```sh
python3 tools/lafvinctl.py program programs/lafvin/default.json
```

`program ... --execute --servo NUMBER` applies one target; `--execute --all`
applies every target sequentially. These targets came from Noob calibration
and have not been physically validated with LAFVIN's angle mapping. Servo 8's
default target remains provisional.

Build the extension with the Arduino CLI and LAFVIN's bundled
`IRremoteESP8266` library installed under `.arduino-cli/user/libraries`:

```sh
/noobia/tools/arduino-cli/arduino-cli --config-file arduino-cli.yaml compile \
  --fqbn esp8266:esp8266:nodemcuv2 --output-dir .build/lafvin_noobia \
  firmware/lafvin_noobia/0.SpiderBot
```

The extension was built and flashed on 2026-09-28. `info` reported
`1.0.0-noobia.1`; `servos` returned all eight startup targets, and `distance`
correctly returned `valid:false` with the sensor unplugged. After the sensor
was reconnected and USB removed, two reads returned valid distances of 241 and
247 mm. A later request timed out when Lolth's battery-powered AP disappeared.

### LAFVIN calibration logic

The firmware stores eight signed offsets in EEPROM, indexed 0–7 in the GPIO
order in the table above. Each servo command applies `target + offset`, then
maps logical angle 1–180 to a 400–2400 µs pulse. The startup zero targets are
`135,45,135,45,45,135,45,135`. The `Servo_Offset[]` constant in
`actionarray.h` is unused; the EEPROM values are authoritative. The most
recent read on 2026-09-27 returned `-1` for every offset, likely an erased
EEPROM byte interpreted as signed `int8_t`.

`GET /api/v1/calibration` reads all eight offsets. `POST` to that endpoint
replaces all eight and commits each to flash; accepted values are -124 to
+124, while the web UI recommends staying within ±30 for quick adjustment.
Saving offsets does **not** command a servo immediately. The new offset takes
effect on the next servo target or action, including the zero pose at boot.
The code does not clamp `target + offset` before mapping, and neither the
calibration endpoint nor `servos` provides physical position feedback. Calibrate
one physical joint at a time, keeping the other seven stored offsets unchanged.

Use the CLI for one offset at a time; calibration IDs here are zero-based:

```sh
python3 tools/lafvinctl.py calibration             # read all offsets
python3 tools/lafvinctl.py calibration set 4 35    # absolute offset
python3 tools/lafvinctl.py calibration add 4 -15   # relative change
```

The client reads the current array, changes only the selected entry, saves it,
then reads it back to verify. These commands do not send servo motion.

## NoobRuntime functions (not currently installed)

IDs 100–115 are `SERVO1_UP`, `SERVO1_DOWN`, through `SERVO8_UP`,
`SERVO8_DOWN`. `UP` increases the servo's electrical angle; `DOWN` decreases
it. Physical up/down direction differs by joint and must be mapped on Lolth
before naming physical motions. A direct call moves 5° by default or accepts
an explicit 1–20° step. The same functions accept a second `enable` bit from
a common sequence channel, so a zero bit leaves the servo alone.

| ID | Function | Arguments / result |
| ---: | --- | --- |
| 116 | `SERVO_ARM` | Servo number 1–8, initial angle 10–170°; attaches one servo |
| 117 | `SERVO_SET` | Servo number and absolute angle; requires armed servo |
| 118 | `SERVO_STATE` | Servo number; returns angle, armed state, and GPIO |
| 119 | `SERVO_DETACH` | Servo number; stops its pulses |
| 120 | `SERVO_DETACH_ALL` | Stops the sequence and all servo pulses |
| 121 | `DISTANCE_MM` | One ultrasonic reading in millimetres |
| 122 | `SERVO1_WIGGLE` | Two channel, four step example; arm servo 1 first |

No servos attach on boot. **Lift Lolth clear before arming a joint**: its first
pulse moves it to the requested angle. The 10–170° software range is only an
initial bound, not proof of mechanical clearance. Work one joint at a time.
`SERVO_DETACH_ALL` stops control pulses; physical power off is the local
emergency stop. Detached legs may move under load.

Examples from a computer connected to the Noobia-Lolth AP:

```sh
python3 tools/lolthctl.py info
python3 tools/lolthctl.py caps
python3 tools/lolthctl.py distance
python3 tools/lolthctl.py arm 1 90
python3 tools/lolthctl.py up 1 5
python3 tools/lolthctl.py down 1 5
python3 tools/lolthctl.py state 1
python3 tools/lolthctl.py wiggle
python3 tools/lolthctl.py stop
```

To compose another pattern through the common sequencer, send NRP/1 commands
via `raw`, for example `CALL_TEXT SEQUENCE_SET 0 300 SERVO2_UP 1010 5`, then
`CALL SEQUENCE_START`. The final `5` is the fixed step size; each bit becomes
the second argument to the function. VM programs can invoke the same numeric
IDs. `CALL SEQUENCE_STOP` ends a running sequence.

## VM standby pose

[`programs/standby.asm`](programs/standby.asm) and its wire-ready
[`standby.hex`](programs/standby.hex) implement the lower-leg part of
[LAFVIN's published standby pose](https://lafvin-quadruped-spider-robot.readthedocs.io/en/latest/kitforlearningcourse.html).
LAFVIN's lower-servo targets are 60°, 120°, 120°, 60°. Applying Lolth's
observed normal offsets gives servo 1 = 60°, servo 4 = 125°, servo 5 = 105°,
and servo 8 = 60°. The first three lower targets are 30° from their observed
normal positions. Servo 8's 60° standby target looked right in the live test,
but its normal angle is being recalibrated. This does **not** command a 90°
servo rotation. Upper servos are untouched. The four `SERVO_ARM` VM syscalls
run in one VM tick without waits, so the four joints start moving close
together, though the hardware pulses are not exactly simultaneous.

Loading the program does not move Lolth. Running it does:

```sh
python3 tools/lolthctl.py load programs/standby.hex
python3 tools/lolthctl.py raw RUN
python3 tools/lolthctl.py raw STATUS
```

The VM halts after setting the pose; the four lower servos remain armed to
hold it. `python3 tools/lolthctl.py stop` detaches them when desired.

[`programs/default.asm`](programs/default.asm) and
[`default.hex`](programs/default.hex) return those same four joints to their
observed normal angles: 90°, 95°, 75°, and a candidate 105° for servo 8.
The candidate corrects Noob's observation that the back left lower joint
sat about 15° too low after the first return. Like standby, the default
program leaves the upper joints untouched and keeps the lower joints armed.
Load it with `python3 tools/lolthctl.py load programs/default.hex`; `LOAD`
does not move Lolth, while a later `raw RUN` does.

## Build and flash

The local Arduino CLI and ESP8266 core 3.1.2 compile this firmware for NodeMCU
1.0. From `/noobia/lolth`:

```sh
/noobia/tools/arduino-cli/arduino-cli --config-file arduino-cli.yaml compile \
  --fqbn esp8266:esp8266:nodemcuv2 --libraries /noobia/esp \
  --output-dir .build/ap firmware/lolth_noob
```

**Before flashing, unplug the ultrasonic module from TX/RX.** LAFVIN warns
that the module conflicts with serial programming. Reconnect it and reset the
board after flashing. The factory image remains available for recovery.

## Installation history

The compiled Noob firmware was uploaded to the connected ESP8266EX (4 MiB
flash). The upload tool verified the written data, and a fresh Wi-Fi scan saw
`Noobia-Lolth` on channel 1. TCP replies, ultrasonic readings, and servo motion
still need live checks after the sensor is reconnected. The Nexus has one Wi-Fi
adapter and did not leave its own LAN to join Lolth's access point.

On 2026-09-27, station mode was flashed for the Nexus's current `MTEL-4064`
network. The credential file is ignored by Git. Lolth joined the LAN at
`192.168.8.101`, and `lolth.local:4242` answered `INFO`, `CAPS`, servo state,
and sequence status. An attempted unarmed servo step correctly returned
`arm servo first`. The ultrasonic module was still unplugged, so the distance
call returned `no ultrasonic echo`. No servo had been armed at that point.

After the sensor was reconnected, `DISTANCE_MM` returned 297 mm and later
398 mm with valid echo durations. A bounded Wi-Fi smoke test armed servo 1 at
90°, commanded 92° then 90°, and sent `SERVO_DETACH_ALL` in cleanup. A follow
up `SERVO_STATE 1` reported `armed:0`; sequence status remained idle. Physical
joint identity and motion quality await observation by someone beside Lolth.

A second Wi-Fi test on 2026-09-27 made servo 1 travel 90°→120° in six 5°
steps, hold for two seconds, then return in six steps. `SERVO_DETACH_ALL`
completed, and a follow up state query reported `angle:90,armed:0`. The
ultrasonic sensor still returned a valid echo afterward.

For joint mapping, servos 2–6 each received one 30° excursion toward their
LAFVIN reference angle and detached. Noob then narrowed the test to servos 3
and 4; their 30° excursions were repeated separately, and both reported
`angle:90,armed:0` afterward. Servos 7 and 8 have not been commanded. Noob
corrected the first observation: servo 1 is front right lower and servo 2 is
upper. Noob identified servo 3 as back right upper and servo 4 as back right
lower. Noob reported that servo 5 had not returned after its first test;
the controller's `angle:90` is a commanded value, not position feedback.
After a direct 90° command produced no visible return, servo 5 was swept
90°→60°→90° again in 5° steps. Noob identified it as left front lower.
Servo 6 was then swept 90°→120°→90° in 5° steps; its joint identity awaits
observation. Both sweeps ended with all servo pulses stopped. Mapping tests
now hold the return position for two seconds before detaching.

The pin order, pulse range, and ultrasonic wiring come from the
[LAFVIN learning course](https://lafvin-quadruped-spider-robot.readthedocs.io/en/latest/kitforlearningcourse.html);
the serial conflict is in their [flashing guide](https://lafvin-quadruped-spider-robot.readthedocs.io/en/latest/Programmingprogram.html).

On 2026-09-27, the fixed-address firmware was flashed and verified over USB.
Lolth answered ping and NRP/1 at `192.168.8.50:4242`. The corrected default
VM was loaded and run there; it halted after 77 bytes, and servo 8 reported
`angle:105,armed:1`. Physical confirmation of that last calibration is still
pending. The ultrasonic module was unplugged for flashing and needs
reconnecting before its readings can resume.

Later on 2026-09-27, firmware configured for the Noobia SSID and fixed
`192.168.100.50` was flashed over USB. Upload hash verification passed;
ping and NRP/1 `INFO` both answered at the new address. No servo command was
sent during or after this flash. Battery-powered Wi-Fi still needs checking
after USB is disconnected.

The station-only revision was flashed and hash-verified over USB on
2026-09-27. Lolth answered all three pings and NRP/1 `INFO` at
`192.168.100.50`; a local Wi-Fi scan showed Noobia but no `Noobia-Lolth`
access point. No servo command was sent.

The reliability revision disabled ESP8266 Wi-Fi sleep and made new TCP clients
replace stale command connections immediately. It was flashed and verified
over USB. A temporary diagnostic image then disconnected Lolth's Wi-Fi once;
she rejoined Noobia through the normal 10-second retry path and answered again
roughly 14 seconds after the last successful ping. The production image was
restored and verified afterward, and answered NRP/1 `INFO` and three pings.
No servo command was sent. During a separate one-minute probe, Nexus lost
10/60 pings to both Lolth and the Noobia gateway at the same time. This
indicates a shared Nexus-to-Noobia radio or access-point problem; it does not
establish a fault in Lolth's firmware. Nexus used a USB MT7601U Wi-Fi adapter,
and its scan showed Noobia signal varying from about 45% to 69%. The adapter
reported power management already off, so changing its power-save setting
would not explain the observed loss. Noobia access-point settings were not
changed.

An experimental USB serial control build flashed on 2026-09-27 raised
repeated ESP8266 fatal exception 0 and could not answer NRP/1. A simplified
USB-only build failed in the same way. The previously verified station image
was restored and hash-verified; Lolth then answered three pings and NRP/1
`INFO` at `192.168.100.50`. No servo command was sent during these flashes.

Later on 2026-09-27, the AP-only Noob image was flashed and hash-verified.
`Noobia-Lolth` appeared on channel 1. Nexus joined it at `192.168.4.2` and
received NRP/1 `INFO` and a read-only servo 8 state response from
`192.168.4.1:4242`; servo 8 reported 90° and unarmed. Nexus then rejoined
Noobia. A one-minute AP check completed 60/60 fresh NRP/1 `INFO` requests
without a failure. No servo command was sent. Battery-powered operation
remains untested.

Later that day, Nexus gained a second USB Wi-Fi adapter. The new MediaTek
MT7612U (`wlx40a5ef5f66f1`) uses the cloned `Noobia MT7612U` NetworkManager
profile and holds `192.168.100.8` plus the default route. The original MT7601U
(`wlx20e017103ffb`) uses `Noobia-Lolth` at `192.168.4.2`; that profile has
`ipv4.never-default=yes`. Routes to `192.168.4.1` use the MT7601U while
internet traffic uses the MT7612U. Lolth answered `INFO` and read-only servo 8
state over the AP, and a further 30/30 `INFO` requests succeeded while the
Noobia adapter remained online. A ping to `1.1.1.1` via the MT7612U succeeded.
No servo command was sent during this network check.

After USB was removed, Lolth's AP disappeared despite the battery switch being
reported on with red power and blue LEDs. Reconnecting USB alone did not
immediately restore the AP. A passive serial-port open (DTR and RTS requested
off) captured an ESP8266 boot message with reset cause 2; the port open may
have triggered that reset. The AP then reappeared, and `INFO` and read-only
servo 8 state answered over `192.168.4.1`. This does not yet establish that
the controller runs on battery alone; repeat the AP check after USB removal.
On that repeat, removing USB again made `Noobia-Lolth` disappear immediately;
both Wi-Fi adapters' scans lacked the SSID, and the old adapter fell back to a
saved network. The AP had answered `INFO` moments earlier with USB connected.
This isolates the current failure to battery-only boot/power or an interaction
that occurs during USB removal; it does not establish a firmware fault. No
servo command was sent.
The user then reported a blue LED still visible (possibly faint) without USB.
Fresh scans from both USB Wi-Fi adapters again found no `Noobia-Lolth` SSID.
The LED's board/location and the battery voltage have not yet been identified.

Later on 2026-09-27, with the battery switch off and ultrasonic module removed,
Nexus read the complete 4 MiB Noob flash to
`lolth-before-factory-restore-2026-09-27.bin` (SHA-256
`dbff9b4c7b45e2a5f726ca64ebc478f1e4c41a69e5fe7cc9380453144366f7e4`).
The initial 4 MiB backup was restored and hash-verified, but it exposed only
an open `ESP-83EC36` AP; its `192.168.4.1` host answered ping while ports 80
and 4242 refused connections. LAFVIN's packaged source and prebuilt binary
were then staged at `firmware/lafvin_stock/0.SpiderBot/`. The supplied
`BIN/SpiderBot.ino.bin` (SHA-256
`2924db3bcbc718d3facde74dc5b4c6452dc2b9f1b7600cfc8991dac18f200ca4`)
was flashed and hash-verified. It now broadcasts WPA2 `Robot - EC36`.
Read-only `info`, `state`, and `calibration` HTTP requests succeeded; the
reported firmware is `QuadBot-E` 1.0.0, idle, with eight calibration offsets
of -1. No action, servo, or stop request was sent. Battery-only operation of
that manufacturer image was not checked.

On 2026-09-28, the Noobia extension compiled and was flashed with esptool
hash verification. Its binary SHA-256 is
`a301c9e0389d7aa74261c7c9719ddcf696f5ac8b81cbc78fce48d0cd3ce5cd03`.
The AP returned as `Robot - EC36`. Read-only API checks returned firmware
`1.0.0-noobia.1`, eight last-commanded startup targets
`135,45,135,45,45,135,45,135`, and an invalid ultrasonic echo while the
module was unplugged. No action, servo, or step request was sent.

After the ultrasonic module was reconnected and ESP USB unplugged, the
extension answered two valid battery-powered distance reads: 241 and 247 mm.
The next read timed out; Nexus lost its `192.168.4.2` address and Lolth's AP
later vanished from scans. The `Lolth LAFVIN AP` NetworkManager profile was
given static `192.168.4.2/24`, no default route, and higher autoconnect
priority to avoid DHCP renewal interrupting the local connection. The saved
`MTEL-4064` profile's autoconnect was disabled so the old adapter prefers
Lolth. A reconnection attempt failed because the AP was absent. This is still
an intermittent battery-power or controller-availability issue; no servo
command was sent during diagnosis.
With only the red power LED visible, a later scan saw `Robot - EC36` again at
62% signal, but a connection attempt failed because the network vanished before
association. Thus red-only LED state does not prove the ESP is off; the AP is
intermittent. The old adapter may join other saved networks while Lolth's AP is
unavailable. The two valid distance readings remain the only confirmed live
ultrasonic samples after USB removal.

On 2026-10-05, Lolth's live `/api/v1/info` identified firmware
`1.0.0-noobia.1`. All eight stored calibration offsets read as -1. At Noob's
request, only LAFVIN servo index 0 (our servo 1, front right lower) was set
to +44 through `/api/v1/calibration`; the verified array is now
`[44,-1,-1,-1,-1,-1,-1,-1]`. The write did not send a servo target or action.
The new offset will affect that joint on its next command or startup zero pose;
its physical result has not yet been observed.

At Noob's next instruction on 2026-10-05, servo index 0's saved offset was
decreased by 90 from +44 to -46. Readback verified the array
`[-46,-1,-1,-1,-1,-1,-1,-1]`; no servo target or action was sent. The
startup zero target for this joint will be `135 + (-46) = 89` logical degrees
on its next reboot or target command.

Noob then requested +20 for the next LAFVIN servo, index 1 (our servo 2,
front right upper). EEPROM readback verified
`[-46,20,-1,-1,-1,-1,-1,-1]`. No servo target or action was sent. Its startup
zero target will be `45 + 20 = 65` logical degrees when reapplied.

Noob later corrected servo index 0's offset from -46 to -43. Readback verified
`[-43,20,-1,-1,-1,-1,-1,-1]`; no servo target or action was sent. A request
to set servo index 1 to -65 was held: its startup target would be `45-65=-20`,
outside the logical 1–180 range. The current code maps that to about 166 µs,
then ESP8266 `Servo.write(166)` interprets 166 as degrees rather than
microseconds, potentially driving near the opposite endpoint. Servo index 1
therefore remains +20 until a safe calibration target is agreed.
