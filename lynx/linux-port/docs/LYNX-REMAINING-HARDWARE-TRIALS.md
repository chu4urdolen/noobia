# Lynx remaining hardware trials

Prepared 2026-10-28 for Lynx (OnePlus Nord 3 CPH2493, MT6983). This records
trial plans and observed results; **the remaining hardware is not yet enabled**.
The matching August 2023 CPH2493
stock package is under `linux-port/artifacts/stock-cph2493-August-eu-ota/`.
Lynx currently runs Alpine V50 with kernel
`5.10.149-android12-9-o-g311738fbb5a8`. The V50 `boot_a` image has SHA-256
`6168cd6288679a321a4d8bc41c7d3dde64a49d3cfe855b8e44542f3307fd5a59`.
See [LYNX-HARDWARE-STATUS.md](LYNX-HARDWARE-STATUS.md) for working hardware and
[LYNX-NOOB-RUNTIME.md](LYNX-NOOB-RUNTIME.md) for the existing NRP/1 interface.

## Trial order and shared rules

| Order | Stack | Why here | Current boundary |
| --- | --- | --- | --- |
| 1 | Microphone | ALSA capture nodes already exist; no new kernel module is needed | Exact input mixer route is unknown |
| 2 | Flashlight | Exact LM3642 driver identified; trial paused after unload hang | Binding worked, but Wi-Fi contact was lost while unloading the core |
| 3 | GNSS | Three matching modules, with a plausible native Linux device path to investigate | `connscp` and all GPS modules are absent; Android's GNSS userspace cannot be assumed to run on Alpine |
| 4 | Bluetooth | Matching module and firmware, but it shares connectivity infrastructure with working Wi-Fi | Both modules now load in RAM; vendor initialization remains |
| 5 | Camera | Several dependencies and vendor-specific userspace pieces | No `/dev/video*` or `/dev/media*` node; `mtk_ccu` and `v4l2-fwnode` are absent |

For **each** trial, first record `boot_id`, `uname -r`, the V50 boot hash,
`lynx-status --assert-ready`, `/proc/modules`, relevant `/dev` nodes, service
state, and a fresh SSH/NRP/1 response. Verify every staged module's SHA-256
and `modinfo -F vermagic` against the matching stock package. Stage modules
under `/run` first; change only RAM state until the device, userspace path,
power behavior, and rollback have been verified. Capture bounded kernel logs,
module state, nodes, health, and timing into a new `logs/` receipt for each
attempt. Keep the V50 boot image and the existing BusyBox rescue path intact.

Stop the trial if health reports an issue, temperature rises unexpectedly,
SSH drops, or a kernel probe behaves differently from the dependency plan.
Unload only trial modules with no consumers. Rebooting the unchanged V50 image
is the fallback for a RAM-only trial; a Wi-Fi failure may require physical
access to Lynx. Do not make any of these modules automatic at boot until a
clean cold boot has passed with SSH, display, battery monitoring, and NRP/1.

The local V50 image and its guarded boot procedure are identified in
`tools/lynx_boot_a_v50_trial.py`. Stock recovery is not a proven Android
restoration route; see [RECOVERY-AND-FIRST-BOOT.md](RECOVERY-AND-FIRST-BOOT.md).
No trial here calls for a partition flash.

After a hardware path works, expose it through Lynx's existing NRP/1 Noob
runtime at `192.168.100.107:4243` (currently restricted to Nexus). Preserve
the common VM and sequencer ABI. Sensors should offer a read-only status and
bounded sample with explicit units and freshness; actuators should offer
bounded SET, STATUS, and STOP calls plus an automatic OFF on service exit.
Require a successful direct NRP/1 call, a VM call where numeric output is
needed, a clean cold boot, and a local physical override before enabling an
automatic service. Assign IDs only when the actual driver behavior is known.

## 1. Microphone capture

**Known:** ALSA card `mt6983-mt6338` is active, and `/proc/asound/pcm` lists
`Capture_1` through `Capture_8`, among other capture PCMs. `/dev/snd/pcmC0D11c`
and related nodes exist. `arecord` is installed. The August ODM
`wifi-reference/odm-unpacked/etc/audio/test_path/common/mixer_paths.xml`
includes a main-microphone test path, but it references `Mic_Type_Mux_0`,
which is absent from Lynx's current `amixer -c 0 controls` output. Thus the
stock test path is **not** an executable Alpine route as written.

