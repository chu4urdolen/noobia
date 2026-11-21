# Lynx Low-Power Island SCP / LPM Preflight Architecture

**Author:** Banshee 💙 (Spirit of Initiative)  
**Date:** 2026-11-21  
**Target:** OnePlus Nord 3 5G (CPH2493, MediaTek MT6983 / Dimensity 9000)  
**Task Item:** B20 (Round 6)  
**Status:** Landed & Validated  

---

## 1. Executive Summary

This document establishes the hardware mapping, Device Tree bindings, mailbox communication topology, and preflight verification gates for the **System Companion Processor (SCP)** and the **Low-Power Module (mtk_lpm / SPM)** on the OnePlus Nord 3.

The MediaTek MT6983 incorporates an isolated always-on low-power subsystem (the "low-power island") anchored by the dual-core RISC-V SCP. The SCP offloads continuous background processing—such as sensor hub / CHRE event fusion, Voice-on-Wakeup (VOW) acoustic trigger detection, Always-On Display (AOD) refresh, and baseband modem wake routing—allowing the main Application Processor (AP) octa-core cluster to enter deep sleep (`mcusysoff`).

---

## 2. Subsystem Architecture & Device Tree Topology

From the kernel Device Tree (`mt6983.dts`), the low-power island and SPM resource management subsystem is structured as follows:

```
+-----------------------------------------------------------------------------------------+
|                               MediaTek MT6983 SoC                                       |
|                                                                                         |
|  +-----------------------------------------------------------------------------------+  |
|  | Application Processor Octa-Core Cluster (Cortex-X2 + A710 + A510)                 |  |
|  +----------------------------------------+------------------------------------------+  |
|                                           |                                             |
|                     5 Hardware Mailboxes  |  Shared TCM SRAM (2 MiB @ 0x1c400000)       |
|                     (mbox0 .. mbox4)      |                                             |
|                                           v                                             |
|  +-----------------------------------------------------------------------------------+  |
|  | System Companion Processor (SCP @ 0x1c700000): Dual-Core RISC-V Subsystem         |  |
|  | - Core 0: System control, DVFS management, deep-sleep coordinator                  |  |
|  | - Core 1: Acoustic trigger (VOW), sensor hub (CHRE), AOD controller               |  |
|  +----------------------------------------+------------------------------------------+  |
|                                           |                                             |
|                                           | Resource Requests & Constraints             |
|                                           v                                             |
|  +-----------------------------------------------------------------------------------+  |
|  | MediaTek Low-Power Module (mtk_lpm / System Power Manager - SPM)                  |  |
|  |                                                                                   |  |
|  |   Resource Voters:                                                                |  |
|  |   - bus26m (id 0): 26 MHz Root Crystal Oscillator & Bus Clock                      |  |
|  |   - infra   (id 1): Infracfg Peripheral Interconnect Bus                          |  |
|  |   - syspll  (id 2): Main System PLL Frequency Synthesizer                         |  |
|  |   - dram_s0 (id 3): LP-DDR5 Channel S0 Self-Refresh Power Controller              |  |
|  |   - dram_s1 (id 4): LP-DDR5 Channel S1 Self-Refresh Power Controller              |  |
|  +-----------------------------------------------------------------------------------+  |
+-----------------------------------------------------------------------------------------+
```

### 2.1 System Companion Processor (SCP) Node Details
- **Node:** `scp: scp@1c700000`
- **Compatible:** `"mediatek,scp"`
- **Physical Memory Map:**
  - `scp_sram_base`: `0x1c400000` (Size: `0x200000` = 2,097,152 bytes / 2 MiB TCM)
  - `scp_cfgreg`: `0x1c724000`
  - `scp_clkreg`: `0x1c721000`
  - `scp_cfgreg_core0`: `0x1c730000`
  - `scp_cfgreg_core1`: `0x1c740000`
  - `scp_bus_tracker`: `0x1c752000`
  - `scp_l1creg`: `0x1c760000`
  - `scp_cfgreg_sec`: `0x1c7a5000`
  - Mailboxes: `mbox0` (`0x1c7fb000`), `mbox1` (`0x1c7fc000`), `mbox2` (`0x1c7fd000`), `mbox3` (`0x1c7fe000`), `mbox4` (`0x1c7ff000`)
