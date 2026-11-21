# Lynx Cellular Modem (CCCI & MD1) Preflight Gate Architecture

**Device:** OnePlus Nord 3 5G (`CPH2493` / platform `MT6983` / Project `22823`)  
**Subsystem:** MediaTek MT6983 MD1 Baseband, Cross Core Communication Interface (`CCCI`)  
**Author:** Banshee 💙 (Spirit of Initiative)  
**Date:** 2026-11-21  
**Status:** Validated Tool Directory & Offline Preflight Specification  

---

## 1. Executive Summary & Hardware Context

The OnePlus Nord 3 features an integrated cellular baseband subsystem designated **MD1** within the MediaTek MT6983 (Dimensity 9000) SoC. Communication between the application processor (AP) running Linux and the modem core is conducted across the **Cross Core Communication Interface (CCCI)**, which provides shared-memory ring buffers, hardware doorbells, and character device endpoints.

Because cellular baseband firmware execution involves radio frequency (RF) calibration, NVRAM access, and potential transmission:
> [!IMPORTANT]
> **Safety Invariant:**
> 1. No live boot of MD1 may occur without explicit, attended operator authorization.
> 2. The SIM card must be physically removed / unbound to ensure zero cellular network registration.
> 3. The modem core must remain in quiescent baseline state `md1:0` (`INVALID`).
> 4. All preflight checks must remain strictly read-only, non-mutating, and bounded.

---

## 2. Kernel & Inter-Processor Communication (CCCI) Architecture

The AP interacts with the modem via kernel CCCI drivers that expose specialized character devices and sysfs telemetry:

### 2.1 Critical Character Device Nodes
The following nodes are exposed by the MT6983 CCCI driver:
- `/dev/ccci_ioctl0` to `/dev/ccci_ioctl4`: Control channels for modem daemon (`ccci_mdinit`) and IPC orchestration.
- `/dev/ccci_md1_sta`: Modem state reporting interface.
- `/dev/ccci_fs`: Filesystem proxy bridge allowing MD1 to read calibrated NVRAM and partition assets from the AP filesystem.
- `/dev/ccci_rpc`: Remote procedure call channel between AP and baseband firmware.
- `/dev/ttyC0`: Virtual serial AT command channel.

### 2.2 Boot State Tracking (`/sys/kernel/ccci/boot`)
The kernel exports the run-state of all modem cores via `/sys/kernel/ccci/boot`:
- **`md1:0` (INVALID / QUIESCENT):** Modem core has not been booted or initialized. RF power amplifier is unpowered; baseband clocks are gated.
- **`md1:1` (BOOTING):** Modem bootloader is executing firmware initialization.
- **`md1:2` (READY):** Modem firmware loaded and running.

The preflight validator strictly asserts that `/sys/kernel/ccci/boot` reads `md1:0`. Any other state halts execution as blocked.

---

## 3. Stock Firmware Artifact Verification on Nexus

Before any modem trial is considered, stock vendor binaries and partition images on Nexus must match exact cryptographic hashes:
1. **Userland Loader Daemon (`ccci_mdinit`):**
   - Path: `/noobia/lynx/linux-port/artifacts/stock-cph2493-August-eu-ota/wifi-reference/vendor-unpacked/bin/ccci_mdinit`
   - Expected SHA-256: `a288eb339fbc13c7a1c135855dbd2de94b01fadc93059ec4e9f5075528582849`
2. **Modem Baseband Partition (`md1img`):**
   - Manifest: `/noobia/lynx/linux-port/artifacts/stock-cph2493-August-eu-ota/payload-partitions.json`
   - Partition Size: `80,928,768` bytes (77.17 MiB)
   - Expected SHA-256: `7cf648e726d4ef57e9e82eb918c113156c73f0f4118f1011973c022af10c2fa7`

---

## 4. Safety Gates & Evaluation Matrix

The preflight tool (`lynx/tools/modem/lynx_modem_preflight.py`) evaluates five sequential safety gates:

| Gate | Requirement | Failure Action |
|---|---|---|
| **Boot Identity** | Phone `boot_id` matches pinned boot (`0fe847d2-44d6-4ac1-9000-2c99df1a51d8`). | Block: stale telemetry or reboot detected. |
| **Power & Thermal** | Battery capacity $\ge 50\%$; SoC temperature $\le 45^\circ\text{C}$ (`45000` m°C). | Block: prevents brownouts or overheating under dynamic load. |
| **SIM Removal** | No driver bound to `/sys/devices/platform/*SIM*` or `odm:oplus_sim_detect`. | Block: physically removed SIM is mandatory. |
| **CCCI Nodes** | All 9 critical CCCI character devices exist in `/dev/`. | Block: baseband communication pathway incomplete. |
| **MD1 Baseline** | `/sys/kernel/ccci/boot` reports `md1:0`. | Block: modem must be unbooted before controlled trial. |

---

## 5. Tool Implementation & Hermetic Test Suite

The tool is packaged in `lynx/tools/modem/`:
- `lynx_modem_preflight.py`: Evaluator with `--validate <FIXTURE>`, offline artifact check, and gated live collector (`--live --allow-live`).
- `fixtures/modem-ready-status.json`: Golden baseline with `md1:0`, unbound SIM, valid battery (85%) and temperature (31°C).
- `fixtures/modem-sim-inserted-blocked.json`: Negative fixture testing SIM detection gate.
- `fixtures/modem-md1-booting.json`: Negative fixture testing non-baseline `md1:1` rejection.
- `test_lynx_modem_preflight.py`: 14 unit tests covering artifact verification, gate evaluation, and fixture replay.

Zero live rootfs writes, zero module loads, zero character device opens.
