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
the stock ISP exactly. An attended RAM-only load passed on 2026-11-03 with
YUV-B IRQ 247 at zero, no RCU stall, and unchanged Alpine health. See
`logs/camera-isp-patched-trial-1793711196204592626/result.json`. This verifies
the probe-time gate. Runtime-resume IRQ behaviour and image capture remain
untested; neither boot packaging nor installation is ready.

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
the known camera prefix loaded in RAM without error. Read-only preflight passed at
`logs/camera-isp-patched-trial-1793710768646260577/result.json`.
The attended patched ISP trial then passed on the same boot with YUV-B IRQ at
zero and no RCU stall; see
`logs/camera-isp-patched-trial-1793711196204592626/result.json`. The ISP is
loaded only in RAM. `/dev/media1` now shows four bound sensors. The sensor4 →
seninf-1 → raw-0 route was linked but has not streamed. The raw-0 graph has 20
enabled immutable video output links; a single-node frame grab cannot satisfy
the driver's streaming barrier. A simpler sensor4 → seninf-1 → CAMSV-0 route
was then linked in RAM. The first bounded frame trial reached `VIDIOC_REQBUFS`
and failed with `EINVAL`; `v4l2-ctl` returned exit zero despite producing a
zero-byte file. Receipt:
`logs/camera-camsv-frame-1793711841867909119/result.json`. No sensor stream
started and YUV-B remained zero. Source review found this vendor driver's
`mtk_cam_dma_contig_memops` omits MMAP allocation and only implements DMA-BUF.
A queue setup probe using `V4L2_MEMORY_DMABUF` succeeded with capabilities 29
(DMA-BUF and media requests included), then released the queue. Receipt:
`logs/camera-dmabuf-queue-probe-1793712008407865709.txt`. A bounded
single-frame CAMSV helper now uses a DMA heap buffer and media requests, with
the watchdog and IRQ monitor retained.

That DMA-BUF helper now exists at `tools/lynx_camsv_dmabuf_capture.py` and its
host trial at `tools/trial_camera_camsv_frame.py`. The first stream attempt
failed with `ENOLINK` because both `lib3a.ccu_dummy` and `remoteproc_scp` were
absent from Lynx's firmware search path. Both names are present in the exact
August stock package. Staging them in RAM and temporarily selecting that
directory allowed CCU and CCD to boot, CAMSV-0 to stream, and a media request
to queue. The frame timed out after nine seconds. Kernel trace:
`logs/kernel-trial-1793712340213912805/kernel.kmsg`; trial receipt:
`logs/camera-camsv-frame-1793712335867990994/result.json`. The firmware path
was restored to `/vendor/firmware` and Alpine health passed afterward.

The trace shows repeated `-6` I²C reads from sensor4 (GC02M1) and no camera
interrupts. A targeted second stream measured its two device-tree supply
rails, `multi_reg_ldo4` and `multi_reg_ldo7`, disabled at all 120 samples;
`num_users` was zero. Receipt:
`logs/camera-camsv-frame-1793712601800841400/`. The matching OnePlus source
at commit `81ec42ad5e803be0cba619f9f7bb298db7d33d7b` is preserved in
`sources/oneplus-nord3-sensor-power/`. It shows `imgsensor_set_stream()` does
not call `adaptor_hw_power_on()` when `IMGSENSOR_USE_PM_FRAMEWORK` is absent;
the driver has a separate `s_power` operation. The compiled phone driver
reports runtime PM unsupported, and the source comments out
`POWERON_ONCE_OPENED`. This supports a missing explicit power-on call as the
cause of the dead I²C bus, pending a live patched trial.

`linux-port/patches/camera-yuv-irq/0002-power-sensor-for-camsv.patch` adds a
balanced `s_power(1)`/`s_power(0)` around CAMSV stream start and stop, with
failure cleanup. It leaves RAW paths alone. The offline build at
`artifacts/camera-yuv-irq-rebuild-1793712879991700862/build-result.json`
passed stock vermagic, all 322 imported symbol CRCs, and the 16 dependencies.
After a controlled reboot to unchanged V53, its RAM-only ISP load passed a
35-second no-capture trial on boot ID
`c9746c2f-20c3-4183-be5f-6ec04109813f`; receipt:
`logs/camera-isp-patched-trial-1793713338389485699/result.json`. Lynx reached
healthy Alpine again with 51% battery. The revised module remains RAM loaded
on that boot. The next step is to link the sensor4 → seninf-1 → CAMSV-0 route
and repeat the bounded frame trial while Noob is physically available. No
frame has yet been captured, and no camera module is installed at boot.

