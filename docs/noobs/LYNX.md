# Lynx code map

**Current conversation handoff:** [Lynx handoff](../../lynx/linux-port/docs/CURRENT-HANDOFF.md).

Lynx is the OnePlus Nord 3 CPH2493 / MT6983. At the 2026-11-20
checkpoint, trial V53 Alpine is healthy on a new boot, charging at 22%, with
Wi-Fi and SSH. V53 waits for shared-radio calibration before requesting
Wi-Fi. Authenticated BLE trials and a 15-minute same-boot Bluetooth hold
passed; automatic Bluetooth startup and long-uptime reboot reliability remain
unverified. RAM-only V53 GNSS trials produced 108 checksum-valid NMEA
sentences but no position fix. The exact V50 BusyBox rescue image and
Fastboot rollback remain available. Her observed Noobia address is
`192.168.100.107`. Check live identity and health before a hardware trial.
The persistent Alpine root uses `Europe/Sofia`; its local time was verified
after the latest V50 restoration.

**Service compatibility rule:** normal Lynx services must check the kernel,
required modules, hardware interfaces, firmware, and health they actually
need. Do not pin a normal service to a whole `boot_a` image SHA: that caused
the display to stay black after V53 booted successfully. Keep exact image
hashes in builders, flashing/rollback tools, and bounded diagnostic trials.

| Need | Source and notes |
| --- | --- |
| Current hardware evidence | [`LYNX-HARDWARE-STATUS.md`](../../lynx/linux-port/docs/LYNX-HARDWARE-STATUS.md) |
| Read-only cellular inventory and SIM gate | [`LYNX-CELLULAR-INVENTORY-20261118.md`](../../lynx/linux-port/docs/LYNX-CELLULAR-INVENTORY-20261118.md) |
| Why Lynx powers off | [Poweroff audit](../../lynx/linux-port/docs/LYNX-POWER-SHUTDOWNS-20261118.md); active 20% reserve and older charging policy |
| Delayed audio and sensor startup | [Sensor retry](../../lynx/linux-port/docs/LYNX-SENSOR-RETRY-20261118.md); low-charge cold boot still unverified |
| Kernel-to-agent gate and flash decision | [`LYNX-KERNEL-TO-AGENT-GATE.md`](../../lynx/linux-port/docs/LYNX-KERNEL-TO-AGENT-GATE.md) |
| Camera and flashlight trial checkpoint | [`LYNX-CAMERA-FLASHLIGHT-20261102.md`](../../lynx/linux-port/docs/LYNX-CAMERA-FLASHLIGHT-20261102.md) |
| Rear flash and color sensor identification | [`LYNX-REAR-LIGHT-AND-COLOR-SENSOR.md`](../../lynx/linux-port/docs/LYNX-REAR-LIGHT-AND-COLOR-SENSOR.md) |
| Four-camera native Linux plan | [`LYNX-CAMERA-PORT-PLAN.md`](../../lynx/linux-port/docs/LYNX-CAMERA-PORT-PLAN.md) |
| Camera ISP and capture trials | `lynx/tools/prepare_camera_camsv.py` read-only status and attended RAM preparation; `trial_camera_camsv_frame.py` guarded frame capture. GC02M1 raw capture, exposure/gain response, and RGGB phase validated; modules are RAM-only |
| Shared Bluetooth/GNSS calibration and V52/V53 trials | [`LYNX-CONNECTIVITY-PRECAL.md`](../../lynx/linux-port/docs/LYNX-CONNECTIVITY-PRECAL.md) |
| Bluetooth NRP/1 service boundary | [`LYNX-BLUETOOTH-NRP.md`](../../lynx/linux-port/docs/LYNX-BLUETOOTH-NRP.md) |
| Trial sequence and known hazards | [`LYNX-REMAINING-HARDWARE-TRIALS.md`](../../lynx/linux-port/docs/LYNX-REMAINING-HARDWARE-TRIALS.md) |
| NRP/1 server and native calls | `lynx/tools/lynx_noob_runtime.py`; [`LYNX-NOOB-RUNTIME.md`](../../lynx/linux-port/docs/LYNX-NOOB-RUNTIME.md) |
| Nexus remote client | `lynx/tools/lynx_noobctl.py` |
| Nexus presence monitor | [`LYNX-PRESENCE.md`](../../lynx/linux-port/docs/LYNX-PRESENCE.md); `lynx/tools/lynx_presence.py` |
| Local hardware backend and agent wrappers | `lynx/tools/lynx_hardware.py`, `lynx/tools/lynx_microphone_level.py`, `lynx/tools/local_calls/`; [tool contract](../../lynx/linux-port/docs/LYNX-HARDWARE-TOOLS.md) |
| Optical and proximity local tools | `lynx/tools/lynx_light_read.py`, `lynx/tools/lynx_proximity_read.py`, and their `local_calls/` wrappers; [controlled rear light trial](../../lynx/linux-port/docs/LYNX-REAR-LIGHT-AND-COLOR-SENSOR.md) |
| Magnetometer local tool | `lynx/tools/lynx_magnetometer_read.py` and `local_calls/lynx_magnetometer_read.*`; raw bounded vector, [hardware status](../../lynx/linux-port/docs/LYNX-HARDWARE-STATUS.md) |
| Motion local tool | `lynx/tools/lynx_motion_read.py` and `local_calls/lynx_motion_read.*`; bounded accelerometer or gyroscope vector |
| Display, keyboard, scrolling | `lynx/tools/lynx_drm_dmabuf_pattern.c`; [`LYNX-CONSOLE.md`](../../lynx/linux-port/docs/LYNX-CONSOLE.md) |
| Media control | `lynx/tools/lynx_media.py`; [`LYNX-MEDIA-CONTROL.md`](../../lynx/linux-port/docs/LYNX-MEDIA-CONTROL.md) |
| Microphone capture experiment | `lynx/tools/trial_v50_microphone.py`; external clap validated on V50 |
| Flashlight control and safe OFF | `lynx/tools/lynx_flashlight_pulse.py`, `lynx/tools/local_calls/`; visual response validated, boot service staged but disabled |
| Boot restoration | [`RECOVERY-AND-FIRST-BOOT.md`](../../lynx/linux-port/docs/RECOVERY-AND-FIRST-BOOT.md) and `lynx/tools/lynx_boot_a_v50_trial.py` |
| V50 Alpine to Fastboot and retained logs | `lynx/tools/return_fastboot_from_alpine.py`, `lynx/tools/capture_v50_expdb_prefix.py`; [Bluetooth boot evidence](../../lynx/linux-port/docs/LYNX-BLUETOOTH-NRP.md) |
| Deferred cleanup after a stable build | [`LYNX-CLEANUP-WHEN-STABLE.md`](../../lynx/linux-port/docs/LYNX-CLEANUP-WHEN-STABLE.md) |
| One-shot OpenAI inference test | `lynx/tools/lynx_inference_probe.py`, `lynx/tools/trial_v50_openai_inference.py`; [inference notes](../../lynx/linux-port/docs/LYNX-INFERENCE.md) |
| Local agent, supervised queue, private health summary, and NRP control | `lynx/tools/agent/`, `lynx/tools/lynx_agent_remote.py`; [agent status and gates](../../lynx/linux-port/docs/LYNX-AGENT.md) |
| Read-only UFS and Alpine file backup | `lynx/tools/backup_full_ufs.py`, `lynx/tools/backup_alpine_files.py`; [backup status, safety-guard incident, and restoration limits](../../lynx/linux-port/docs/LYNX-FULL-UFS-BACKUP-20261106.md) |
| Alpine root expansion | `lynx/tools/grow_alpine_root.py`, `lynx/tools/audit_alpine_root_growth.py`; [current readiness and battery gate](../../lynx/linux-port/docs/ROOT-GROW-READINESS-20261108.md) |

