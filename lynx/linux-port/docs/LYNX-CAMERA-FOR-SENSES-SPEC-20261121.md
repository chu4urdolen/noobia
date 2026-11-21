# Lynx's camera for the senses: what the proven path really is, and a staged plan

Gwyn, 2026-11-21. This is offline analysis of the repository's trial tools.
No phone contact. It replaces the assumption behind H2 (`be2a477`) that
the camera only needs media links at boot.

## The proven path today (attended, RAM-only)

**Stage A, `lynx/tools/trial_camera_isp_patched.py`:**
- `insmod` of **one** module: a patched, stripped `mtk-cam-isp.ko`, the
  sensor-power variant with candidate `SENSOR_POWER_ISP_SHA
  0910503d465a9ea51b70a6b501fc7dead5f2eafd1f7d5a17845b1056eb5d9b3e`.
  - It is built offline from stock source plus the YUV-IRQ patch
    (`31f6176b…`) and the sensor-power patch (`35931ce2…`). The artifacts
    are under `lynx/linux-port/artifacts/camera-yuv-irq-*`.
  - The load is bounded by `busybox timeout 25`.
- It counts as good only after **35 s of stable observation**, recorded in a
  receipt with `state=stable_35_seconds_no_capture`.
- Gates: kernel identity, module hash, battery ≥ 25 % while charging (35 %
  otherwise), temperatures.

**Stage B, `lynx/tools/trial_camera_camsv_frame.py`:**
- **Requires a Stage A receipt for the same boot**, and `mtk_cam_isp` loaded.
- The health gate: battery ≥ 35 % and temperatures below limits.
- The CAMSV route must be **exclusive**: `sensor4 → seninf-1 → mtk-cam
  camsv-0`, with `raw-0` not linked.
- **YUV-B IRQ guard**: the `cam_yuv_b` interrupt count must be under 1000.
  The stock ISP caused an IRQ storm.
- It **temporarily switches the global firmware path**
  (`/sys/module/firmware_class/parameters/path`, normally
  `/vendor/firmware`) to a staged directory. That directory holds
  `lib3a.ccu` staged as `lib3a.ccu_dummy` (`6f8d5119…`) and
  `remoteproc_scp` (`66687aad…`), both from the stock CPH2493 OTA.
- It sets the format 1600×1200 BA81 on `/dev/video145`. That node number
  comes from that boot.
- It **arms a 55 s `reboot -f` watchdog** during capture, then captures one
  frame.

Documented hazards:
- the stock ISP's IRQ storm;
- a stock camera-control ioctl that caused a kernel Oops;
- direct exposure `S_CTRL`, which lost frames (`CAMERA-EXPOSURE-20261104.md`).

**Conclusion.** Today, every capture needs an attended operator and a
forced-reboot safety net. "Camera at boot" means making Stage A persistent,
and making Stage B safe to repeat **without** the reboot net. That is real
hardware work, not just service plumbing.

## Proposed stages (decision for Noob and Aria)

| Tier | What | Who | Gate |
| --- | --- | --- | --- |
| **C1: first live test, attended** | Aria runs Stage A and B as today, once, with Noob present. A small wrapper sends the captured frame to Nexus detection (`:5050`) and emits `NOOBIA P1 camera object.seen label=…` through `sense.py`, so Aigel and Lynx's loop see a **real** camera event | Banshee writes the wrapper; Aria runs it | Existing trial gates. No boot change. Proves the whole loop with real pixels |
| **C2: repeatability** | Run Stage B 10 times on one boot, attended, without the reboot net firing. Measure the IRQ count, frame validity, heat and battery. Script it as a bounded trial | Banshee writes; Aria runs | No IRQ growth, no Oops, every frame valid |
| **C3: Stage A at boot** | OpenRC service that loads the patched ISP **after** health is ready, behind a disable switch, with the hash checked first and the 35 s stability check. It writes a status file and **reports not-ready honestly** | Banshee writes; Aria installs after C2 | Cold-boot trial with Noob present; recovery route ready |
| **C4: autonomous capture** | `lynx-camera-capture` with the Stage B gates built in. Nodes resolved by entity name, no hard-coded `/dev/video145` or `/dev/media1`. The firmware path is switched and restored inside the capture, or the CCU firmware is staged permanently under `/vendor/firmware`. The IRQ guard aborts. Rate-limited, e.g. one frame per 30 s. The camera sense S1 uses it | Banshee writes; Gwyn and Dushich review | Only after C2 passes. The reboot net is replaced by the IRQ guard plus a bounded stop |

Recommendation: do **C1 now** for the first live test. It is attended, uses
only proven steps, and needs no boot change. Then C2 → C3 → C4 for a camera
Lynx can use on her own.
