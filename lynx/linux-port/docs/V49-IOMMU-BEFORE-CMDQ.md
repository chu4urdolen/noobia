# Lynx V49 offline display candidate — 2026-10-25

Noob watched the 15-second V48 color-bar test and saw a black screen. The
DRM ioctl returned success, but `dmesg` recorded CMDQ error interrupts with
`err:-22` during the test. The original trial parser searched for timeouts
and missed these error interrupts. Its code now detects `[cmdq][err]` and
`[DISP][E]`; old trial receipts are retained as originally recorded.
Evidence: `logs/v48-dmabuf-trial-1792962915844407881/`.

The two GCE platform devices have `iommus` properties but no visible
`iommu_group` links on V48. The CMDQ source prints `cannot get dev ... domain`
when `iommu_get_domain_for_dev()` returns null. V48 loads
`mtk-cmdq-drv-ext.ko` during Wi-Fi setup; it never loads stock
`mtk_iommu.ko` until the later, host-triggered display bootstrap. The stock
`modules.load` puts `mtk_iommu.ko` before CMDQ. This makes an early IOMMU
load a specific hypothesis, **not a proven fix**.

`tools/build_v49_iommu_before_cmdq.py` built a 64 MiB V49 candidate from the
exact working V48 image. It added the hash-verified stock
`mtk_iommu.ko` to the supplement and placed it after its already-loaded
dependencies and immediately before CMDQ in
`etc/lynx/wifi-radio-modules.load`. The kernel, init script, command line,
all other supplement members, tail, bootloader, recovery partitions, and
slot B are unchanged. Independent roundtrip and delta checks passed in
`tools/validate_v49_iommu_before_cmdq.py`.

V49 SHA-256:
`896aa4937b168090cd3c75d41995917dad05aedfbc7bf83790fe31342b061e0f`.
Image: `linux-port/artifacts/iommu-before-cmdq-v49-offline/nord3-iommu-before-cmdq-v49-untested.img`.
V48 rollback SHA-256:
`ff1244698cf791546b7c03c2f510882048c91a88f9344e80d583fda388f2340d`.

`python3 tools/lynx_boot_a_v49_trial.py --prepare` passed and prints the
exact flash, reboot, and V48 restoration commands. It does not contact the
phone. A controlled trial may write **boot_a only** after a fresh battery
check and Fastboot preflight. If V49 fails to boot but Fastboot returns,
restore the pinned V48 image using `--restore-v48`. Do not change slot B or
recovery-related partitions.

## Controlled boot and display result

V49 was flashed to `boot_a` only after a root Fastboot preflight matched
product `k6983v1_64`, unlocked slot A, expected partition sizes, and the
pinned bootloader. The verified V48 image remained available for restoration.
Receipts: `logs/v49-boot-a-trial-1792963603055373523/` for the flash and
`logs/v49-boot-a-trial-1792963622970388983/` for reboot. The first
unprivileged preflight failed because USB access required sudo; it performed
no write. The root preflight passed.

On new boot `38795684-219b-4b82-9b36-2b3001fc02a6`, rescue SSH showed
`CHECKPOINT_MODULE_OK mtk_iommu.ko` before CMDQ and a GCE IOMMU group link.
Alpine 3.24.2 then passed three observer samples and health checks:
`logs/v49-first-boot-1792963613869822471/`.

The guarded RAM-only display bootstrap registered the same connected DRM
panel. DMA-BUF allocation passed. A ten-second color-bar modeset returned
exit 0, but the corrected log parser found a CMDQ timeout waiting for event
644 (`EVENT_STREAM_BLOCK`) on thread 0. Receipt:
`logs/v49-dmabuf-trial-1792963974493441918/`. Thus the earlier missing
IOMMU domain is fixed, but it was not sufficient to produce a healthy display
commit. Do not repeat the same draw trial until the event producer and panel
power sequence are understood. V49 remains the current boot image; rollback
is available if needed.

The stock Synaptics touchscreen stack was loaded into RAM on the same V49
boot. `/dev/input/event0` registered, and Noob's taps produced 12 press and
12 release events with valid X/Y coordinates in a 30-second read-only
capture: `logs/v49-touch-events-1792964117579390120/`. Touch input works.
