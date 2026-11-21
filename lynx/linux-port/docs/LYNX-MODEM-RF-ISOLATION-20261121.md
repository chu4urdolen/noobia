# Lynx MD1 Cellular Modem RF-Isolation Assessment (2026-11-21)

## Executive Summary

This document presents an offline, evidence-backed technical assessment of radio frequency (RF) isolation for the MediaTek MT6983 (Dimensity 9000) baseband modem subsystem (MD1) on the OnePlus Nord 3 5G (Lynx, CPH2493) running native Alpine Linux on boot `0fe847d2-44d6-4ac1-9000-2c99df1a51d8`.

Following review feedback from Aria (Note #85), this assessment is structured as an analytical evaluation of hardware, driver, and firmware boundaries—not an executable trial runbook. It explicitly distinguishes between:
1. **Observed Baseline Facts** (verified directly on live hardware or verified local artifacts).
2. **Upstream Source References & Tracing** (inferred from public kernel trees and stock Android manifests).
3. **Unknowns & Unverified Assumptions** (parameters that cannot be proven without physical measurement or proprietary source code).

**Final Determination:** **NO-GO** for live MD1 power-on trials under the current environment. MD1 must remain powered off (`md1:0`, `INVALID`).

RF isolation cannot be proven from offline software inspection, baseline regulator states, or the physical absence of a SIM card. Closed-source baseband DSP firmware (`md1img`) possesses dedicated hardware paths to PMIC regulators and RF transceiver interfaces. Without physical RF shielding or hardware-level interlocks on PMIC supplies, zero RF emission cannot be guaranteed upon releasing the baseband processor from reset.

---

## 1. Subsystem Architecture and Epistemic Boundary

### 1.1 CCCI Kernel Driver and FSM Architecture

*   **Observed Baseline:**
    *   Kernel modules loaded on Lynx: `ccci_md_all`, `ccci_auxadc`, `ccci_util_lib`, `mddp`.
    *   Sysfs state attribute: `/sys/kernel/ccci/boot` reads `md1:0 | md2:n/a | md3:n/a | md4:n/a | md5:n/a`.
    *   Bootloader metadata in sysfs (`/sys/kernel/ccci/lk_md`): reports `LK Load MD:[Enabled](0x00000001)`, `LK load MD success!`, and `md_en=E-D-D-D-D (1->5)`.
    *   Character devices: 53 nodes exist under `/dev/ccci*` and `/dev/ttyC*` (including `/dev/ccci_ioctl0`-`4`, `/dev/ccci_md1_sta`, `/dev/ccci_fs`, `/dev/ttyC0`).
    *   Kernel message logs: `mddp_rx` continuously reports `port ccci_0_200 read data fail when md_state = 0` (~1 message/sec), indicating the AP-side network driver is attempting to poll an inactive modem.

*   **Upstream Source Lineage:**
    *   **State Enumeration:** Defined in [`/noobia/lynx/tools/gauge-build-inputs-1792103708378707350/kbuild-selective/drivers/misc/mediatek/include/mt-plat/mtk_ccci_common.h#L442-L451`](file:///noobia/lynx/tools/gauge-build-inputs-1792103708378707350/kbuild-selective/drivers/misc/mediatek/include/mt-plat/mtk_ccci_common.h#L442-L451):
        ```c
        enum MD_STATE {
            INVALID = 0,         /* Baseline: MD powered off, no traffic */
            GATED,               /* MD powered, clocks gated */
            BOOT_WAITING_FOR_HS1,/* Handshake 1: boot handshake with AP */
            BOOT_WAITING_FOR_HS2,/* Handshake 2: runtime NVRAM data exchange */
            READY,               /* Full operational AP-MD link */
            EXCEPTION,           /* Baseband assertion / firmware crash */
            RESET,               /* Hardware reset in progress */
            WAITING_TO_STOP,     /* Controlled shutdown sequence */
        };
        ```
    *   **Start IOCTL Caller Enforcement:** In `drivers/misc/mediatek/eccci/fsm/ccci_fsm_ioctl.c#L454-L485`, the kernel checks `strncmp(current->comm, "ccci_mdinit", 11) == 0` before accepting `CCCI_IOC_DO_START_MD` (`_IO(CCCI_IOC_MAGIC, 13)`).
    *   **Sysfs Write Trap:** In `drivers/misc/mediatek/ccci_util/ccci_util_lib_sys.c#L141-L150`, writing to `/sys/kernel/ccci/boot` returns the write count to userspace while calling `trigger_md_boot()`. In `drivers/misc/mediatek/eccci/ccci_modem.c#L981`, `boot_md_store()` returns `-EACCES`. Sysfs writes do not start the modem.

*   **Inference vs. Unknown:**
    *   *Inference:* The bootloader loaded modem partition material (`md1img`) into reserved DRAM during boot, but MD1 core execution has remained gated in state `0` (`INVALID`).
    *   *Unknown:* Whether issuing `CCCI_IOC_DO_START_MD` from a custom process spoofing `comm="ccci_mdinit"` would successfully transition the FSM past `GATED (1)` on Alpine without stock Android shared memory Daemons (`ccci_fsd`).

### 1.2 Device Tree Hardware Mapping (`/soc/mddriver`)

*   **Observed Baseline:**
    *   Device tree node `/sys/firmware/devicetree/base/soc/mddriver` declares:
        *   `compatible = "mediatek,mddriver"`
        *   `md_vmodem-supply = <0x40>` (phandle pointing to PMIC regulator `VBUCK6`)
        *   `md_vsram-supply = <0x41>` (phandle pointing to PMIC regulator `VSRAM_MODEM`)
        *   `md_vdigrf-supply = <0x42>` (phandle pointing to PMIC regulator `VBUCK1`)
        *   `mediatek,srclken_o1 = <0x0>`
    *   Hardware clock and power handshake node exists at `/sys/firmware/devicetree/base/srclken-rc@1c00d000/md1-ctl`.

*   **Inference vs. Unknown:**
    *   *Inference:* The AP controls power domains supplying the digital baseband core and digital RF interface (`VBUCK1`, `VBUCK6`, `VSRAM_MODEM`).
    *   *Unknown:* The degree of hardware autonomy granted to MD1 over PMIC registers via SPMI/SRCLKEN lines once MD1 is released from reset.

### 1.3 PMIC Regulators and RF Power Rail Status

*   **Observed Baseline (on boot `0fe847d2-44d6-4ac1-9000-2c99df1a51d8`):**

| Regulator Name | Sysfs Path | State | Voltage | Users | Role |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `mt6363_vsram_digrf` | `/sys/class/regulator/regulator.12` | **enabled** | 850 mV | 1 | Digital RF interface (AP side) |
| `mt6363_vsram_modem` | `/sys/class/regulator/regulator.14` | **enabled** | 800 mV | 1 | Baseband SRAM retention |
| `mt6363_vrfio18` | `/sys/class/regulator/regulator.29` | **enabled** | 1700 mV | 1 | RF I/O digital bus level shifter |
| `mt6363_vrf12` | `/sys/class/regulator/regulator.34` | **enabled** | 1200 mV | 1 | Shared internal logic / PLL rail |
| `mt6373_vrf18_aif` | `/sys/class/regulator/regulator.50` | **enabled** | 1800 mV | 1 | Secondary PMIC interface I/O |
| `mt6373_vrfio18_aif`| `/sys/class/regulator/regulator.51` | **enabled** | 1800 mV | 1 | Secondary PMIC digital I/O |
| `mt6363_vsram_mdfe` | `/sys/class/regulator/regulator.13` | **disabled** | 800 mV | 0 | Modem Front-End (MDFE) DSP memory |
| `mt6363_vrf18` | `/sys/class/regulator/regulator.28` | **disabled** | 1800 mV | 0 | RF Transceiver analog supply |
| `mt6363_vrf13` | `/sys/class/regulator/regulator.35` | **disabled** | 1300 mV | 0 | RF Transceiver analog supply |
| `mt6363_vrf09` | `/sys/class/regulator/regulator.36` | **disabled** | 900 mV | 0 | RF Transceiver core supply |
| `mt6373_vrf13_aif` | `/sys/class/regulator/regulator.49` | **disabled** | 1300 mV | 0 | Front-End Module secondary supply |
| `mt6373_vrf09_aif` | `/sys/class/regulator/regulator.52` | **disabled** | 900 mV | 0 | Front-End Module core supply |
| `mt6373_vrf12_aif` | `/sys/class/regulator/regulator.53` | **disabled** | 1200 mV | 0 | Front-End Module secondary supply |
| `mt6373_vsram_digrf_aif`| `/sys/class/regulator/regulator.55`| **disabled**| 850 mV | 0 | Front-End Module interface supply |

*   **Critical Clarification on Regulator Status:**
    > [!WARNING]
    > The observed disabled state of `mt6363_vrf09/13/18` and `mt6363_vsram_mdfe` applies **only** while MD1 is held in reset (`md1:0`). It does **not** prove that these rails remain disabled after MD1 powers on. In MediaTek system architecture, baseband coprocessors interface directly with PMIC hardware via dedicated hardware channels. Powering MD1 can result in autonomous hardware enablement of transceiver supplies without AP intervention.

### 1.4 SIM Hardware Interface & Linux Driver State

*   **Observed Baseline:**
    *   Platform device nodes present:
        *   `/sys/devices/platform/MD1_SIM1_HOT_PLUG_EINT`
        *   `/sys/devices/platform/MD1_SIM2_HOT_PLUG_EINT`
        *   `/sys/devices/platform/odm:oplus_sim_detect`
    *   None of these three nodes currently have a bound `driver` symlink.
*   **Critical Clarification on SIM Status:**
    > [!IMPORTANT]
    > The absence of a bound Linux driver under `/sys/devices/platform/*SIM*` proves **only** that the Alpine Linux kernel has not loaded an AP-side driver for SIM detection. It does **not** prove the physical SIM tray is empty. A physical SIM card could be physically inserted in the tray while remaining unmonitored by Linux. Confirmation of an empty tray relies strictly on physical human inspection.

---

## 2. RF Transmission Analysis: What Powering MD1 Triggers

### 2.1 3GPP Specification Boundary vs. Unverified Firmware Reality

*   **The 3GPP Specification Perspective (Theory):**
    *   Under 3GPP TS 38.304 and TS 36.304, a User Equipment (UE) without an authorized Universal Subscriber Identity Module (USIM) cannot perform network registration (Attach / Registration Request). It transitions into the *Limited Service State*.
    *   In Limited Service State, standard UE behavior is nominally restricted to downlink reception (scanning available carrier frequencies, acquiring synchronization signals PSS/SSS, and reading broadcast system information MIB/SIB1).
    *   Under standard protocol specifications, uplink transmission (PRACH preamble burst) is prohibited unless an explicit Emergency Call is triggered by upper-layer telephony software.

*   **The Unverified Firmware Reality:**
    *   **Closed-Source DSP Blob (`md1img`):** The modem partition contains an 80,928,768-byte proprietary binary image (`7cf648e7...`). The AP host does not have access to its source code or internal state machine logic.
    *   **Boot-Time Transceiver Calibration:** During baseband boot (Handshake 1 and early DSP initialization), cellular basebands routinely perform radio frequency hardware calibrations (e.g. Phase-Locked Loop lock verification, Local Oscillator leakage calibration, DC offset correction, and internal loopback checks).
    *   **Unverified Uplink Silence:** The assumption that "no SIM means no RF uplink" is **unverified**. Closed-source baseband DSP code could emit test signals, LO leakage, or spurious RF energy through antenna switches during early initialization or in unhandled fault loops (such as missing NVRAM). SIM absence does **not** guarantee RF silence.

### 2.2 Dependency on Missing Userspace Daemons

In stock Android, Handshake 2 (`BOOT_WAITING_FOR_HS2`) requires `/vendor/bin/ccci_fsd` to read NVRAM calibration files (`/mnt/vendor/nvdata/md`).
*   On Lynx Alpine Linux, `ccci_fsd` does not exist.
*   If MD1 is commanded to boot, it will inevitably stall at `BOOT_WAITING_FOR_HS2 (3)` or time out into `EXCEPTION (5)`.
*   An uncalibrated, faulting baseband core represents an uncontrolled hardware state where analog RF behavior cannot be predicted from documentation.

---

## 3. Failure and Uncertainty Matrix

| Failure / Risk Category | Epistemic Status | Mechanism / Source | Detectable via Read-Only Software? | Impact Severity |
| :--- | :--- | :--- | :--- | :--- |
| **Spurious RF Emission during Boot** | **Unverified / Unknown** | Transceiver self-calibration or LO leakage during PLL lock prior to Handshake 2. | **NO.** Linux host has no RF power detector or spectrum sensor. | **CRITICAL** |
| **Autonomous PMIC Rail Enablement** | **Inferred Hardware Risk** | Baseband SPM asserts PMIC rails via SPMI/SRCLKEN lines upon reset release. | **PARTIALLY.** Visible in `/sys/class/regulator/` after assert, but cannot be blocked. | **HIGH** |
| **SIM Tray Status Uncertainty** | **Unknown without Operator Check** | Platform nodes have no bound driver; physical tray contents cannot be probed via software. | **NO.** Software cannot differentiate empty tray from unprobed SIM. | **MEDIUM** |
| **Missing NVRAM (`ccci_fsd`) Stall** | **Observed Software Absence** | MD1 halts in `BOOT_WAITING_FOR_HS2 (3)` due to missing daemon; draws power without completing boot. | **YES.** Visible via `/dev/ccci_md1_sta` and kernel dmesg. | **MEDIUM** |
| **CCCI AP Kernel Panic / Lockup** | **Inferred Driver Risk** | Baseband assertion triggers CCCI panic handler on the Application Processor. | **YES.** Device freezes or resets; contact lost. | **HIGH** |

---

## 4. Observable Read-Only Gates

Before considering any future trial, the following read-only observations must be verified and logged:

1. **Gate 1: Baseband State Inactive**
   - Command: `cat /sys/kernel/ccci/boot`
   - Verified Baseline: `md1:0 | md2:n/a | md3:n/a | md4:n/a | md5:n/a` (MD1 in `INVALID`).
2. **Gate 2: Baseline Regulator Inactivity**
   - Command: Check `/sys/class/regulator/regulator.*/state`
   - Verified Baseline: `mt6363_vsram_mdfe`, `mt6363_vrf18`, `mt6363_vrf13`, `mt6363_vrf09`, `mt6373_vrf*` must report `disabled` with `users=0`.
3. **Gate 3: Telephony Userspace Inactivity**
   - Command: `ps -ef | grep -E "(rild|mtkfusionrild|ccci_mdinit|ccci_fsd|ccci_rpcd)"`
   - Verified Baseline: Zero active processes.
4. **Gate 4: Platform Hardware Health**
   - Telemetry: Battery capacity $\ge 50\%$, SoC temperature $< 40^\circ\text{C}$, rootfs clean.

---

## 5. Untested Stop and Abort Mechanics & Associated Risks

### 5.1 Proposed Abort Sequence (Theoretical)

MediaTek CCCI driver source indicates that a software shutdown of MD1 would proceed via:
1. `ioctl(CCCI_IOC_DO_STOP_MD, 1)`: Requests modem transition to flight mode / `WAITING_TO_STOP (7)`.
2. `ioctl(CCCI_IOC_MD_RESET, 0)`: Forces hardware reset assertion if soft shutdown fails.

### 5.2 Critical Uncertainties & Risks of Abort Sequence:
*   **Untested on Alpine:** This sequence has never been executed or verified on Lynx's native Alpine rootfs. It cannot be characterized as deterministic.
*   **Regulator Force-Disable Is Unsafe:** Manually disabling PMIC regulator rails (`/sys/class/regulator/`) from AP Linux while a coprocessor is active or resetting is **prohibited**. Arbitrary PMIC rail drops can violate hardware power-down sequencing rules, potentially causing latch-up, voltage spikes, or permanent silicon damage.
*   **Watchdog Uncertainty:** A hardware watchdog reboot (`/dev/watchdog`) provides an emergency recovery mechanism against AP kernel panics, but SoC-level reboots subject flash storage and battery to uncontrolled cycles.

---

## 6. Proposed Physical Containment Rationale ($\ge 60\text{ dB}$)

The requirement for an RF-attenuating enclosure (Faraday pouch or RF shield box) with $\ge 60\text{ dB}$ attenuation is an **engineering proposal** derived from standard RF lab safety margins:
*   **Nominal UE Max Transmit Power:** Under 3GPP TS 38.101-1 (Table 6.2.1-1), Power Class 3 user equipment has a maximum output power of $+23\text{ dBm}$ ($\approx 200\text{ mW}$).
*   **Spurious Emission Limits:** 3GPP TS 38.101-1 (Table 6.5.2.1-1) sets general out-of-band spurious emission limits at $-36\text{ dBm}$ ($< 1\text{ GHz}$) and $-30\text{ dBm}$ ($> 1\text{ GHz}$).
*   **Attenuation Calculation:**
    $$\text{Target Level} \le -37\text{ dBm} \implies \text{Required Attenuation} \ge 23\text{ dBm} - (-37\text{ dBm}) = 60\text{ dB}$$
    A $60\text{ dB}$ attenuation reduces a full $+23\text{ dBm}$ transmission down to $-37\text{ dBm}$ ($\approx 0.0002\text{ mW}$), attenuating radiated power below legal interference thresholds. Complete suppression to the ambient thermal noise floor ($-90\text{ dBm}$ to $-100\text{ dBm}$) would require $\approx 110\text{ dB}$ of isolation.

---

## 7. Clear Go / No-Go Recommendation

### **Recommendation: NO-GO**

MD1 must remain powered off in baseline state `md1:0`. No live power-on trial, IOCTL invocation, or regulator modification is permitted.

### Evidence Required to Re-evaluate NO-GO:
To reconsider a live, attended power-on trial in the future, the following concrete evidence must be established:
1. **Physical RF Shielding:** Physical placement of Lynx within an RF containment enclosure verified for $\ge 60\text{ dB}$ attenuation across cellular bands (600 MHz – 6 GHz), or verified physical disconnection of the antenna feeds.
2. **Attended Physical Tray Inspection:** Explicit confirmation by Noob verifying the physical dual-SIM tray has been removed and visually confirmed empty.
3. **PMIC Hardware Interlock Proof:** Device-tree or PMIC register analysis establishing whether the AP can enforce a hardware mask preventing the modem from asserting `mt6363_vrf*` rails.
4. **Baseband Firmware Entry Analysis:** Static analysis or symbolic decompilation of `md1img` entry routines confirming that RF transceiver initialization is strictly gated behind Handshake 2.
