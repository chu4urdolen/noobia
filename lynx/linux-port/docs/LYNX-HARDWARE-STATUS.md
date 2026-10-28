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
| Charging | MT6375 charger and battery reserve service | Monitored locally; remote charging controls are not exposed |

The new numeric calls return one value per NRP/1 `CALL`, so they work from
the common Noob VM as well as a direct client. Units are explicit in the
reply: percent, millidegrees Celsius, signed milliamps, and millivolts.
Invalid gauge/error readings return `NATIVE_ERROR` rather than a plausible
number. `AUDIO_READY` checks the ALSA card and loaded TFA98xx firmware.

The stock module bundle contains `sensorhub.ko` (depends on SCP and
`hf_manager`), `bt_drv_6983.ko`, `gps_drv_dl_v050.ko`, `nfc_i2c.ko`,
`imgsensor.ko`, `flashlight.ko`, and video codec modules. Their presence in
firmware does not establish working hardware. On the observed Alpine boot,
touch and power ADC nodes existed, but camera/video and Bluetooth device
nodes were not established. The next driver trials should proceed one stack
at a time, with boot identity checks, module dependency review, a read-only
probe first, and rollback over SSH. Motion sensors likely depend on the
sensorhub path; do not assume direct IIO accelerometer or gyroscope nodes.

The audio service stores the exact 75-module dependency plan and corrected
codec under `/var/lib/lynx-audio/v1`, verifies every module hash, and loads
only missing modules. It requires at least 25% battery while charging (or
50% otherwise), battery below 35°C, and `soc_max` below 45°C. It mutes both
speakers before loading the matching TFA98xx firmware. Disable it with
`rc-service lynx-audio stop; rc-update del lynx-audio default` over Alpine SSH.
The V50 boot image and BusyBox rescue path remain available.
The clean cold boot receipt for automatic audio readiness is
`logs/v50-audio-cold-boot-1793198926121333822/result.json`.