GPS, Bluetooth, and camera have matching stock modules. V52's shared-radio
calibration succeeded, Bluetooth answered HCI commands, and Nexus connected
to Lynx using her factory Bluetooth address. A bounded PTY bridge now also
exposes a standard `hci0` to BlueZ, and a guarded trial powered it on; BlueZ
is installed but not started automatically. A separate guarded trial completed
an unpaired NRP/1 `PING`/`PONG` over a temporary GATT service using the same
runtime as Wi-Fi. GNSS now emits NMEA through a
native listener; the latest GGA reported fix quality 0 and no position has yet
been measured. Microphone
level capture works locally and over NRP/1 for one second; an external clap
validated its acoustic response. Flashlight driver binding
was observed, then unloading
the core lost SSH; do not repeat that sequence until its failure is resolved.
On a later V53 trial boot the flashlight driver bound and accepted a bounded
100 ms command, with OFF verified and rear LED flash visually confirmed by Noob.
`FLASH_STATUS` now reports `validated=1` while the driver is loaded. Four camera
sensors also bound after their clock and regulator providers were loaded.
A monitored V53 trial found the stock `mtk-cam-isp` causes a YUV-B interrupt
storm. A patched ISP gate passed a
RAM-only load with zero YUV-B IRQs. A second patch explicitly powers the
CAMSV sensor. With the matching full CCU firmware staged in RAM, the GC02M1
macro camera now completes a 1600×1200 DMA-BUF raw frame, with sensor I²C,
CAMSV IRQ, and stream cleanup observed. A brighter-scene frame has visible
geometry but remains underexposed. The RGGB phase is confirmed by a red-cable
target; physical lens identity remains unverified. Request-scoped exposure and
gain control produced
a measured brightness response; see
[`CAMERA-EXPOSURE-20261104.md`](../../lynx/linux-port/docs/CAMERA-EXPOSURE-20261104.md).
The IMX355 wide route and 3264×2448 capture format have also passed guarded
RAM-only tests. Its first complete raw frame is nearly black, so scene and
lens validation are still pending; the macro route and original capture
format were restored. See the camera plan for receipts.
An attended bright-scene trial on 2026-11-06 produced a recognizable wide
image and a 201× rise in positive raw signal versus the dark frame. The
macro route and original format were again restored; see the camera plan.
A later sensor-control enumeration with
`v4l2-ctl --list-ctrls-menus` caused a vendor kernel Oops; do not repeat it.
Pstore identified the exact ioctl path, and V53 Alpine has been restored and
verified. See the camera plan and
[`CAMERA-CTRL-CRASH-20261104.md`](../../lynx/linux-port/docs/CAMERA-CTRL-CRASH-20261104.md)
for receipts and recovery steps.
The V50 boot image and recovery path must stay available.
The Status page now reports live Bluetooth service readiness; see
[`LYNX-SCREEN-NAVIGATION.md`](../../lynx/linux-port/docs/LYNX-SCREEN-NAVIGATION.md).
It also distinguishes a detected flashlight chip from an active driver and
checks GPS and camera interfaces. Source review found a plausible stale
callback path in the stock LM3642 unload sequence; see the flashlight trial
notes before another module probe.
