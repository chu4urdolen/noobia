# Lynx hardware and Noob runtime status

Lynx is a OnePlus Nord 3 CPH2493, MT6983, running native Alpine on the V50
boot image. The runtime speaks the Iris-compatible NRP/1 protocol at
`192.168.100.107:4243`, currently accepting Nexus (`192.168.100.106`).
No boot partition changed during the hardware work described here.

| Hardware | Current Linux evidence | Noob interface |
| --- | --- | --- |
| Wi-Fi, storage, SSH | Alpine boots from `/dev/sdc85`, joins Noobia, opens SSH | NRP/1 transport; SSH remains for maintenance |
| Display and touch | `lynx-display` runs; `/dev/dri/card0`, `/dev/input/event0` and `touchpanel` exist | Pose and animation calls 310–319; touch events are not exposed yet |
| Vibration | AW86907 driver and firmware load on cold boot | Bounded haptic calls 300–302 |
| Sound | MT6983 ALSA card, corrected MT6338 codec, TFA98xx firmware, controlled beep | Sound calls 340–346; audio readiness call 355 |
| Battery | Gauge at I²C `7-0055`, validated type 42495 and error flags | Read-only calls 350–353 |
| SoC thermal | `soc_max` thermal zone | Read-only call 354 |
| Accelerometer | `hf_manager` and `sensorhub` register Bosch `bmi2xy acc`; 16 bounded live events recorded | Raw vector and axis calls 360–364 |
| Gyroscope | Bosch `bmi2xy gyro`; 16 bounded live events recorded | Raw vector and axis calls 365–369 |
| Proximity and rear light | AMS `tcs3701 ps` and `tcs3408 als` return bounded events; stationary raw values need a physical response test | Status and raw calls 370–373 |
| Magnetometer | AKM09918 returns 16 bounded live events | Raw vector and axis calls 374–378 |
| Charging | MT6375 charger and battery reserve service | Monitored locally; remote charging controls are not exposed |

The new numeric calls return one value per NRP/1 `CALL`, so they work from
the common Noob VM as well as a direct client. Units are explicit in the
reply: percent, millidegrees Celsius, signed milliamps, and millivolts.
Invalid gauge/error readings return `NATIVE_ERROR` rather than a plausible
number. `AUDIO_READY` checks the ALSA card and loaded TFA98xx firmware.

The stock module bundle contains `bt_drv_6983.ko`, `gps_drv_dl_v050.ko`, `nfc_i2c.ko`,
`imgsensor.ko`, `flashlight.ko`, and video codec modules. Their presence in
firmware does not establish working hardware. On the observed Alpine boot,
touch and power ADC nodes existed, but camera/video and Bluetooth device
nodes were not established. The sensorhub's `/proc/hf_manager` registered a
Bosch accelerometer and gyroscope, magnetometer, proximity, ambient light,
and other logical sensors. Accelerometer, gyroscope, magnetometer, proximity,
and rear light samples have been read. Values are still raw driver values;
physical units and optical response remain unverified.
The next driver trials should proceed one stack
at a time, with boot identity checks, module dependency review, a read-only
probe first, and rollback over SSH.

The audio service stores the exact 75-module dependency plan and corrected
codec under `/var/lib/lynx-audio/v1`, verifies every module hash, and loads
only missing modules. It requires at least 25% battery while charging (or
50% otherwise), battery below 35°C, and `soc_max` below 45°C. It mutes both
speakers before loading the matching TFA98xx firmware. Disable it with
`rc-service lynx-audio stop; rc-update del lynx-audio default` over Alpine SSH.
The V50 boot image and BusyBox rescue path remain available.
The clean cold boot receipt for automatic audio and sensorhub readiness is
`logs/v50-audio-cold-boot-1793199862813330816/result.json`.

`lynx-sensorhub` stores and verifies the two matching August stock modules
under `/var/lib/lynx-sensors/v1`. It depends on `lynx-audio` because SCP is
currently provided by that stack, and waits for the registered accelerometer
before reporting ready. It does not enable any sensor at boot. The first
RAM-only module receipt is `logs/v50-sensorhub-module-trial-1793199405514115242/`;
the bounded accelerometer read is `logs/v50-hf-accelerometer-1793199639429564957/`.
That read returned 16 samples. Bounded gyroscope, optical, and magnetometer
receipts are `logs/v50-hf-gyroscope-1793200181549329489/`,
`logs/v50-hf-optical-1793200278234671051/`, and
`logs/v50-hf-magnetometer-1793200364041072751/`. The helper explicitly
disables each sensor after sampling, and `/proc/hf_manager` shows an empty
active list. A subsequent clean boot started audio and sensorhub automatically,
with NRP/1 accelerometer readings and the health assertion passing.
