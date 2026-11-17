# Lynx four-camera native Linux plan

Prepared on 2026-11-02. Keep V53 boot, Alpine SSH, the portrait, and the
V50/BusyBox recovery path intact. Do not load the stock ISP module again:
the monitored trial found a severe YUV-B interrupt storm before any capture.

## Hardware map to verify

The August CPH2493 stock device tree and `CameraHWConfiguration.config` point
to four physically distinct sensors. The factory configuration names rear
main, front, rear wide, and rear macro camera roles. The role assignment below
is the best current mapping, not yet validated with images from each lens.

| Role | Sensor | I2C device | Stock sensor slot |
| --- | --- | --- | --- |
| Rear main | IMX890 | `8-0036` | 0 |
| Front | S5K3P9SP | `9-0010` | 1 |
| Rear wide | IMX355 | `2-001a` | 2 |
| Rear macro | GC02M1 | `9-003d` | 4 |

Source artifacts:
`linux-port/artifacts/stock-cph2493-August-eu-ota/wifi-reference/odm-unpacked/etc/camera/CameraHWConfiguration.config`
and `logs/camera-dt-1793566429579083902.json`. The physical role of each
sensor must be checked by covering one lens at a time once capture works.

## Gate 1: explain the ISP stall

**Gate failed with a concrete cause on 2026-11-02.** The targeted stock ISP
trial at `logs/camera-isp-irq-trial-1793638524269566924/result.json` loaded
successfully, but Linux IRQ 247 (`1a090000.cam_yuv_b`, GIC SPI 495) fired on
CPU 0 without a camera stream. The 80-second IRQ monitor recorded 7,427,727
at sample 5, 32,768,812 at sample 20, and a final live snapshot reached
68,127,138. Other camera IRQs remained at zero. SSH became intermittent; a
brief battery-reserve and Wi-Fi service health error appeared, then cleared.
The kernel stream through the monitor window contained no RCU stall, so the
earlier RCU warnings may have followed this sustained IRQ load. That causal
relationship remains a hypothesis, while the IRQ storm itself is measured.
The final snapshot is `logs/camera-isp-irq-trial-1793638524269566924/irq-final.stdout`;
the full time series is
`logs/camera-health-window-1793638530148096643/`. A forced reboot request
lost SSH, then Noob brought Lynx to Fastboot. Nexus verified product
`k6983v1_64`, slot A, unlocked, and issued `fastboot reboot` to unchanged V53.
The first reboot stayed black; a second Fastboot reboot reached BusyBox SSH
at uptime 52 seconds and completed its delayed Alpine PID 1 handoff after
uptime 219 seconds. Alpine SSH and health then passed on boot ID
`83967af8-f818-4472-87df-6fa04eb0af78`, with the ISP absent. This was
a slow V53 boot, not a failed Alpine image.

The matching OnePlus source `cam/mtk_cam-raw.c` registers YUV IRQs in
`mtk_yuv_of_probe()` with `devm_request_irq()` and does not disable them at
probe. `mtk_irq_yuv()` reads four YUV interrupt status registers and returns
`IRQ_HANDLED`. A powered-off or uncleared YUV-B line could repeatedly invoke
that handler. This is an inference from source and the observed IRQ count;
the actual register state is not captured. Repair requires understanding
YUV-B power/reset/IRQ acknowledgement and either a reviewed driver fix or a
safe early IRQ disable before another live ISP load. The targeted trial
launcher now refuses execution until that repair is reviewed.

An experimental repair patch now exists at
`linux-port/patches/camera-yuv-irq/0001-gate-yuv-irq-on-runtime-power.patch`.
It disables the YUV IRQ after request, disables it during runtime suspend,
and enables it after runtime resume clocks are prepared and status registers
are read. The matching source compiled with the pinned Android Clang 12
toolchain into `artifacts/camera-yuv-irq-build/cam/mtk-cam-isp.ko`.
Its vermagic matches the stock module; all 322 imported symbol CRCs match
the stock ISP exactly. It has **not been loaded on Lynx**. The first guarded
trial refused because its pinned output hash was stale after a rebuild; the
second stopped at the SSH boot identity check. There is no evidence yet that
the patch fixes YUV-B or allows capture. Review the runtime PM state and
record exact IRQ counts before any further load or image packaging.

