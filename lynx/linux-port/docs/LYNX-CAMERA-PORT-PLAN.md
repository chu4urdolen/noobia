# Lynx four-camera native Linux plan

Prepared offline on 2026-11-02. This plan does not change Lynx's running
system. No camera module should be loaded again until the ISP stall is
understood. Keep V53 boot, Alpine SSH, the portrait, and the V50/BusyBox
recovery path intact.

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

The stock clock, regulator, CCU, EEPROM, four sensors, and image-processing
modules have loaded in RAM. `mtk-cam-isp` binds and creates capture-class
nodes, but two separate trials then produced CPU 0 RCU stalls and transient
service loss. The second trace is
`logs/kernel-trial-1793604146750082321/kernel.kmsg`; the trial receipt is
`logs/camera-pipeline-1793604298438939297/result.json`. The ISP module's
successful return is followed about 15 seconds later by the first stall.
CPU 0 has only WFI enabled; its deeper idle states are already disabled.
This is an association, not yet a proven kernel cause.

Review the exact module's probe and clock/interrupt paths against matching
MT6983 source and the stock device tree. The checked-out OnePlusOSS modules
branch and the official Nord 3 13.1 modules branch have no `mtkcam` source
tree, so other OEM camera source can guide
questions but cannot be treated as a drop-in match. Check the module's
dependencies, IRQ affinity, media registration, and firmware requests
offline. Do not try to hide the stall by loosening health assertions or
repeating the same load.

`tools/analyze_camera_kernel_trace.py` extracts the saved init and RCU
timeline. `tools/record_camera_health_window.py` is a read-only Nexus-side
collector for boot identity, module state, `/proc/interrupts`,
`/proc/softirqs`, and Alpine health. Its five-second baseline trial on the
healthy recovered boot recorded two samples and no health issues at
`logs/camera-health-window-1793636233918336343/result.json`. It also writes
the largest IRQ-count changes, which can be compared with a future bounded
ISP trial. It does not load modules or change Lynx.

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

Lynx is back on V53 Alpine with her portrait, SSH, and Noob service healthy.
The camera stack is not loaded on this boot. Noob visually confirmed the
flashlight with a bounded 100 ms pulse; its Noob status now reports
`validated=1` while the driver is bound. The staged flashlight boot service
remains disabled. The two pale rear circles are documented separately in
[LYNX-REAR-LIGHT-AND-COLOR-SENSOR.md](LYNX-REAR-LIGHT-AND-COLOR-SENSOR.md).
