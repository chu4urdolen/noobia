# Lynx NRP/1 runtime and haptic control

Lynx now speaks the Noob `NRP/1` line protocol used by Iris. Her Linux
endpoint listens on `192.168.100.107:4243` and accepts only Nexus at
`192.168.100.106`. The wire shape is the same:
`NRP/1 <id> <command> [arguments]`, with `OK`, `ERR`, and sequence
`NRP/1 0 EVENT` replies. It supports `PING`, `INFO`, `CAPS`,
`LOAD`, `RUN`, `START_THREAD`, `STOP`, `STOP_THREAD`, `RESET_VM`,
`STATUS`, `THREAD_STATUS`, `CALL`, `CALL_TEXT`, and `CALL_MIXED`.
Commands can be sent with `tools/lynx_noobctl.py` on Nexus or any NRP/1
client using the permitted address. The existing SSH path remains available.

This is a Linux implementation of the common runtime behavior, not a build of
the Arduino C++ library. The version 1 bytecode layout is the same: at most
1024 program bytes, 256 data bytes, eight signed 32-bit registers, eight
call frames, and 32 instructions per tick. Numeric native IDs 1–12 implement
the common clock and four-channel sequencer ABI. Tracks hold at most 64 bits
in text form or 32 packed bits from VM/CALL, seven fixed numeric arguments,
and eight result records. A repeating sequence must be stopped explicitly.
The image-cycle thread has the common `running`, `channel_busy`,
`queued`, `dropped`, `POLL`, and `STOP` behavior. The controller starts
with no VM running and no thread or sequence active.

## Lynx native functions

| ID | Name | Arguments | Effect |
| --- | --- | --- | --- |
| 300 | `HAPTIC_SET` | `duration_ms bit` | 20–250 ms pulse for bit 1; stop for bit 0 |
| 301 | `HAPTIC_STATUS` | none | Read active state |
| 302 | `HAPTIC_STOP` | none | Explicit motor stop |
| 310 | `IMAGE_SELECT` | `pose_index` | Select a pose by sorted manifest index |
| 311 | `IMAGE_CHOOSE` | `pose0 pose1 bit` | Choose between two poses from a sequence bit |
| 312 | `IMAGE_POSE` | ASCII pose name | Select by name via `CALL_MIXED` or `CALL_TEXT` |
| 313 | `IMAGE_ANIMATE` | ASCII animation name | Select an animation |
| 314 | `IMAGE_QUEUE` | ASCII pose or animation name | Append to image queue |
| 315–319 | `IMAGE_PAUSE`, `IMAGE_RESUME`, `IMAGE_STOP`, `IMAGE_NEXT`, `IMAGE_PREVIOUS` | none | Image transport controls |
| 330–333 | `IMAGE_CYCLE_*` | interval/start, stop, status, poll | Compiled image thread |
| 340 | `SOUND_PLAY` | ASCII catalog name | Play through the existing media service |
| 341 | `SOUND_QUEUE` | ASCII catalog name | Append to sound queue |
| 342–346 | `SOUND_PAUSE`, `SOUND_RESUME`, `SOUND_STOP`, `SOUND_NEXT`, `SOUND_PREVIOUS` | none | Sound transport controls |
| 350–353 | `BATTERY_PERCENT`, `BATTERY_TEMP`, `BATTERY_CURRENT`, `BATTERY_VOLTAGE` | none | Validated gauge readings; percent, m°C, signed mA, mV |
| 354 | `SOC_TEMP` | none | SoC maximum thermal zone in m°C |
| 355 | `AUDIO_READY` | none | ALSA card and loaded TFA98xx firmware status |
| 360–362 | `ACCEL_X`, `ACCEL_Y`, `ACCEL_Z` | none | Latest Bosch accelerometer raw axis; shared sample cache for coherent reads |
| 363–364 | `ACCEL_STATUS`, `ACCEL_VECTOR` | none | Sensor registration, or one full raw X/Y/Z sample |
| 365–367 | `GYRO_X`, `GYRO_Y`, `GYRO_Z` | none | Bosch gyroscope raw axes from one cached sample |
| 368–369 | `GYRO_STATUS`, `GYRO_VECTOR` | none | Sensor registration, or one raw X/Y/Z sample |
| 370–371 | `PROX_STATUS`, `PROX_RAW` | none | AMS proximity registration and one raw event |
| 372–373 | `LIGHT_STATUS`, `LIGHT_RAW` | none | Rear ambient light registration and one raw event |
| 374–376 | `MAG_X`, `MAG_Y`, `MAG_Z` | none | AKM09918 magnetometer raw axes from one cached sample |
| 377–378 | `MAG_STATUS`, `MAG_VECTOR` | none | Sensor registration, or one raw X/Y/Z sample |

