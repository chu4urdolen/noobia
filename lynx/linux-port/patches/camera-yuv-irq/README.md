# Nord 3 YUV IRQ gating candidate

The stock `mtk-cam-isp.ko` binds the camera media graph but leaves the YUV-B
interrupt line active before streaming. On Lynx V53, Linux IRQ 247 counted
68,127,138 events on CPU 0 during a bounded stock-module trial. The matching
OnePlus 13.1 source registers YUV IRQs without the probe-time disable used
for RAW IRQs.

`0001-gate-yuv-irq-on-runtime-power.patch` is an **experimental** fix for the
pinned OnePlus kernel commit `81ec42ad5e803be0cba619f9f7bb298db7d33d7b`.
It disables each YUV IRQ immediately after registration, disables it before
runtime clock suspend, and enables it after runtime clock resume. It reads
the same four status registers as the stock handler before enabling. The
patch has not been proven on Lynx; in particular, runtime PM state and IRQ
acknowledgement semantics still require a guarded trial.

The build output is
`artifacts/camera-yuv-irq-build/cam/mtk-cam-isp.ko`, SHA256
`ade3ba24ff56d3b96f3f37842f878880d5e38a4da211e88768b4ebbd8d0cb5eb`.
`artifacts/camera-yuv-irq-build/build-result.json` records the source,
compiler, module checksums, and limits. The pinned Android Clang 12 toolchain
and copied stock-header Kbuild basis were used. The candidate has the same
vermagic, all 322 imported symbol CRCs, and the same 16 `depends` providers
as the stock ISP module. The partial symbol table maps the 34 imports from
those providers using the stock modules' `__ksymtab` exports; the remaining
imports are recorded as `vmlinux`. Load the known provider prefix manually
in a guarded RAM trial. The candidate must not be installed at boot or flashed
until the YUV-B IRQ remains quiet and a real camera frame is captured.

`tools/build_camera_yuv_irq_patch.py` reproduces the build in a new timestamped
artifact directory without contacting Lynx. One clean rebuild passed the
same vermagic, 322 import CRC, and 16 provider checks at
`artifacts/camera-yuv-irq-rebuild-1793693137162767366/build-result.json`.
Its file SHA differs from the pinned trial candidate because Kbuild embeds
build-path information; the trial tool still pins the earlier reviewed file.

`tools/trial_camera_isp_patched.py --execute --attended` is the bounded RAM trial. It
checks the exact V53 boot hash, module checksum, prerequisites, battery, and
thermals; starts kernel and IRQ recorders; arms a reboot fallback; and stops
if YUV-B exceeds 10,000 interrupts. The trial has not loaded the candidate:
one preflight caught an outdated checksum and another found Lynx still in
BusyBox before Alpine SSH started. Both ended before `insmod`.
