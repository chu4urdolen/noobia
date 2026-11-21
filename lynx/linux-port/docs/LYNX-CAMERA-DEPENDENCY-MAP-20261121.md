# Lynx Camera Subsystem: Multi-Sensor Dependency and Failure Map

**Document ID:** LYNX-DOC-20261121-CAMERA-DEP-MAP  
**Author:** Banshee 💙 (Spirit of Initiative)  
**Date:** 2026-11-21  
**Status:** SPECIFICATION & ARCHITECTURAL DEPENDENCY MAP  
**Platform:** OnePlus 11R 5G (Lynx / MT6895 / Dimensity 9000-series platform, Project `22823` / Vitamin)  
**Subsystem:** Camera Imaging Architecture (MediaTek ISP 7.1 / Seninf / CAMSV)  

---

## 1. Executive Summary & Core Diagnostic Boundaries

The OnePlus 11R 5G camera cluster integrates four physically distinct image sensors: rear macro, rear wide, rear main, and front selfie. While kernel device-tree entries exist for all four, **a device-tree match does NOT constitute optical proof or hardware readiness**.

During earlier hardware porting stages, an attended, RAM-patched ISP driver (`mtk-cam-isp.ko`) overcame the critical YUV-B interrupt storm (IRQ 247) and enabled bounded raw frame acquisition for the macro and wide sensors. However, the rear main (IMX890) and front (S5K3P9SP) sensors possess fundamentally different physical interface, color filter array, and actuator requirements.

### Hard Boundary Statement
> **`lynx_camera_gate.py` strictly restricts capture to the macro GC02M1 (`1600x1200 BA81`) and wide IMX355 (`3264x2448 BA81`) routes when explicitly optically verified.**  
> **The main IMX890 and front S5K3P9SP sensors use four-cell Bayer architectures and are HARD-REFUSED. They must never be streamed with assumed single-cell `BA81` formats.**

This document details the exact dependency chain, failure modes, and next smallest *offline* gate for every sensor.

---

## 2. Comprehensive Multi-Sensor Comparison Matrix

The table below contrasts all four sensors based on vendor device tree bindings (`cust_mt6983_vitamin_camera_v4l2.dtsi`), driver sources (`imgsensor_hw.c`), and trial history:

| Parameter | Rear Macro | Rear Wide | Rear Main | Front Selfie |
|:---|:---|:---|:---|:---|
| **Sensor Model** | GalaxyCore **GC02M1** | Sony **IMX355** | Sony **IMX890** | Samsung **S5K3P9SP** |
| **Physical Role** | Rear Macro | Rear Ultrawide | Rear Primary (OIS) | Front Display Punch-Hole |
| **I2C Address / Bus** | `9-003d` | `2-001a` | `8-0036` | `9-0010` |
| **EEPROM Calibration** | None | `2-0051` | `8-0050` / `8-0051` | None |
| **V4L2 Subdevice** | `/dev/v4l-subdev4` | `/dev/v4l-subdev6` | `/dev/v4l-subdev8` | `/dev/v4l-subdev2` |
| **Seninf CSI Sink** | `seninf-1` | `seninf-2` | `seninf-3` | `seninf-0` |
| **Physical PHY Bus** | MIPI D-PHY (1 lane) | MIPI D-PHY (4 lanes) | **MIPI C-PHY** (3 trios) | MIPI D-PHY (4 lanes) |
| **Color Filter Array (CFA)** | Single-cell Bayer (RGGB) | Single-cell Bayer (RGGB) | **Four-cell Quad Bayer** | **Four-cell Tetracell** |
| **Preview Geometry** | $1600 \times 1200$ | $3264 \times 2448$ | $4096 \times 3072$ | $2320 \times 1744$ |
| **Active Focus Actuator** | None (Fixed Focus) | None (Fixed Focus) | **VCM Actuator (`main_af`)** | None (Fixed Focus) |
| **Gate Status (`lynx_camera_gate`)** | **ALLOW** (with optical verification) | **ALLOW** (with optical verification) | **HARD REFUSE** | **HARD REFUSE** |
| **Proven Route Status** | **PROVEN_OPTICAL_RAM** | **PROVEN_FRAME_RAM** | **UNTESTED_HARDWARE** | **UNTESTED_HARDWARE** |

---

## 3. The Proven Macro and Wide RAM-Patched ISP Route

The baseline for all sensor operation on Lynx is the RAM-patched ISP architecture developed by Aria:

```
[Userspace: Bounded DMA-BUF Capture Helper]
                   |
     (Media Requests & Request-Scoped mtk_hdr_ae Controls)
                   |
                   v
[Kernel V4L2 Framework: /dev/media1 & /dev/video145 (CAMSV-0)]
                   |
                   v
[RAM-Patched mtk-cam-isp.ko]
   ├── Patch 0001: YUV-B IRQ Gate (prevents 68M IRQ storm on Linux IRQ 247)
   └── Patch 0002: CAMSV s_power(1)/s_power(0) wrapper (energizes PMIC LDOs)
                   |
                   v
[Staged RISC-V CCU Firmware in RAM (lib3a.ccu under dummy filename)]
                   |
                   v
[MediaTek Seninf CSI Controller (seninf-1 for macro, seninf-2 for wide)]
                   |
                   v
[Physical Image Sensor: GC02M1 or IMX355]
```

