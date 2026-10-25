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
recovery-related partitions. As of this note, V49 has **not been flashed**.