The stock clock, regulator, CCU, EEPROM, four sensors, and image-processing
modules have loaded in RAM. `mtk-cam-isp` binds and creates capture-class
nodes, but two separate trials then produced CPU 0 RCU stalls and transient
service loss. The second trace is
`logs/kernel-trial-1793604146750082321/kernel.kmsg`; the trial receipt is
`logs/camera-pipeline-1793604298438939297/result.json`. The ISP module's
successful return is followed about 15 seconds later by the first stall.
CPU 0 has only WFI enabled; its deeper idle states are already disabled.
This is an association, not yet a proven kernel cause.

The official Nord 3 13.1 kernel tree at
`OnePlusOSS/android_kernel_5.10_oneplus_mt6983`, commit
`81ec42ad5e803be0cba619f9f7bb298db7d33d7b`, contains the ISP7.1 camera
source under `drivers/media/platform/mtk-isp/camsys/isp7_1/cam/` and the CCD
remoteproc driver under `drivers/remoteproc/mtk_ccd.c`. A checksum manifest
and fetch/verify tool live in `sources/oneplus-nord3-mtkcam/SOURCE.json` and
`tools/fetch_nord3_camera_source.py`. These source files match the stock
module's diagnostic strings and Kbuild module name; bit-for-bit binary
identity has not been established. Review probe, IRQ, clock, media, and
firmware paths there before another live trial. Do not hide the stall by
loosening health assertions or repeating the same load.

In that source, RAW IRQs are requested and then disabled at probe. The
seninf and YUV IRQ request paths do not show an immediate disable. The new
trial measured the storm specifically on YUV-B; seninf and other camera
IRQs remained at zero.

Lynx's live seninf tree has no `mtk_csi_phy_ver` property, so the matching
source selects its CSI PHY 3.0 handler by default. Its core starts with
`csi_irq_en_flag` and `vsync_irq_en_flag` both zero. The seninf IRQ is
requested at probe; the handler only reads and clears the corresponding
status registers when those flags are set. If the hardware IRQ were
asserted before streaming, that path could repeatedly return without
clearing it. **This hypothesis was not supported by the measured trial:**
seninf IRQ remained at zero. The old trial did not save `/proc/interrupts`.
The targeted launcher recorded the new trial, then was disabled after the
YUV-B result. The broad pipeline loader also refuses to cross into ISP.

`tools/analyze_camera_kernel_trace.py` extracts the saved init and RCU
timeline. `tools/record_camera_health_window.py` is a read-only Nexus-side
collector for boot identity, module state, `/proc/interrupts`,
`/proc/softirqs`, and Alpine health. Its five-second baseline trial on the
healthy recovered boot recorded two samples and no health issues at
`logs/camera-health-window-1793636233918336343/result.json`. It also writes
the largest IRQ-count changes and a complete camera IRQ subset. It does not
load modules or change Lynx.

The read-only device-tree IRQ inventory at
`logs/camera-dt-irq-inventory-20261102.json` records seven camera-related
interrupt specifiers: seninf SPI 476, RAW A/B/C SPIs 460/462/464, and YUV
A/B/C SPIs 461/463/465. Those nodes have no explicit
`interrupt-affinity` property in Lynx's live tree. The numbers are device
tree SPI specifiers, not Linux IRQ numbers. The measured YUV-B line is Linux
IRQ 247, corresponding to GIC SPI 495 as printed by `/proc/interrupts`.