For the attended frame trial, `tools/configure_camera_camsv_route.py` links
sensor4 to CAMSV-0 in RAM. `tools/trial_camera_camsv_frame.py` verifies the
boot ID and stable ISP receipt, discovers the two sensor supply regulators
by name, and records their states while requesting one DMA-BUF frame. It
restores the normal firmware path and verifies it before disarming the reboot
fallback. A successful raw frame is copied to Nexus and decoded by
`tools/decode_camera_bayer.py` into a grayscale mosaic, an approximate RGB
preview, and pixel statistics. A generated preview is diagnostic only; lens
identity and image quality still require visual inspection. No live trial
will run until Noob is beside Lynx.

The first attended sensor-power trial on 2026-11-04 was bounded and left
Alpine healthy, but no frame arrived. Receipt:
`logs/camera-camsv-frame-1793786945696097633/result.json`; kernel trace:
`logs/kernel-trial-1793786962986304092/kernel.kmsg`. Both named sensor
rails remained disabled, and GC02M1 I²C reads again failed with `-6`.
Source review found the patch's `ctx->used_sv_num` test was evaluated before
`mtk_camsv_sd_s_stream()` increments that counter. The power call therefore
never ran. The patch now identifies the CAMSV node by `pipe_id` at that point.
The corrected offline rebuild at
`artifacts/camera-yuv-irq-rebuild-1793787441973056494/build-result.json`
passed the same ABI checks and still needs a RAM-only load trial.

The trial also logged `CCU init timeout` and regulator warnings while
booting the stock `lib3a.ccu_dummy` (52 bytes). The same firmware package
contains a full RISC-V `lib3a.ccu` (about 1.2 MB); the stock CCU module
hardcodes the dummy filename. The next guarded frame trial stages the full
image under that requested name in RAM and restores `/vendor/firmware` after
the stream. This is an experiment, not a verified CCU firmware fix. The
phone's boot and firmware partitions remain unchanged.

Lynx rebooted cleanly to Alpine on boot ID
`c8e0511e-ce54-405a-9d73-4561ce3cb082`. The corrected ISP module passed
its guarded 35-second RAM load at
`logs/camera-isp-patched-trial-1793787882967369823/result.json`. One CAMSV
request with the full stock CCU ELF staged under the dummy filename completed
and returned a 1,920,024-byte buffer. Receipt:
`logs/camera-camsv-frame-1793787958713322338/result.json`; raw copy and
preview are alongside it. CCU startup no longer timed out, GC02M1 I²C
transactions succeeded, YUV-B IRQ stayed at zero, stream-off completed,
the firmware path was restored, and Alpine stayed healthy. The first 24 bytes
of the buffer form a header; the original helper mistakenly included those
bytes in its 1,920,000-byte pixel copy. The corrected helper now skips them.
About 99.8% of the remaining first-frame bytes equal `0x10`, and the preview
is essentially black. This proves a capture buffer can complete; it does not
yet validate scene imaging. A second attended capture with the lens brightly
lit and a short stream settle is needed to distinguish a dark first frame
from a format or sensor configuration problem.

With the rear cluster pointed at a brighter scene, a second guarded CAMSV
request returned a valid 1,920,000-byte pixel payload after skipping the
24-byte header. Receipt:
`logs/camera-camsv-frame-1793792595508360700/result.json`; raw and RGB
preview are in the same directory. The pixel range widened from the first
frame's near-constant `0x10` to 15–52, with a coherent spatial brightness
gradient. CAMSV IRQ increased by 22; sensor stream-on/off completed, CCU
started without timeout, and Alpine health passed after capture. The image
is still very underexposed and does not yet identify the lens or prove a
recognizable scene. A covered-rear-cluster comparison is prepared to verify
optical response before tuning exposure or moving to other sensors.

The requested covered-lens comparison has not run. Its preflight at
`logs/camera-camsv-frame-1793792749933904088/result.json` failed on the
very first SSH boot-ID read (`No route to host`); no capture, firmware staging,
or camera state change occurred in that attempt. Nexus presence switched to
`not_observed` at 11:45 UTC, after the last authenticated battery observation
of 37% at 11:43 UTC. Shortly beforehand a read-only
`v4l2-ctl -d /dev/v4l-subdev4 --list-ctrls-menus` query did not return a
usable result. Its relation to Wi-Fi loss is unknown; do not repeat that
query until Lynx's boot and health are checked. Wait for physical screen
status or renewed authenticated SSH before another camera trial.

