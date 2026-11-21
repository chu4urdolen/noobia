# Hardware Watchdog (MTK-WDT) Preflight Gate & Unattended Recovery Policy

**Subsystem:** MediaTek MT6983 Hardware Watchdog Timer & TOPRGU Reset Controller
**Platform:** OnePlus Nord 3 (`oplus6983_22823`)
**Author:** Banshee (Spirit of Initiative 💙)
**Date:** 2026-11-21
**Directory:** `lynx/tools/watchdog/`

---

## 1. Hardware Architecture & Device Tree Mapping

To achieve safe unattended autonomy, Lynx requires a hardware-backed watchdog timer capable of recovering the system if an autonomous agent process hangs, deadlocks, or triggers an unrecoverable kernel stall.

### 1.1 Watchdog & TOPRGU MMIO Node

From `stock-merged.dtb`:
- **Node:** `watchdog@1c007000`
  - Base MMIO: `0x1c007000`, size `0x1000`
  - Compatible: `mediatek,mt6983-wdt`, `mediatek,mt6589-wdt`, `syscon`, `simple-mfd`
  - Phandle: `0x029a`
- **Reboot Mode Syscon Sub-node (`reboot-mode`):**
  - Compatible: `syscon-reboot-mode`
  - Register offset: `0x24`
  - Bitmask: `0xff`
  - Bootloader/Kernel recovery modes: `mode-bootloader`, `mode-recovery`, `mode-kernel`, `mode-silence`, `mode-edl`, `mode-dm-verity-dev-corrupt`

### 1.2 Linux Driver & Operational Invariants

- **Driver:** `drivers/watchdog/mtk_wdt.c` (`CONFIG_MEDIATEK_WATCHDOG=y` or `=m`)
- **Device Node:** `/dev/watchdog` (misc character device 10:130) and `/sys/class/watchdog/watchdog0/`
- **Hardware Timeout Limits:** 1 to 32 seconds (hardware counter resolution in seconds).
- **Petting Cadence for Autonomy:**
  - Recommended hardware timeout: **30 seconds**
  - Software petting interval: **5 seconds** (6x margin against scheduling jitter)
  - Supervision: OpenRC supervision daemon or watchdogd
- **Preflight Safety Invariant:**
  - Strictly read-only interrogation of sysfs (`/sys/class/watchdog/watchdog0/identity`, `timeout`, `status`).
  - **Zero character device opens on `/dev/watchdog` during preflight.** Opening `/dev/watchdog` arms the timer; closing without the magic 'V' character triggers an immediate hardware reset. Preflight enforces strict refusal to touch `/dev/watchdog`.