Gate 1 passes only after a bounded RAM trial loads the ISP, captures kernel
messages continuously on Nexus, and remains healthy through the probe and a
later observation window. Verify Wi-Fi, SSH, the battery reserve service,
display, thermals, and a normal reboot. Keep the independent timed reboot
fallback; never unload the stock camera stack during a trial.

## Gate 2: enumerate the graph without streaming

Once the ISP is stable, inventory `/dev/media*`, the named V4L2 capture nodes,
subdevices, pads, links, formats, controls, and each sensor's modes. Resolve
the path from each sensor through CSI/seninf and RAW/ISP to a capture node.
Record the graph and hashes in a machine-readable manifest. The 73
`MTK-ISP-DIP-V4L2` nodes seen earlier are processing nodes and do not prove
a camera path. `CAMERA_STATUS` may show `interface_ready=1` after the ISP
binds but must retain `validated=0` until a real frame is inspected.
`tools/inventory_camera_runtime.py` now saves the read-only boot identity,
loaded camera modules, video/media device nodes, camera IRQs, and recent kernel
messages. A healthy V53 baseline with ISP absent produced 74 video nodes and
`/dev/media0`; `media-ctl` identified this as the image-processing
`MTK-ISP-DIP-V4L2` graph, not a sensor capture path. The baseline with the
topology is `logs/camera-runtime-inventory-1793710550075741704.json`. Run
the tool with `--media-graph --expect-isp` after a stable patched ISP trial,
then identify a separate camera capture graph before attempting any frame.
Alpine `v4l-utils` 1.32.0-r1 was installed for these read-only topology
queries; the root partition had 456 MiB free afterward.

## Gate 3: one frame per lens

Build a bounded local capture helper with a single-sensor lock, explicit
sensor selection, format and resolution limits, a short timeout, and cleanup
that stops streaming even on failure. Begin with one low-resolution raw frame
from the rear main IMX890. Check buffer metadata, nonzero pixel variation,
expected Bayer format, and that covering that lens changes the image. Repeat
for front, wide, and macro separately. Keep frames in a capped trial directory
on Alpine, copy them to Nexus for review, and remove trial frames only after
their evidence is preserved. No continuous preview or multi-camera concurrency
until all four single-frame trials are stable.

## Gate 4: Noob interfaces

After the frame trials, provide a local agent tool and Nexus-only NRP/1 calls
that share one guarded backend. Expose `CAMERA_LIST`, per-sensor status, one
bounded capture request, request status, and explicit cancel. NRP/1 should
return metadata and a request ID; image bytes should be retrieved over an
authenticated file-transfer path rather than put into VM numeric replies.
The VM can select a camera and request one frame only after the local helper
has passed the same safety checks. Publish each lens's independent validation
state on Lynx's Status page. Add boot-time camera services only after a clean
cold boot and recovery trial.

## Current stopping point

On 2026-11-03, Lynx returned from Fastboot to unchanged V53 Alpine. The
presence service reports `alpine_wifi`; SSH and `lynx-status --assert-ready`
passed on boot ID `f649a319-dcbb-47b9-9a54-7e482ee7eef2`. The camera stack
was initially absent. Battery later reached 46%. The four sensor drivers and
the known camera prefix loaded in RAM without error; the patched ISP remains
unloaded. Read-only preflight passed at
`logs/camera-isp-patched-trial-1793710768646260577/result.json`.
The ISP trial is held until an attended Fastboot recovery window is confirmed.
The offline patch build is complete
and reproducible with `tools/build_camera_yuv_irq_patch.py`; the live launcher
requires `--execute --attended` and an exact healthy V53 boot. Noob visually
confirmed the flashlight with a bounded 100 ms pulse; its Noob status reports
`validated=1` while the driver is bound. The staged flashlight boot service
remains disabled. The two pale rear circles are documented separately in
[LYNX-REAR-LIGHT-AND-COLOR-SENSOR.md](LYNX-REAR-LIGHT-AND-COLOR-SENSOR.md).