**Prepare:** Map the live `UL1`, ADC, PGA, source mux, and capture PCM controls
against the stock codec driver and device tree. Save *every* control value to
be changed. Identify a route that does not connect capture to playback or
activate a speaker. Keep sound output muted.
The reviewed primary sources are OnePlus's Nord 3
[MT6338 codec routes](https://github.com/OnePlusOSS/android_kernel_5.10_oneplus_mt6983/blob/oneplus/mt6983_t_13.1_oneplus_nord_3_5g/sound/soc/codecs/mt6338.c)
and [MT6983 capture front end](https://github.com/OnePlusOSS/android_kernel_5.10_oneplus_mt6983/blob/oneplus/mt6983_t_13.1_oneplus_nord_3_5g/sound/soc/mediatek/mt6983/mt6983-afe-pcm.c).

**Trial:** Apply the smallest reversible input route, capture at most one
second to `/run` (tmpfs), compute only format, frame count, peak/RMS and
whether samples respond to a known sound, then delete the PCM bytes. Restore
all saved mixer values in a `finally` path even if capture fails. Do not leave
a recording or a continuously listening service. Verify playback and the
audio service still work afterward.

**Success before NRP/1:** a repeatable nonzero signal with a known acoustic
stimulus, no speaker feedback, clean mixer restoration, and a healthy cold
boot. Only then add a bounded capture or level API to the Noob runtime.

**2026-10-28 first trial:** `tools/trial_v50_microphone.py` used the live
`ADC_L_Mux` and `UL1_CH1 ADDA_UL_CH1` controls, leaving both speakers muted.
One second at 48 kHz mono returned 48,000 samples (peak 3356, RMS 163.26),
and both changed controls restored exactly. The boot ID and health assertion
were unchanged. Kernel logs showed `ADDA Capture Enable`, `mt_mic_bias_0_event`,
and `mt_pga_l_event`, followed by their shutdown events. Receipt:
`logs/v50-microphone-trial-1793223350495266359/result.json`. A known
acoustic stimulus has **not yet** been compared with the ambient baseline,
so this is a working capture path, not final microphone validation. The
preceding receipt `logs/v50-microphone-trial-1793223334657382940/result.json`
records a parser rejection before any mixer change. A second one-second trial
applied a single 80 ms haptic pulse while capturing. Its early 250 ms RMS was
289.54, whereas the pulse window RMS was 4.35, with no clear response to the
known stimulus. This suggests the earlier peak may be a capture startup
transient; it does **not** confirm a working microphone. Mixer values and the
haptic OFF state were verified afterward. Receipt:
`logs/v50-microphone-trial-1793223666496784744/result.json`.

Two further one-second captures compared the same late window with and
without Lynx's existing quiet 700 Hz beep. Quiet late RMS was 3.9 and the
700 Hz amplitude was 0.01; during the beep they were 31.5 and 29.96.
No raw PCM was kept. Playback stopped, both speakers returned to mute,
both input controls were restored, and health passed. Receipts:
`logs/v50-microphone-trial-1793223805222328472/result.json` and
`logs/v50-microphone-trial-1793223812227403737/result.json`.
This established response to the beep. The user then confirmed an external
clap on the same boot: RMS × 100 rose from a quiet median of 499 to a maximum
of 5888 (11.8×), with peak 1164. No raw audio was saved; controls were
restored and Alpine health passed. Receipt:
`logs/v50-microphone-clap-1793305372427637018.json`.

## 2. Flashlight

**Known:** Matching vendor modules are `mtk_battery_oc_throttling.ko`
(SHA-256 `2285905a04532af8eaf2a04ad436eb14b4c8a7fc2bdbeaed3e5f647005b0cdf3`)
and `flashlight.ko`
(`58dbf6edb80115078739a3b008ef73a2bad734f9c4812a1f34b8e28ae36bb915`).
`flashlight` depends on `mtk_battery_oc_throttling` and the already loaded
`mtk_pbm`. Android expects `/dev/flashlight`; that node is absent now.
The packaged `flashlight.ko` advertises the generic
`mediatek,flashlight_core` alias, and its embedded device name is
`flashlights-none`. No separate `flashlights-*.ko` was found in this package,
but the exact V4L2 provider **is** present as `lm3642_22823.ko` (SHA-256
`96dc429c39453dbd0ba469069655bfafc43e329cc3216d912bb080e87b7bef67`).
Read-only inspection of Lynx's **active** device tree identifies the LED chip
as `i2c@11e02000/lm3642@63`, compatible
`mediatek,lm3642_22823`. It appears as I²C device `6-0063` but has no
bound driver in `/sys/bus/i2c/devices/6-0063/driver` before the trial. The stock `dtbo.img`
contains several phone variants with other LED chips, so its overlays alone
cannot identify Lynx's chip. The reviewed Nord 3 primary source is the
[LM3642-22823 V4L2 driver](https://github.com/OnePlusOSS/android_kernel_5.10_oneplus_mt6983/blob/oneplus/mt6983_t_13.1_oneplus_nord_3_5g/drivers/misc/mediatek/flashlight/v4l2/lm3642_22823.c).

**Prepare:** Review the exact driver's I²C register behavior, current table,
control ABI, and the active device-tree channel before writing any control.
Resolve the core unload hang first. Check whether module probe alone creates
the expected node, and whether it changes battery/thermal state. Use a
one-shot watchdog that explicitly turns the LED off even on an error.

**Trial (on hold):** Load the three verified modules in dependency order in RAM. Inspect
probe logs and device nodes first. If the ABI and current limit are known,
request a single dim pulse of at most 100 ms while someone can see Lynx, then
write OFF and verify OFF. Record the pulse duration, battery current, and
thermal readings. Do not expose raw brightness or indefinite ON through NRP/1.

**Success before service:** visual confirmation, verified OFF after timeout,
no health regression, and a successful reboot without the modules. A future
Noob native should mirror the bounded haptic pattern: SET, STATUS, STOP.

**2026-10-28 probe incident — further flashlight trials paused:** A RAM-only
trial loaded matching `mtk_battery_oc_throttling`, `flashlight`, then
`lm3642_22823` in that order, with health and Wi-Fi checks passing after
each load. The exact driver bound I²C `6-0063` and `/dev/flashlight` appeared.
No LED actuation was requested. `rmmod lm3642_22823` returned; the following
`rmmod flashlight` SSH call timed out, and Lynx then stopped answering SSH
and ping. The state of `flashlight` and `mtk_battery_oc_throttling` after
contact loss is unknown. The trial changed no boot partition and staged only
temporary files under `/run`. Receipt:
`logs/v50-flashlight-probe-1793224037686461488/result.json`. The script
`tools/trial_v50_flashlight_probe.py` is deliberately paused to prevent a
repeat until Lynx is recovered and the unload failure is understood. Do not
try an LED pulse or repeat the load/unload sequence as written.

**Recovery verified:** With Lynx connected in Fastboot, read-only getvars
reported `product: k6983v1_64`, `current-slot: a`, and `unlocked: yes`.
`fastboot reboot` succeeded without writing any partition (receipt:
`logs/v50-recovery-reboot-1793224979745750278/result.json`). BusyBox rescue
SSH returned first; its health check completed and handed off to Alpine.
Alpine SSH then returned with boot ID
`d7a150f8-b500-4256-ab8b-ee00120a0704`. The boot image on `/dev/sdc39`
still had the exact V50 SHA-256
`6168cd6288679a321a4d8bc41c7d3dde64a49d3cfe855b8e44542f3307fd5a59`.
`lynx-status --assert-ready` passed, all six control services were started,
and NRP/1 `PING` returned `PONG`. All three probe modules were absent and
the LM3642 I²C device was unbound. The incident did not require reflashing.
The cause of the core unload timeout remains unknown; the flashlight trial
stays paused.

**Offline source review:** `flashlight_exit()` calls
`platform_driver_unregister()`, whose remove path calls `fl_uninit()`.
`fl_uninit()` holds `fl_mutex` while invoking each registered device's
`flashlight_open`, `flashlight_set_driver`, `fl_enable`, and
`flashlight_release` operations. That path may block if a device operation
waits on hardware or another lock; there is no kernel trace proving which
call stalled here. The core also registers a battery overcurrent callback
at initialization, with no corresponding unregister call visible in this
source. Treat unloading the stock core as unsafe until the callback lifetime
and remove path are resolved. This is a source-level concern, not a confirmed
cause of Lynx's contact loss.

## 3. GNSS

**Known:** The stock Android init files `init.gps_scp.rc`, `init.gps_pwr.rc`,
and `init.gps_drv.rc` load `gps_scp.ko`, `gps_pwr.ko`, and a configured GPS
driver after `vendor.connsys.driver.ready=yes`. For this package the driver
candidate is `gps_drv_dl_v050.ko`. `gps_scp` depends on currently absent
`connscp` (which itself depends on loaded `scp`, `mtk_tinysys_ipi`, and
`connadp`); `gps_pwr` depends on loaded `connadp`; `gps_drv_dl_v050` depends
on loaded `conninfra`. All four files report the V50 kernel vermagic. The
Android package also contains `mnld`, `mtk_agpsd`, GNSS HAL binaries, and
AGPS configuration; these are Android components, not a ready Alpine daemon.

**Prepare:** Inspect the four kernel modules' init/probe and device-node ABI,
firmware requests, and clock/power behavior. Decide how native Linux will
receive measurements or NMEA and whether a userspace daemon is required.
Check that loading `connscp` will not reset the working Wi-Fi path. Arrange a
physical recovery window because connectivity is shared.

**Trial result, 2026-10-29:** All four matching modules loaded in RAM, one
at a time with timed reboot fallbacks. Wi-Fi, SSH, and Alpine health stayed
intact. The driver exposed `/dev/gpsdl0`, `/dev/gpsdl1`, `/dev/gps2scp`,
and `/dev/gps_pwr`; no receiver power or fix was attempted. Receipts are
listed in `LYNX-HARDWARE-TOOLS.md`. Next map the GPS device ABI and native
userspace flow, then verify outdoors against an independent position/time.
A node alone is not a GNSS fix.

## 4. Bluetooth

**Known:** `btif_drv.ko`
(`f81ec909db5e986b2a8e23fa1c34f3f3a027a07e2da5335fc3917b8bf9615d51`)
is absent. `bt_drv_6983.ko`
(`f6c99218edc8e903b2ccbaac7f9e7176cd11b6129350ff738fb64d1b9ade5296`)
depends on `btif_drv` plus loaded `conninfra`, `connfem`, `connadp`,
`oplus_project`, and `mtk_disp_notify` (recheck all at trial time). The stock
vendor firmware directory contains `soc7_0_ram_bt_*_hdr.bin`, `BT_FW.cfg`,
and related configuration. Android's `init.bt_drv.rc` loads the device driver
on a connectivity-ready property. Neither a Linux HCI device nor a usable
BlueZ path has been shown on Lynx.

**Prepare:** Inspect firmware lookup names from the driver and compare with
the matching stock files. Determine whether the driver exposes standard HCI,
a character device, or a vendor transport needing a native daemon. Preserve
current Wi-Fi/SSH and schedule the trial when physical recovery is available.

**Trial result, 2026-10-29:** Both exact modules loaded sequentially in RAM
under a timed reboot fallback. SSH, Wi-Fi, and Alpine health stayed intact.
The driver created `/dev/stpbt` but no HCI controller; its log reported a
failed flavor-bin lookup. Receipts:
`logs/v50-bluetooth-btif_drv-1793305632764445738/result.json` and
`logs/v50-bluetooth-bt_drv_6983-1793305649275022156/result.json`. Neither
module was unloaded because a prior unrelated driver unload hung. Next map
the stock vendor transport and firmware initialization before radio operation,
scanning, or pairing. A loaded module is not proof of Bluetooth operation.

## 5. Camera

**Known:** `imgsensor.ko` matches the V50 kernel but depends on
`imgsensor-glue`, `mtk_ccu`, `v4l2-fwnode`, `oplus_project`, `kernel_fb`,
`olc`, and `oplus_cam_event_report`. `mtk_ccu` itself needs `aee_aed`,
`mtk-icc-core`, `mrdump`, `mtk-smi`, and `mtk-smi-dbg`.
`camera_eeprom`, `camera_af_media`, `camera_pda`, and ISP modules are also
present in stock. `/dev/video*` and `/dev/media*` are absent on the observed
Alpine boot. This is a dependency inventory, not a complete camera load plan.

**Prepare:** Match the active device tree to camera sensor IDs, regulator and
clock requirements, EEPROM/calibration data, and the stock module load order.
Review the vendor userspace/HAL boundary and identify a native V4L2 or
libcamera path. The matching `lib3a.ccu` firmware files are present, but
their presence alone does not establish a usable native camera pipeline.

**Trial:** Bring up the minimum sensor/CCU stack in RAM with one module probe
at a time. Confirm sensor identity and read-only media topology before any
streaming. Then attempt a short, local, low-resolution frame capture to
tmpfs and discard it after inspecting metadata and an image checksum. Verify
the display, Wi-Fi, power, and thermal state after every stage. Do not add a
camera service or NRP/1 image stream before a clean cold boot and a privacy
indicator or local override are available.

## Other hardware backlog

NFC, fingerprint, headset jack, modem/cellular, USB data roles, and full
charging control still need their own inventory and trial plans. Existing
power management and battery monitoring should remain in place during every
experiment. None of the five trials above changes those controls.