Images and sounds resolve through the already installed `lynx-media`
service. Pose names and animations come from its current display manifest.
The haptic native writes only `oplus_duration` and `oplus_activate` in
`/sys/class/leds/vibrator`; it does not expose raw registers or unbounded
motor activation. Sequence stop and service shutdown explicitly write zero
to the motor control. A pulse also enforces its duration plus a 50 ms cooldown,
so a repeating VM cannot hold the motor continuously.

Examples from Nexus:

```sh
cd /noobia/lynx
python3 tools/lynx_noobctl.py PING
python3 tools/lynx_noobctl.py CAPS
python3 tools/lynx_noobctl.py CALL HAPTIC_SET 80 1
python3 tools/lynx_noobctl.py CALL HAPTIC_STATUS
python3 tools/lynx_noobctl.py 'CALL_MIXED IMAGE_POSE "01_standing_smile"'
python3 tools/lynx_noobctl.py 'CALL_MIXED IMAGE_QUEUE "dance"'
python3 tools/lynx_noobctl.py CALL IMAGE_NEXT
python3 tools/lynx_noobctl.py CALL IMAGE_STOP
python3 tools/lynx_noobctl.py LOAD @programs/haptic_two_pulses.hex
python3 tools/lynx_noobctl.py RUN
python3 tools/lynx_noobctl.py CALL SEQUENCE_STATUS
python3 tools/lynx_noobctl.py LOAD @programs/image_talk_sequence.hex
python3 tools/lynx_noobctl.py RUN
python3 tools/lynx_noobctl.py LOAD @programs/image_cycle_thread.hex
python3 tools/lynx_noobctl.py RUN
python3 tools/lynx_noobctl.py CALL IMAGE_CYCLE_STOP
python3 tools/lynx_noobctl.py CALL BATTERY_PERCENT
python3 tools/lynx_noobctl.py CALL BATTERY_TEMP
python3 tools/lynx_noobctl.py CALL SOC_TEMP
python3 tools/lynx_noobctl.py CALL AUDIO_READY
python3 tools/lynx_noobctl.py CALL ACCEL_STATUS
python3 tools/lynx_noobctl.py CALL ACCEL_VECTOR
python3 tools/lynx_noobctl.py CALL GYRO_VECTOR
python3 tools/lynx_noobctl.py CALL PROX_RAW
python3 tools/lynx_noobctl.py CALL LIGHT_RAW
python3 tools/lynx_noobctl.py CALL MAG_VECTOR
```

The read-only hardware calls were installed on boot
`42256da1-930e-4469-9370-cfba5ff1fd93` without changing boot partitions.
Live NRP/1 replies reported 45%, 28.7°C battery temperature, 328 mA charging
current, 7748 mV pack voltage, 35.609°C SoC temperature, and audio readiness
`1`. Gauge type and each reading's error flag are checked before a value is
returned. The previous daemon was saved as
`/usr/local/bin/lynx-noobd.before-sensors-20261028` on Lynx.

The matching August stock `hf_manager.ko` and `sensorhub.ko` register a Bosch
`bmi2xy acc` sensor through `/dev/hf_manager`. `ACCEL_X/Y/Z` use a bounded
one-second helper with at most three events; each call explicitly disables
the sensor before returning, and the runtime caches one vector briefly so
successive axis calls refer to the same sample. The numeric replies are raw
driver values with reported gain `1000`; their physical unit has not yet been
independently calibrated. The first live vector was approximately
`x=-107 y=186 z=9917`. The sensor service depends on the verified audio/SCP
stack and stages only the matching module hashes. The old daemon was also
saved as `/usr/local/bin/lynx-noobd.before-accel-20261028`.
The same bounded helper now serves gyroscope, magnetometer, proximity, and
rear light. Its normal path disables each sensor before returning; the
sensor manager's active list was empty after live trials. These are raw
driver readings, not calibrated SI units. The optical sensors returned
events but still need a deliberate light and near-object response test.
The clean boot receipt after installing `lynx-sensorhub` is
`logs/v50-audio-cold-boot-1793199862813330816/result.json`.

