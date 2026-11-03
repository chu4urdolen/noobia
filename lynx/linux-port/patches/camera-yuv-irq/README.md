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
`5b73c62a4d6ad768a44f09ce48231229ca9d1ee7aa7d88eb018b61e54e56fa40`.
`artifacts/camera-yuv-irq-build/build-result.json` records the source,
compiler, module checksums, and limits. The pinned Android Clang 12 toolchain
and copied stock-header Kbuild basis were used. The candidate has the same
vermagic and all 322 imported symbol CRCs as the stock ISP module. Its
`depends` metadata is incomplete because the partial symbol table records
unknown providers as `vmlinux`; load the known provider prefix manually in a
guarded RAM trial. The candidate must not be installed at boot or flashed
until the YUV-B IRQ remains quiet and a real camera frame is captured.

`tools/trial_camera_isp_patched.py --execute` is the bounded RAM trial. It
checks the exact V53 boot hash, module checksum, prerequisites, battery, and
thermals; starts kernel and IRQ recorders; arms a reboot fallback; and stops
if YUV-B exceeds 10,000 interrupts. The trial has not loaded the candidate:
one preflight caught an outdated checksum and another found Lynx still in
BusyBox before Alpine SSH started. Both ended before `insmod`.