At 11:53 UTC Lynx was observed on USB Fastboot. Read-only preflight at
`logs/fastboot-preflight-1793793254255713665.json` confirmed the expected
product, bootloader, active slot A, and `slot-successful:a=yes` with retry
count 7. One normal `fastboot reboot` was sent without flashing. Alpine SSH
did not return in the following minutes, and Nexus saw Fastboot again at
11:58 UTC. A second read-only preflight at
`logs/fastboot-preflight-1793793552924834049.json` showed the same slot
metadata; no slot switch or boot partition write occurred. This does not
yet establish whether the return to Fastboot was autonomous or caused by
buttons; ask Noob before attributing the boot outcome to the camera trial.

Noob confirmed no button press. The exact V50 rescue image was rechecked
locally and restored to **boot_a only** via Fastboot, receipt
`logs/v53-boot-a-trial-1793795057385904665/result.json`: the 64 MiB send and
write both returned OKAY. A passive V50 observer was started before one
normal reboot at `logs/v50-first-boot-1793795078583486097/events.jsonl`.
Neither BusyBox SSH on port 22 nor Alpine SSH on port 2222 appeared before
Lynx returned to USB Fastboot. Read-only preflight at
`logs/fastboot-preflight-1793795427835180046.json` still shows slot A
successful, retry count 7, expected product and bootloader. Do not repeat
reboots or camera trials until power and boot-stage status are investigated.
The V50 rescue image is currently installed in boot_a; the Alpine ext4 root,
bootloader, slot B, and recovery partitions were not touched in this step.

That intermediate V50 state has now been resolved. `fastboot continue`
reached V50 BusyBox and healthy Alpine, allowing pstore retrieval. The
persistent log proves a `v4l2-ctl --list-ctrls-menus` sensor control ioctl
crashed the vendor V4L2 kernel path at previous-boot uptime 5157 seconds.
See `docs/CAMERA-CTRL-CRASH-20261104.md`; never repeat that control query.
The verified V53 image was then restored to boot_a and booted successfully
with `fastboot continue`. Alpine checked the exact V53 SHA256 and health at
`logs/v53-restored-continue-1793797376061989766.json`. The corrected ISP
loaded again in RAM. A trial-tool check falsely required YUV-B to be IRQ 247;
it was IRQ 246 with zero interrupts. The watchdog was disarmed after a live
health check, the check was fixed, and a read-only 35-second module
verification passed at
`logs/camera-isp-patched-trial-1793797587089689124/result.json`.
The sensor4 → seninf-1 → CAMSV-0 route was then linked in RAM at
`logs/camera-camsv-route-1793797633053228225.json`. V53 boot ID was
`fa2ee038-c248-498d-8343-2e39a2395c71`. The later covered-lens trial
on that boot is recorded below. Check current boot ID and health before any
new trial, since a reboot clears the RAM module and route. Do not query
sensor controls with `v4l2-ctl`.
The offline patch build is complete
and reproducible with `tools/build_camera_yuv_irq_patch.py`; the live launcher
requires `--execute --attended` and an exact healthy V53 boot. Noob visually
confirmed the flashlight with a bounded 100 ms pulse; its Noob status reports
`validated=1` while the driver is bound. The staged flashlight boot service
remains disabled. The two pale rear circles are documented separately in
[LYNX-REAR-LIGHT-AND-COLOR-SENSOR.md](LYNX-REAR-LIGHT-AND-COLOR-SENSOR.md).

Noob then placed Lynx on her back with the rear camera cluster against the
desk. The first covered attempt, `logs/camera-camsv-frame-1793797873149322911`,
stopped before streaming because the optional `/dev/kmsg` SSH monitor exited
early. Lynx stayed healthy and the trial watchdog was disarmed. The monitor
now saves a `dmesg` tail with each IRQ/health sample and treats loss of the
optional stream as degraded logging rather than a camera failure.

The guarded retry captured a 1600×1200 BA81 Bayer frame (1,920,000 pixel
bytes after its 24-byte header) at
`logs/camera-camsv-frame-1793797979714459979/result.json`. Its values were
14–20, mean 16.002, and 99.806% of pixels were `0x10`; the preview is
visually black. During the same trial, CAMSV1 IRQ 249 rose by 22, sensor
regulators were enabled during streaming and disabled afterward, all 17
health samples reported the same V53 boot ID with no issues, and firmware
search path was restored to `/vendor/firmware`. The independent brighter
capture had values 15–52, mean 18.563, and a spatial gradient. Together,
these observations support an optical response to covering the rear cluster,
but do not identify which lens sensor4 uses or establish a usable exposure.
No partition was written during either covered attempt. Avoid the crashing
V4L2 control-enumeration ioctl while reviewing the sensor source and safe
exposure path.