The three programs in `programs/` are generated by
`tools/build_lynx_vm_examples.py`, with readable `.asm` explanations.
The haptic program sets a four-position `1010` sequence at 200 ms and
80 ms pulses. The image program alternates talking and standing four times
at 500 ms, ending on the standing portrait. Both were loaded and run over
NRP/1 on Lynx: VM state `HALTED`, sequencer position `4/4`, and motor
off afterward. The image-cycle thread also started, queued three bounded
events, returned two through `POLL`, and stopped with `channel_busy=0`.
Noob confirmed feeling the repeated 80 ms NRP/1 pulse. The repeat
receipt is `logs/v50-haptic-repeat-1793138983869063779/`: command success,
kernel motor state `1` then `0`, motor off afterward, and Alpine health ready.
The third program started that compiled image thread through VM syscall
330. The VM halted after 13 bytes while the thread continued, published three
events, and then stopped on its own native stop call.

The three unmodified portable programs from `esp/common/programs` for
`time_now`, `arithmetic`, and `time_reset` also loaded and halted on Lynx;
the arithmetic program returned 12 in register 2. This checks the shared
bytecode boundary without any phone-specific assembly.

## Driver and boot state

The August CPH2493 stock package contains two haptic drivers. Legacy
`aw8697.ko` rejected the phone's revision `0x04`. The newer
`haptic_feedback.ko` and `haptic.ko` bound I²C `12-005a` as AW86907.
The matching `aw8697_haptic_170.bin` loaded successfully: 4465 bytes,
checksum passed, 14 RAM waveforms. One direct 80 ms sysfs trial logged
motor state `1` then `0`, and Alpine health stayed ready.

`lynx-haptic` is an OpenRC service that verifies the exact module and
firmware hashes, loads `kernel_fb.ko` before those two modules after the display supplier stack,
checks the driver binding, and stops the motor. `lynx-noobd` depends on
Wi-Fi and media and starts after haptic. Both are enabled in the default
runlevel. The first cold boot exposed a missing `kernel_fb.ko` dependency:
`haptic_feedback.ko` failed to load with `Unknown symbol fb_kevent_send_to_user`.
The matching August stock `kernel_fb.ko` was staged on Alpine with SHA-256
`d9c0e2546e6af4716e76c539bfe3339c9b52cbc4f88aa7c4c33717ad6201fade`,
and the service now checks that `mtk_boot_common` is loaded and loads
`kernel_fb` before `haptic_feedback` and `haptic`.

On the next cold boot, all four services (`lynx-display`, `lynx-media`,
`lynx-haptic`, `lynx-noobd`) returned without intervention. The boot retained
the pinned V50 kernel, init, and boot partition checksum. NRP/1 answered
`PING` and `HAPTIC_STATUS`; an 80 ms pulse logged motor state 1 then 0,
and the motor returned to off. Alpine health was ready with no reported issues.
The repeatable host check is `tools/verify_v50_noob_cold_boot.py`. Its successful
receipt is `logs/v50-noob-cold-boot-1793140010040084706/`; the first boot
and on-boot repair are recorded in `logs/v50-noob-cold-boot-1793139624662414307/`.
If haptic loading fails later, the
NRP endpoint can still answer image and sound calls, while haptic calls
return unavailable. Sound itself still needs its separate audio module
bootstrap after reboot.

No boot partition was changed. To disable these new services over Alpine
SSH: `rc-service lynx-noobd stop; rc-update del lynx-noobd default` and
`rc-service lynx-haptic stop; rc-update del lynx-haptic default`. The
working V50 boot image and Fastboot rollback path remain unchanged.

Receipts are under `logs/v50-haptic-driver-1793138362102004808/`,
`logs/v50-haptic-modern-1793138380797524818/`,
`logs/v50-haptic-firmware-1793138396197095231/`,
`logs/v50-haptic-pulse-1793138440799561677/`,
`logs/v50-noob-runtime-install-1793138639539905812/`,
`logs/v50-noob-vm-haptic-1793138650625836053/`,
`logs/v50-noob-vm-image-1793138657637029893/`, and
`logs/v50-noob-thread-image-1793138669169659521/`. The final NRP media
transport trial is `logs/v50-noob-media-transport-1793138905072214282/`, and
the VM-started thread trial is `logs/v50-noob-vm-thread-1793138921692639123/`.
