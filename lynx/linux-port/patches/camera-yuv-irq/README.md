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
patch passed one guarded RAM-only load on Lynx. A real camera stream and
runtime-resume IRQ behaviour remain untested.
The source also links each RAW device to its matching YUV device with
`DL_FLAG_PM_RUNTIME` in `mtk_raw_setup_dependencies()`. The stream path calls
`pm_runtime_get_sync()` on RAW devices, which should power their YUV suppliers
before RAW. This supports the proposed runtime resume gate, though it does
not prove that YUV-B's IRQ line clears correctly when powered.

The build output is
`artifacts/camera-yuv-irq-build/cam/mtk-cam-isp.ko`, SHA256
`ade3ba24ff56d3b96f3f37842f878880d5e38a4da211e88768b4ebbd8d0cb5eb`.
The guarded trial uses its debug-stripped copy
`artifacts/camera-yuv-irq-build/cam/mtk-cam-isp-stripped.ko`, SHA256
`b0072fce10d91202cf02586bb21cea7ccb61d36988828fc86c696e8f9c838b64`.
It is 2.7 MB instead of 17.2 MB. `.text`, `__versions`, and `.modinfo`
are byte-identical to the unstripped build.
`artifacts/camera-yuv-irq-build/build-result.json` records the source,
compiler, module checksums, and limits. The pinned Android Clang 12 toolchain
and copied stock-header Kbuild basis were used. The candidate has the same
vermagic, all 322 imported symbol CRCs, and the same 16 `depends` providers
as the stock ISP module. The partial symbol table maps the 34 imports from
those providers using the stock modules' `__ksymtab` exports; the remaining
imports are recorded as `vmlinux`. Load the known provider prefix manually
in a guarded RAM trial. The candidate must not be installed at boot or flashed
until a real camera frame is captured and the stream remains stable.

`tools/build_camera_yuv_irq_patch.py` reproduces the build in a new timestamped
artifact directory without contacting Lynx. One clean rebuild passed the
same vermagic, 322 import CRC, and 16 provider checks at
`artifacts/camera-yuv-irq-rebuild-1793693137162767366/build-result.json`.
Its file SHA differs from the pinned trial candidate because Kbuild embeds
build-path information; the trial tool still pins the earlier reviewed file.

`tools/trial_camera_isp_patched.py --preflight-only` checks the module,
dependencies, V53 image, battery, thermals, and RCU state without loading
anything. It passed on the current boot at
`logs/camera-isp-patched-trial-1793710768646260577/result.json` using the
debug-stripped trial file.
`tools/trial_camera_isp_patched.py --execute --attended` is the bounded RAM trial. It
checks the exact V53 boot hash, module checksum, prerequisites, battery, and
thermals; starts kernel and IRQ recorders; arms a reboot fallback; and stops
if YUV-B exceeds 10,000 interrupts. The attended trial loaded the candidate
into RAM on boot ID `f649a319-dcbb-47b9-9a54-7e482ee7eef2`. Its receipt is
`logs/camera-isp-patched-trial-1793711196204592626/result.json`. The 35-second
observation passed with no RCU stall, YUV-B IRQ 247 at zero, and Alpine health
intact. The fallback watchdog was disarmed. No frame was requested and no
partition was changed.

After the load, `/dev/media1` appeared as the `mtk-cam` capture graph with
four bound sensors. `logs/camera-runtime-inventory-1793711513222991424.json`
records the graph. A candidate route from sensor4 through seninf-1 to raw-0
was enabled in RAM using dynamic link flags 5; it has not been streamed.
Source review shows raw-0 has 20 enabled immutable video output links and
`mtk_cam_vb2_start_streaming()` waits for every enabled node in the pipeline.
A single `v4l2-ctl --stream-mmap` on main-stream is therefore not a valid
frame trial. The CAMSV path below avoids that multi-output barrier.

## CAMSV sensor-power follow-up

CAMSV-0 has a single output. `tools/lynx_camsv_dmabuf_capture.py` uses a
DMA heap buffer and media request because the vendor buffer driver omits MMAP
allocation. With the matching stock CCU and CCD firmware staged in RAM, the
first CAMSV trial reached stream-on but got no frame. The sensor4 GC02M1 I²C
transactions failed with `-6`, and its AVDD/DOVDD regulator rails remained
disabled throughout the capture window. The matching stock `adaptor-drv.c`
has a separate `s_power` operation; its stream callback does not enable power
in this build. See the detailed timeline in `docs/LYNX-CAMERA-PORT-PLAN.md`.

`0002-power-sensor-for-camsv.patch` adds a balanced sensor power call only for
CAMSV stream contexts. `tools/build_camera_yuv_irq_patch.py --extra-patch
linux-port/patches/camera-yuv-irq/0002-power-sensor-for-camsv.patch` produced a
module with stock vermagic, 322 matching import CRCs, and 16 matching module
dependencies. Receipt:
`artifacts/camera-yuv-irq-rebuild-1793712879991700862/build-result.json`.
The revised module passed one guarded RAM load on boot ID
`c9746c2f-20c3-4183-be5f-6ec04109813f`; no capture was attempted and YUV-B
IRQ stayed quiet. Receipt:
`logs/camera-isp-patched-trial-1793713338389485699/result.json`. A live frame
trial is still needed before using this module at boot.