The first direct exposure test has now produced a specific negative result.
Both bounded scalar `VIDIOC_S_CTRL` writes (1,200 and 3,000 lines) returned
success after stream-on, but neither trial generated a CAMSV frame interrupt
or a buffer within nine seconds. An unchanged capture between them delivered
a frame and 22 CAMSV1 interrupts on the same boot. Alpine stayed healthy and
the trial cleanup completed. The host tool now blocks direct exposure writes.
See [CAMERA-EXPOSURE-20261104.md](CAMERA-EXPOSURE-20261104.md) for source
paths, receipts, and the next offline investigation.

A request-scoped 1,200-line exposure trial subsequently returned a complete
CAMSV frame with 22 interrupts and healthy Alpine. This uses the ISP's
request-time sensor-control path and avoids the failing standalone write.
Because the rear cluster was still covered, a lit-scene comparison is needed
to show whether exposure actually changed the pixels. The receipt and source
review are in [CAMERA-EXPOSURE-20261104.md](CAMERA-EXPOSURE-20261104.md).

With the rear cluster uncovered, a two-frame media-request trial attached a
3,000-line exposure to the first request. Both frames completed in one
stream. The second brightened coherently across all measured image regions,
from mean 17.254 to 19.034 raw units, and a diagnostic contrast stretch
revealed a recognizable room scene. See the same exposure note for the raw
frames, preview, and guarded procedure. The remaining camera work is to
raise actual signal quality and color accuracy, then package a safe runtime
service; this trial did not install camera modules at boot.

On 2026-11-04 a request-scoped `mtk_hdr_ae` control set the same 3,000-line
exposure with raw gain 1,024 and then 2,048 in separate guarded two-frame
captures. The untouched first frames matched closely; the affected second
frames showed 1.8616× more black-level-corrected signal at nominal 2× gain.
All sixteen image regions brightened. The matching vendor source, request
layout, Dushich's independently tested offline helper, frame receipts, and
limits are recorded in [CAMERA-EXPOSURE-20261104.md](CAMERA-EXPOSURE-20261104.md).
The next engineering task is to improve the dark raw image, validate each
physical lens, and build a guarded camera service without changing V53 boot.
Offline Bayer channel analysis found that the matching GC02M1 source declares
RAW_R, whereas CAMSV accepted a BA81 capture format and the generic graph
shows SBGGR10. Both BGGR and RGGB previews have now been generated from the
same saved frame. The phase and color balance remain unresolved; use a known
color target before publishing a color camera interface. On the current
2026-11-05 V53 boot, Alpine health passed and the camera stack is absent
because its experimental modules were loaded only in RAM on the prior boot.

### Next attended trial sequence

The current boot ID is `25360b8f-e99c-404c-b295-4535f8c5e47a`; re-read it
before acting. The previous known-good preparation sequence was
`probe_camera_ram.py --through mtk-cam-plat-mt6983`, then
`probe_camera_pipeline_ram.py --through mtk_printk_ctrl`, followed by
`trial_camera_isp_patched.py --preflight-only --with-sensor-power` and its
`--execute --attended --with-sensor-power` mode. Link the route with
`configure_camera_camsv_route.py --boot-id <current-id>` only after the ISP
trial passes. The host capture helper also requires `--attended` and the
same boot ID. An initial read-only preflight on 2026-11-05 stopped before
loading because this new boot has no camera prefix; receipt:
`logs/camera-isp-patched-trial-1793889425493621641/result.json`. No camera
module or route was loaded by that preflight.

For the next optical test, aim the uncovered rear cameras at a bright scene
containing known red and blue objects. Capture a bounded raw frame with the
existing watchdog and monitors, then compare both Bayer phase previews.
Avoid `v4l2-ctl --list-ctrls-menus`, standalone exposure `S_CTRL`, and any
boot partition change. Keep the patch and V53 restoration path available.