- **Topology:** Dual-core (`core_nums = <2>`, `twohart = <1>`), status `okay`.
- **Interrupts:** 7 SPI interrupts (`ipc0`, `ipc1`, `mbox0` through `mbox4`).
- **Inter-Processor Interrupt (IPI) Endpoints:**
  - `IPI_OUT_C_SLEEP_0/1`: Coordinated sleep entry and AP cluster power-down
  - `IPI_OUT_SENSOR_CTRL`: Sensor hub communication & event polling
  - `IPI_OUT_AUDIO_VOW_1`: Voice-on-Wakeup low-power acoustic trigger
  - `IPI_OUT_APCCCI_0`: Low-power modem event bridge
  - `IPI_OUT_SCP_AOD`: Always-on display buffer presentation

### 2.2 Low-Power Module (mtk_lpm) Node Details
- **Node:** `mtk_lpm: mtk_lpm`
- **Compatible:** `"mediatek,mtk-lpm"`
- **Resource Controllers:**
  - `bus26m`: id `0x00000000`, root 26MHz reference clock voter
  - `infra`: id `0x00000001`, Infracfg peripheral interconnect voter
  - `syspll`: id `0x00000002`, system PLL synthesizer voter
  - `dram_s0`: id `0x00000003`, LP-DDR5 Rank S0 self-refresh entry controller
  - `dram_s1`: id `0x00000004`, LP-DDR5 Rank S1 self-refresh entry controller
- **Tracked Power States:** `mcusysoff` (AP cluster power down), `system_mem` (DRAM self-refresh retention), `system_pll` (PLLs gated), `system_bus` (high-speed interconnect clocks gated).

---

## 3. Preflight Validator & Safety Gates

The preflight tool `lynx/tools/lpm/lynx_lpm_preflight.py` verifies both static device tree mappings and runtime low-power telemetry against invariant safety criteria:

1. **SCP Core & Remoteproc Verification:**
   - Asserts SCP controller presence on SoC interconnect (`1c700000.scp`).
   - Verifies core running state (`running` or `active`).
   - Asserts TCM allocation equals 2 MiB (`0x200000` bytes).
   - Verifies all 5 hardware mailboxes are instantiated.
2. **LPM Resource Voter Integrity:**
   - Confirms all 5 required resource voters (`bus26m`, `infra`, `syspll`, `dram_s0`, `dram_s1`) are enumerated.
   - Monitors low-power entry abort counters; flags warnings if abort counts escalate.
3. **Safety & Permission Boundaries:**
   - **Zero Sleep Actuation:** Tool NEVER echoes to `/sys/power/state`, never triggers SPM suspend routines, and never alters LPM debugfs nodes.
   - **Zero Module Injections:** Observes existing state without loading or unloading modules.
   - **Double-Gated Live Probes:** Live interrogation requires explicit `--live --allow-live`.

---

## 4. Test Evidence

The tool includes a hermetic unit test suite (`test_lynx_lpm_preflight.py`) validating three realistic snapshots:
- `lpm-baseline-active.json`: Normal active state (`LPM_ACTIVE_RUNNING`, Status `OK`).
- `lpm-deep-sleep.json`: DRAM self-refresh low-power state (`LPM_LOW_POWER_STANDBY`, Status `OK`).
- `lpm-scp-hung-failure.json`: Fault state with crashed SCP and missing mailboxes (`SCP_FAULT_OR_HUNG`, Status `FAIL`).

```
test_ast_safety_and_no_writes (test_lynx_lpm_preflight.TestLynxLpmPreflight) ... ok
test_baseline_active_running (test_lynx_lpm_preflight.TestLynxLpmPreflight) ... ok
test_boot_id_mismatch (test_lynx_lpm_preflight.TestLynxLpmPreflight) ... ok
test_cli_live_safety_gate (test_lynx_lpm_preflight.TestLynxLpmPreflight) ... ok
test_cli_validate_offline (test_lynx_lpm_preflight.TestLynxLpmPreflight) ... ok
test_deep_sleep_standby (test_lynx_lpm_preflight.TestLynxLpmPreflight) ... ok
test_lpm_missing_controller (test_lynx_lpm_preflight.TestLynxLpmPreflight) ... ok
test_lpm_missing_resource (test_lynx_lpm_preflight.TestLynxLpmPreflight) ... ok
test_scp_crashed_failure (test_lynx_lpm_preflight.TestLynxLpmPreflight) ... ok
test_wakeup_abort_warning (test_lynx_lpm_preflight.TestLynxLpmPreflight) ... ok

----------------------------------------------------------------------
Ran 10 tests in 0.100s

OK
```
