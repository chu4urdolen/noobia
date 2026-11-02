# Lynx camera and flashlight checkpoint, 2026-11-02

This is the current boundary for the CPH2493 V53 Alpine boot. These trials
changed RAM modules and Alpine userspace only. They did not write any boot or
recovery partition. The V53 `boot_a` SHA-256 is
`c047455271828cf9bfa90984eea121d8ede8754f6297fc06f33f1e99fb23c75e`.
Keep the V50 rollback and BusyBox rescue images available.

## Flashlight

The exact August stock `mtk_battery_oc_throttling`, `flashlight`, and
`lm3642_22823` modules loaded in RAM. LM3642 bound at I2C `6-0063` and
exposed `/dev/flashlight` and one `flash@0` channel. A 100 ms torch request
returned successfully and the sysfs state was OFF afterward. This proves the
driver command path; no visual confirmation of light was recorded. Evidence:
`logs/flashlight-ram-1793565934085949404/result.json` and
`logs/flashlight-pulse-1793566008203365862/result.json`.

The same bounded request is available through local
`lynx_flashlight_pulse.sh` and NRP/1 `FLASH_PULSE` (396), and OFF through
`lynx_flashlight_stop.sh` and `FLASH_STOP` (397). `FLASH_PULSE` accepts only
20–100 ms, requires at least 50% battery, checks pack and SoC temperature,
requires the bound LM3642 and exact device-tree channel, limits repeated
pulses to one per ten seconds, and has a separate delayed OFF child. Neither
interface offers continuous ON. A remote pulse returned `off_verified=1`.
The stop call explicitly reports `off_verified=0` when no driver is present.
The current V53 boot has **no flashlight modules loaded**.

The hash-checked `lynx-flashlight` OpenRC boot service and matching modules
are staged on Alpine but **disabled and not started**. Stage receipt:
`logs/flashlight-service-stage-1793602446886966899/result.json`.
Do not unload the stock LM3642 driver followed by its core: that sequence
previously lost SSH, and source review found a plausible stale callback in
LM3642's remove path. Use a normal reboot to clear RAM modules if needed.
Before enabling the service, obtain visual confirmation on a healthy,
adequately charged boot and repeat a monitored cold boot.

## Camera

The stock device tree describes four sensor addresses. On the trial boot,
after loading the matching CCU clock provider, `mtk_ccu`, and the
`multi_regulator` driver, all four sensor nodes bound: IMX890 at `8-0036`,
IMX355 at `2-001a`, S5K3P9SP at `9-0010`, and GC02M1 at `9-003d`.
The regulator was discovered at I2C `3-002f` and found its chip at `0x35`.
`camera_eeprom` and two platform modules also loaded. Evidence:
`logs/camera-dt-1793566429579083902.json` and the four
`logs/camera-bind-*/result.json` receipts.

The `mtk_imgsys_v4l2` dependency prefix loaded in RAM and created
`/dev/media0` plus many video nodes. Their names were `MTK-ISP-DIP-V4L2`
processing nodes; this did **not** establish a camera capture stream.
Evidence: `logs/camera-pipeline-1793566776476890007/result.json` and
`logs/camera-media-names-20261101.txt`.

Loading the later prefix through `mtk-cam-isp` returned from `insmod`, but
the immediate Alpine health assertion failed because `lynx-battery-reserve`
was no longer running. The kernel also emitted an RCU stall warning. The
trial stopped without requesting a frame or unloading any modules. Lynx
subsequently rebooted and recovered her normal services. The reboot cause
is unknown. Evidence: `logs/camera-pipeline-1793566914812741706/result.json`
and `logs/camera-recovery-*-20261102.txt`. The current boot has **none of
these RAM-only camera modules loaded**. There is no validated camera capture,
image, or camera action in the Noob interface. `CAMERA_STATUS` (394) and the
local `lynx_camera.sh` report readiness and bound sensors without claiming
capture. The display calls processing nodes `ISP NODES`, not capture nodes.

## Next trial boundary

On 2026-11-02 Lynx was healthy and charging at 38%; the 50% driver-trial
gate therefore prevented another live load. Before a camera retry, capture
the kernel ring buffer continuously to Nexus and inspect the `mtk-cam-isp`
probe and service failure. The current pstore is empty, while existing
persistent kernel logs contain only early boot. Keep the health assertion and
timed reboot fallback. Do not expose capture through NRP/1 or enable camera
modules at boot until a frame can be acquired without losing services.