Noob supplied a red cable and blue soldering helper as targets. The guarded
preparation and two-frame capture completed on this boot, but the immediate
post-capture health check briefly reported `lynx-health` stopped. The host
tool stopped with its watchdog armed; Aria verified a healthy same boot,
restored `/vendor/firmware`, disarmed the watchdog, and copied both raw frames.
The brighter second frame shows the monitor and lights, but the intended red
and blue objects are not identifiable. See the 2026-11-05 section of
[CAMERA-EXPOSURE-20261104.md](CAMERA-EXPOSURE-20261104.md) and its
`manual-recovery.json` receipt. The host cleanup path has been tightened but
has not yet been live-tested. Wait for a clearly positioned color target
before another attended capture.

A subsequent attended capture at
`logs/camera-camsv-frame-1793895847755492267/result.json` passed end to end
on the same boot and saved a much clearer image of the curved cable and
segmented helper. The live seninf source pad reported RGGB; the matching
sensor source declares RAW_R; and the left curved object's red-minus-blue
signal was +6.20 raw units under RGGB. The decoder therefore defaults to
RGGB now, while BGGR remains selectable for comparison. No color calibration
or physical lens identification has been completed. The revised normal
success cleanup path passed this trial; its error branch has not yet had a
live regression trial.

Noob confirmed the curved object in that frame is the red cable, resolving
the Bayer phase for this route in favor of RGGB. The raw decoder keeps the
original payload and an explicit BGGR option for audit.

`tools/prepare_camera_camsv.py` now sequences the established RAM-only
preparation steps after a reboot. `--status` checks the exact V53 boot SHA,
Alpine health, restored firmware path, current boot ID, patched ISP receipt,
and media route without changing Lynx. `--execute --attended` loads missing
camera prefixes, performs the patched ISP's own read-only preflight and
monitored load, then links sensor4 to CAMSV-0. Each stage retains its native
receipt and stops on failure. It does not capture frames, unload modules, or
write partitions. Its read-only status mode reported `already_prepared` on
boot `25360b8f-e99c-404c-b295-4535f8c5e47a` at
`logs/camera-prepare-1793896774981616185/result.json`; the live execution
path has not yet been exercised as a whole.

The read-only `/dev/media1` graph saved at
`logs/camera-graph-20261105-v53-live.txt` gives the next sensor routes:

| Sensor | Source node | Current mode | Seninf sink | State |
| --- | --- | --- | --- | --- |
| sensor0 / IMX890 | `/dev/v4l-subdev8` | 4096×3072 | seninf-3 | link disabled |
| sensor1 / S5K3P9SP | `/dev/v4l-subdev2` | 2320×1744 | seninf-0 | link disabled |
| sensor2 / IMX355 | `/dev/v4l-subdev6` | 3264×2448 | seninf-2 | link disabled |
| sensor4 / GC02M1 | `/dev/v4l-subdev4` | 1600×1200 | seninf-1 | CAMSV-0 route enabled |

The current capture helper allocates exactly one 1600×1200 8-bit frame, so
it cannot safely capture the other sensor modes yet. The pinned matching
source confirms IMX355 preview at 3264×2448 with RAW_R and four MIPI lanes.
IMX890 preview is 4096×3072 but declares hardware four-cell Bayer over CPHY;
the front S5K3P9SP is also four-cell Bayer. Start with the wide IMX355 as the
next independent sensor path. Parameterize buffer geometry and format under
explicit per-sensor bounds, and implement an attended route switch that
disables the working sensor4 → CAMSV-0 link before enabling sensor2 →
seninf-2 → CAMSV-0. Its cleanup must restore the sensor4 baseline even if
the wide trial fails. Do not stream sensor0 or sensor1 using an assumed
single-cell Bayer format. Keep sensor4's working route available as the
baseline. The source files are pinned and SHA-verified in
`sources/oneplus-nord3-sensor-power/SOURCE.json`.

Dushich's separate geometry calculator (verified commit `369aca5`, 36 tests)
checks the planned 8-bit buffer sizes: sensor4 1,920,024 bytes and sensor2
7,990,296 bytes, including the observed 24-byte CAMSV header. Aria adapted
the one-frame remote helper to accept only sensor4 or sensor2 and kept it
self-contained because it is streamed to Lynx via `python3 -`. The existing
sensor4 default is preserved. This is an **offline preparation only** for
sensor2; the wide sensor's actual `sizeimage`, header layout, route switch,
and frame completion have not been verified. The two-frame AE helper and host
trial still target sensor4 only.

## 2026-11-05 IMX355 wide trial