### Key Elements of the Working Route:
1. **Interrupt Protection:** Stock `mtk-cam-isp.ko` unconditionally enabled YUV-B interrupt lines at probe, generating over 68 million unhandled interrupts and triggering RCU stalls. Patch `0001` gates YUV interrupts on active runtime power.
2. **Sensor Power Sequencing:** In `imgsensor_hw.c`, streaming via CAMSV did not assert sensor PMIC rails (`multi_reg_ldo4`, `multi_reg_ldo7`), resulting in I2C `-6` communication failures. Patch `0002` explicitly wraps stream start/stop with `s_power`.
3. **Firmware Dependencies:** CCU initialization requires the full RISC-V `lib3a.ccu` binary staged in RAM under the dummy file name expected by stock drivers.
4. **Control Crash Avoidance:** Standard V4L2 control queries (`v4l2-ctl --list-ctrls-menus`) trigger a fatal kernel dereference (`docs/CAMERA-CTRL-CRASH-20261104.md`). Only request-scoped `mtk_hdr_ae` controls attached to media requests may be used.

---

## 4. Main Sensor (IMX890) Hardware Dependencies & Failure Map

The Sony IMX890 is a 50MP ($8192 \times 6144$) sensor operating natively in Quad Bayer format. Attempting to activate it without addressing the following dependencies will produce hardware failure:

### 4.1 Dependency 1: Four-Cell Quad Bayer Color Filter Array
- **Failure Mode:** Attempting capture with `BA81` (single-cell 8-bit Bayer) yields severe demosaicing corruption, false color artifacts, and spatial grid distortions.
- **Root Cause:** Pixels are grouped in $2 \times 2$ blocks under identical color filters ($2\text{R}, 2\text{Gr}, 2\text{Gb}, 2\text{B}$).
- **Requirement:** A software or hardware remosaic algorithm (Quad-to-Bayer conversion) must be incorporated into the image pipeline before standard debayering.

### 4.2 Dependency 2: MIPI C-PHY Signaling
- **Failure Mode:** Packet framing synchronization failure, PHY receiver bit errors, or seninf lockup.
- **Root Cause:** Unlike the D-PHY (clock lane + data lanes) used by GC02M1 and IMX355, IMX890 utilizes 3-phase trio signaling (C-PHY) on `seninf_csi_port_3`.
- **Requirement:** Precise C-PHY clock calibration and e-fuse trimming (`csi_efuse2`, `rg_csi`) within the seninf driver.

### 4.3 Dependency 3: Voice Coil Motor (VCM / OIS) Actuator
- **Failure Mode:** Blurred / out-of-focus imagery; potential actuator driver hang.
- **Root Cause:** The main lens assembly is mechanically suspended in an electromagnetic actuator (`&main_af` / `&main_af1` in DT at `&mtk_composite_v4l2_2`).
- **Requirement:** Actuator driver binding and initialization to drive the lens to its infinity or hyperfocal holding position before streaming.

### 4.4 Next Smallest Offline Gate for IMX890
- **Deliverable:** Offline C-PHY seninf-3 configuration validator and Quad Bayer $4096 \times 3072$ buffer geometry calculator (accounting for 10-bit packed pixel stride and 24-byte CAMSV headers).

---

## 5. Front Sensor (S5K3P9SP) Hardware Dependencies & Failure Map

The Samsung S5K3P9SP is a 16MP front-facing sensor utilizing Samsung's proprietary Tetracell color architecture:

### 5.1 Dependency 1: Four-Cell Tetracell Architecture
- **Failure Mode:** Color channel crosstalk and invalid demosaicing under standard Bayer tools.
- **Root Cause:** Tetracell arranges four adjacent subpixels of the same color into a single pixel unit in low light, or remosaics them into high-resolution mode.
- **Requirement:** Dedicated Tetracell re-mosaic configuration or binning mode selection in sensor register sequences.

### 5.2 Dependency 2: Seninf-0 Port Configuration
- **Failure Mode:** Seninf routing mismatch or link failure.
- **Root Cause:** Front sensor routes to `seninf-0` (`/dev/v4l-subdev2`), which uses distinct clock trees and pin multiplexing (`pinctrl` for mclk, rst, and PMIC regulators).
- **Requirement:** Validated `media-ctl` dynamic link descriptor to route `seninf-0` to CAMSV without disrupting existing links.

### 5.3 Next Smallest Offline Gate for S5K3P9SP
- **Deliverable:** Offline Tetracell mode descriptor parser, PMIC supply sequence specification (`dvdd`, `avdd`, `dovdd`), and buffer sizing calculation for $2320 \times 1744$ frame buffers.

---

## 6. Operational Restrictions & Safety Summary

1. **Gate Preservation:** The existing policy in `lynx_camera_gate.py` remains active and strictly enforced. All automated tools must refuse IMX890 and S5K3P9SP capture requests.
2. **No Hardware Trials in this Backlog Item:** Zero kernel module loads, zero media link changes, and zero capture attempts were issued.
3. **No Modification of Trial Scripts:** Aria's live camera scripts (`trial_camera_camsv_frame.py`, `prepare_camera_camsv.py`, `configure_camera_camsv_route.py`) remain untouched.
4. **Offline Progress:** The tooling in `/noobia/lynx/tools/camera_deps/` provides offline dependency tracking and verification without touching the physical phone.
