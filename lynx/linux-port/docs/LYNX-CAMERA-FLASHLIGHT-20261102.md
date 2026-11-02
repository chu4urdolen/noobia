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
At this early checkpoint, the V53 boot had **no flashlight modules loaded**.

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
and `logs/camera-recovery-*-20261102.txt`. The recovered boot has **none of
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

## Remote and VM checks on the current boot

On boot `18b2d497-dd35-4b11-a139-2dd388916208`, at 42% and charging,
`CALL CAMERA_STATUS` returned `interface_ready=0 validated=0 sensors_bound=0`.
`CALL FLASH_STATUS` returned `interface_ready=0 validated=0 driver_bound=0`,
and `CALL FLASH_STOP` reported `driver_present=0 off_verified=0`.
The matching read-only VM programs halted with register 0 equal to 0.
The `flashlight_stop` VM program also halted normally. A VM request for a
100 ms pulse entered `FAULT` with `flashlight_pulse_unavailable`, as did the
direct NRP/1 pulse call, because the driver is absent; no LED command was
sent. The VM was reset to `EMPTY` after the tests. The reproducible programs
are generated by `tools/build_hardware_vm_tests.py` under `programs/`.
At that checkpoint the physical remote-then-VM pulse sequence was pending. The camera has
only an inventory call; no frame capture native call exists yet.

## Later charging-aware trial on the same day

With Lynx charging and healthy at 43%, the RAM loader and pulse tool were
aligned with the existing 25%-while-charging service gate; the unplugged gate
remains 50%. The exact stock flashlight modules bound again. A direct NRP/1
`CALL FLASH_PULSE 100` returned `value=1 off_verified=1`; after the ten-second
cooldown, the finite `flashlight_pulse_100ms` VM program halted with
`regs=100,1,0,...`. A later `FLASH_STOP` returned `driver_present=1
off_verified=1`, and the sysfs torch state was `0 0 0 0`. Battery was 44%,
pack 25.2°C, maximum SoC zone 32.6°C, and Alpine health had no issues.
Noob later visually confirmed a separate 100 ms pulse. The gate update rollback is
`/usr/local/bin/lynx-flashlight-pulse.before-charging-aware-gate`; receipt:
`logs/flashlight-gate-1793604034550050199/result.json`. Module receipt:
`logs/flashlight-ram-1793604042763421283/result.json`.

The camera provider and sensor prefix then loaded on the same boot. Four
sensors bound automatically; `CALL CAMERA_STATUS` reported `sensors_bound=4`.
The previously successful `mtk_imgsys_v4l2` prefix and later prerequisites
also loaded with Alpine health passing. When `mtk-cam-isp` loaded, `insmod`
returned success but immediate health failed and SSH briefly timed out.
Nexus regained SSH, disarmed the trial watchdog, and saw a transient healthy
state. The kernel stream then captured repeated CPU 0 RCU stalls and another
transient Wi-Fi service failure. `CAMERA_STATUS` reported
`interface_ready=1 validated=0 sensors_bound=4`, which only means capture
nodes exist, not that a frame can be taken. No capture was requested.
Receipts: `logs/camera-ram-1793604153309797177/result.json`,
`logs/camera-pipeline-1793604201201629305/result.json`,
`logs/camera-pipeline-1793604247981444718/result.json`, and
`logs/camera-pipeline-1793604298438939297/result.json`.
The raw kernel stream is
`logs/kernel-trial-1793604146750082321/kernel.kmsg`. Repeated RCU stalls
began after the `mtk-cam-isp` bind on two separate boot trials; the precise
kernel cause remains unknown. No more ISP loads or frame requests should be
made until its probe path is understood. A normal reboot was requested to
clear the RAM-only camera stack; verify the resulting boot before further
hardware work.
The kernel recorder completed with 3,536,021 bytes and preserved repeated
RCU warnings; its result is
`logs/kernel-trial-1793604146750082321/result.json`. At the 2026-11-02
09:32 Sofia check, Lynx had not returned on Wi-Fi or Bluetooth and was not
visible on Nexus USB. Her physical screen state is pending confirmation.
She later appeared on Nexus USB in Fastboot as product `k6983v1_64`.
`fastboot reboot` returned OK without a partition write.
As of 09:37 Sofia, neither Alpine SSH nor NRP/1 had returned and USB Fastboot
was no longer enumerated. The screen state still requires a physical report;
do not issue another reboot or attempt a camera load without one.
Noob later reported Lynx's normal portrait. Nexus then verified Alpine 3.24.2,
NRP/1 `PING`, healthy Wi-Fi and SSH, and boot ID
`232927fb-06d8-4cda-a7ac-5000a67856d9`. The camera and flashlight RAM
modules had cleared. At 51% and normal temperature, the exact flashlight
modules were loaded in RAM again. A direct 100 ms NRP/1 pulse returned
`off_verified=1`; after cooldown the finite VM pulse halted with
`regs=100,1,0,...`. `FLASH_STOP` and the sysfs channel verified OFF, Alpine
health had no issues, and the VM was reset to `EMPTY`. Noob was not present
for these two newly announced pulses. No camera module was loaded
on this recovered boot.
Noob then watched a further 100 ms NRP/1 pulse and confirmed seeing the rear
LED flash. The command returned `off_verified=1`. This validates the
flashlight's physical response, although `FLASH_STATUS` still returns
`validated=0` until its backend is updated and deployed. Lynx has not been
changed since Noob requested offline-only camera planning.

After offline planning, the local hardware backend was updated with the
visual confirmation record and deployed to Alpine userspace. The first
installation attempt rolled back because NRP/1 was queried before its daemon
had restarted; receipt:
`logs/flashlight-visual-install-1793635410402565320/result.json`.
The retry waited for readiness and passed local inventory, NRP/1
`CALL FLASH_STATUS` (`value=1`, `validated=1`, `driver_bound=1`), and the
Alpine health assertion on the same boot. Receipt:
`logs/flashlight-visual-install-1793635454301342988/result.json`.
This change loaded no module, actuated no LED, and wrote no boot partition.
The staged flashlight boot service remains disabled pending a monitored
cold boot, because the driver should not be unloaded to reset a trial.

Source boundary: the checked-out OnePlusOSS MT6983 modules branch in
`sources/oneplus-mt6983-modules/` contains connectivity, GPU, and related
modules but no `mtkcam` tree. The stock `mtk-cam-isp.ko` is therefore the
exact binary for this trial, while its matching source is not in that
checkout. Do not treat another device's camera driver source as an exact
match. The next camera step is source matching and analysis of the CPU 0
stall before any further live ISP load.
Read-only CPU 0 inspection on the recovered boot found `psci_idle`: WFI is
enabled, while `clusteroff_l`, `mcusysoff`, `system_mem`, `system_pll`,
`system_bus`, and `s2idle` are already disabled. The RCU trace's
`cpuidle_enter_state` frame therefore does not identify a deeper idle state
that can simply be turned off. This is an observation, not a diagnosis.
In the captured stream, `mtk_cam_master_bind success` precedes an `init_module`
return after 6,018,312 microseconds. The first CPU 0 RCU stall report follows
about 15 seconds later, with a grace-period thread reportedly starved for
4,922 jiffies. Another stall report follows roughly 63 seconds later. The
module's successful return and the later stalls are both established; their
causal path is not. The exact ISP module reported the matching
`5.10.149-android12-9-o-g311738fbb5a8` vermagic and the expected camera,
CCU, memory, and V4L2 dependencies.