The previous paragraph records the preparation state. A guarded route switch
has now run twice in RAM and returned to sensor4 each time. The correct
`media-ctl` descriptor retains dynamic flag 4 when disabling a link:
`27:1->615:0[4]`. A descriptor ending in `[0]` was rejected before any link
changed. The exact graph and restoration receipts are under
`logs/camera-route-switch-1793897872599657409/` and
`logs/camera-route-switch-1793897888561957769/`. Dushich's verified
route-planning task `20261105T165126Z-8c39a783` used incomplete media link
descriptors, so Aria did not adopt its code; the live plan in
`tools/camera_route_plan.py` was checked against the graph and parser.

An attended format-only probe confirmed that `/dev/video145` accepts IMX355
3264×2448 BA81 with `Size Image 7990296`, exactly 7,990,272 pixel bytes plus
the 24-byte CAMSV header. It restored 1600×1200 BA81 and the macro route.
Receipt: `logs/camera-wide-format-1793897952473287594/result.json`.

The first guarded IMX355 stream returned a complete 7,990,272-byte Bayer
payload, with `bytesused=7990296`, buffer sequence 1, clean STREAMOFF, no
YUV-B interrupt storm, and same-boot Alpine health. The raw payload is almost
entirely the black level 16 (98.8% at or below 16), so no scene or lens
identity can yet be claimed. The diagnostic contrast image is speckled noise.
See `logs/camera-wide-frame-1793898116331141692/result.json` and its saved
frame. The host trial reported `failed_format_restore` because it checked
`v4l2-ctl --set-fmt` stdout, which is empty on success. A separate read-only
check immediately afterward confirmed 1600×1200 BA81, `/vendor/firmware`,
healthy Alpine, the same boot ID, and zero YUV-B IRQs. The macro route was
explicitly restored by the trial. The host tool now verifies restoration with
`--get-fmt-video`; that correction awaits the next live trial. No partition
was modified.

An offline parity analysis of the dark wide payload found all four Bayer
positions near 16.01, with 1.16–1.20% of samples above 16. Adjacent value-17
pairs occurred 1,905 times versus about 1,112 expected from an independent
uniform distribution. This is weak spatial structure, not a recognizable
scene; see `logs/camera-wide-frame-1793898116331141692/dark-spatial-analysis.json`.
The guarded wide tool now marks frames with at least 98% black-level samples
as optically unverified. The next discriminating test remains a bright,
detailed scene with all rear lenses uncovered, followed by comparison of raw
histograms and image structure. Do not treat a full DMA-BUF as camera
validation by itself.

On 2026-11-06, Noob prepared a brighter rear-camera scene. An attended trial
on the same V53 boot returned a recognizable 3264×2448 IMX355 wide image
showing a monitor, work surface, and lights. Raw positive signal rose from
0.0119 in the dark trial to 2.3965 (about 201×); black-level fraction fell
from 98.82% to 48.12%. The complete DMA-BUF was 7,990,296 bytes including
its 24-byte header, and the 7,990,272-byte payload was decoded as RGGB for
preview. The visible image validates this optical route; exact Bayer phase
and color calibration for IMX355 remain to be checked with a color target.
The helper reported clean STREAMOFF and the host restored 1600×1200 BA81,
the sensor4 macro route, and `/vendor/firmware`. Alpine health passed on the
same boot. Receipt and preview:
`logs/camera-wide-frame-1793970498449657635/result.json` and
`logs/camera-wide-frame-1793970498449657635/sensor2-preview-lifted.png`.
No boot partition or recovery partition was written.

An offline planning gate in `tools/lynx_camera_gate.py` now distinguishes the
two previously recognizable routes (GC02M1 1600×1200 BA81 and IMX355
3264×2448 BA81) from untested main/front routes and unknown formats. Dushich
prepared it in his separate workspace; Aria reviewed and adopted the pure
parser. Its input includes a caller assertion of optical verification, so an
`allow` result is not evidence from a live receipt and must not authorize a
camera action by itself. It makes no phone calls or hardware changes.

## 2026-11-15 new-boot read-only preflight

On boot `0aa70b0f-1449-43e7-acf5-1bb5680c2a0f`,
`prepare_camera_camsv.py --status` returned `not_prepared` with no error at
68% battery. Its receipt records zero preparation steps and no camera stream:
`logs/camera-prepare-1794771627167366489/result.json`. This confirms the
camera stack is still RAM-only after a new Alpine boot. It does not test the
patched ISP or capture path on this boot. No camera module, route, firmware
path, or boot partition was changed by this preflight.
