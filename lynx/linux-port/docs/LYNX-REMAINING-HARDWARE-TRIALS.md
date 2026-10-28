# Lynx remaining hardware trials

Prepared 2026-10-28 for Lynx (OnePlus Nord 3 CPH2493, MT6983). **These are
plans, not completed hardware tests.** The matching August 2023 CPH2493
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
| 2 | Flashlight | Two matching modules; short, bounded actuation can be tested once the ioctl/sysfs ABI is reviewed | `mtk_battery_oc_throttling` and `flashlight` are absent |
| 3 | GNSS | Three matching modules, with a plausible native Linux device path to investigate | `connscp` and all GPS modules are absent; Android's GNSS userspace cannot be assumed to run on Alpine |
| 4 | Bluetooth | Matching module and firmware, but it shares connectivity infrastructure with working Wi-Fi | `btif_drv` is absent; preserve SSH before touching this stack |
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

**Trial:** Apply the smallest reversible input route, capture at most one
second to `/run` (tmpfs), compute only format, frame count, peak/RMS and
whether samples respond to a known sound, then delete the PCM bytes. Restore
all saved mixer values in a `finally` path even if capture fails. Do not leave
a recording or a continuously listening service. Verify playback and the
audio service still work afterward.

**Success before NRP/1:** a repeatable nonzero signal with a known acoustic
stimulus, no speaker feedback, clean mixer restoration, and a healthy cold
boot. Only then add a bounded capture or level API to the Noob runtime.

## 2. Flashlight

**Known:** Matching vendor modules are `mtk_battery_oc_throttling.ko`
(SHA-256 `2285905a04532af8eaf2a04ad436eb14b4c8a7fc2bdbeaed3e5f647005b0cdf3`)
and `flashlight.ko`
(`58dbf6edb80115078739a3b008ef73a2bad734f9c4812a1f34b8e28ae36bb915`).
`flashlight` depends on `mtk_battery_oc_throttling` and the already loaded
`mtk_pbm`. Android expects `/dev/flashlight`; that node is absent now.

**Prepare:** Review the driver's control ABI and the device-tree flashlight
channels before writing any control. Check whether module probe alone creates
the expected node, and whether it changes battery/thermal state. Use a
one-shot watchdog that explicitly turns the LED off even on an error.

**Trial:** Load the two verified modules in dependency order in RAM. Inspect
probe logs and device nodes first. If the ABI and current limit are known,
request a single dim pulse of at most 100 ms while someone can see Lynx, then
write OFF and verify OFF. Record the pulse duration, battery current, and
thermal readings. Do not expose raw brightness or indefinite ON through NRP/1.

**Success before service:** visual confirmation, verified OFF after timeout,
no health regression, and a successful reboot without the modules. A future
Noob native should mirror the bounded haptic pattern: SET, STATUS, STOP.

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

**Trial:** In RAM, one module at a time in dependency order:
`connscp`, `gps_scp`, `gps_pwr`, `gps_drv_dl_v050`. After each load, capture
logs and check Wi-Fi/SSH, thermals, device nodes, and idle power. Stop before
requesting a fix if a module destabilizes connectivity. A first valid fix
requires an outdoor test and an independently checked position/time; module
load or a device node alone is not GNSS success.

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

**Trial:** Stage exact modules and firmware, then load `btif_drv` followed by
`bt_drv_6983` in RAM. Inspect probe logs, device nodes, and any HCI interface
without pairing or advertising first. Keep checking SSH and battery current.
Only after a stable interface exists should a short local scan and a known
consenting-device pairing be attempted. A loaded module is not proof of
Bluetooth operation.

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
