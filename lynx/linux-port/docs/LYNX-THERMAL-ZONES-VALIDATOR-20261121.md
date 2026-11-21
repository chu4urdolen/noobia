# Lynx Thermal Mitigation Zones & Trip Points Validator Architecture

**Author:** Banshee 💙 (Spirit of Initiative)  
**Date:** 2026-11-21  
**Target:** OnePlus Nord 3 5G (CPH2493, MediaTek MT6983 / Dimensity 9000)  
**Task Item:** B22 (Round 7)  
**Status:** Landed & Validated  

---

## 1. Executive Summary

This document establishes the hardware mapping, Device Tree sensor bindings, trip point temperature thresholds, and validation gates for the thermal mitigation subsystem on the OnePlus Nord 3.

The MediaTek Dimensity 9000 integrates an advanced multi-channel **Low Voltage Thermal Sensor (LVTS)** array distributed across CPU cores, GPU execution engines, APU compute tiles, and modem blocks. In parallel, OnePlus board-level thermal design incorporates precision Negative Temperature Coefficient (NTC) thermistors monitored by PMIC AUXADC channels to sense external chassis/skin surface temperatures.

---

## 2. Hardware Topology & Thermal Zone Mapping

From the kernel Device Tree (`mt6983.dts` and `cust_mt6983_vitamin_thermal.dtsi`), the thermal management infrastructure comprises both silicon-level and chassis-level zones:

```
+-----------------------------------------------------------------------------------------+
|                               MediaTek MT6983 SoC                                       |
|                                                                                         |
|  +-----------------------------------------------------------------------------------+  |
|  | Low Voltage Thermal Sensor (LVTS) Array (&lvts / thermal-zones)                   |  |
|  | - lvts 0: soc_max (Critical Trip: 116.5 C, Hysteresis: 2.0 C)                      |  |
|  | - lvts 6, 8: cpu_bigbig1, 2 (Cortex-X2 Prime Core @ 3.05 GHz)                      |  |
|  | - lvts 1..5, 7: cpu_big1..6 (Cortex-A710 Performance Cores @ 2.85 GHz)            |  |
|  | - lvts 9..12: cpu_little1..4 (Cortex-A510 Efficiency Cores @ 1.80 GHz)            |  |
|  +----------------------------------------+------------------------------------------+  |
+-------------------------------------------|---------------------------------------------+
                                            |
+-------------------------------------------v---------------------------------------------+
| OnePlus Board-Level Chassis / Skin Thermistor (&shell_temp / cust_mt6983_vitamin_thermal)|
| - Monitored by: pmic_adc channel 5 (AUXADC_VIN5 with 100K NTC resistor pull-up)         |
| - Feeds zone: &quiet_ntc                                                                |
| - Passive Throttling Trip Point: 42.0 C                                                 |
| - Maximum Safe Skin Cutoff / Charge Cutoff: 45.0 C                                      |
+-----------------------------------------------------------------------------------------+
```

### 2.1 Silicon-Level Zones (LVTS)
- **`soc_max`:** Aggregates peak junction temperature across the die.
  - Critical Trip: $116,500\,\text{m}^\circ\text{C}$ ($116.5^\circ\text{C}$) with $2,000\,\text{m}^\circ\text{C}$ hysteresis. Triggering initiates emergency hardware shutdown.
- **`cpu_bigbig` (Cortex-X2):** Primary thermal limiter under bursty single-threaded loads.
  - Warning Trip: $85,000\,\text{m}^\circ\text{C}$ ($85.0^\circ\text{C}$) triggers DVFS frequency capping.
  - Critical Trip: $105,000\,\text{m}^\circ\text{C}$ ($105.0^\circ\text{C}$).
- **`cpu_big` (Cortex-A710):** Sustained multi-threaded compute monitoring.

### 2.2 Board-Level Zone (`quiet_ntc` / `shell_temp`)
- Defined in `cust_mt6983_vitamin_thermal.dtsi`:
  - Calibration lookup table spans $-40^\circ\text{C}$ to $+125^\circ\text{C}$ across 166 calibrated voltage points.
  - Skin temperature directly dictates human safety comfort and fast-charging thermal back-off:
    - $T_{\text{skin}} \ge 42^\circ\text{C}$: SuperVOOC throttles from 80W down to standard USB PD / 15W.
    - $T_{\text{skin}} \ge 45^\circ\text{C}$: Charging is completely interrupted to prevent lithium battery degradation.

---

## 3. Preflight Validator & State Machine

The validator `lynx/tools/thermal_zones/lynx_thermal_zones_validator.py` evaluates thermal readings against hardware trip boundaries:

1. **`THERMAL_ENVELOPE_NOMINAL` (Status `OK`):**
   - Skin temperature $< 42^\circ\text{C}$.
   - SoC junction temperature $< 85^\circ\text{C}$.
   - Full compute capacity and maximum charging rate permitted.

2. **`THERMAL_THROTTLED_PASSIVE` (Status `WARN`):**
   - Skin temperature in $42^\circ\text{C} \le T < 45^\circ\text{C}$ throttling band, or CPU $\ge 85^\circ\text{C}$.
   - DVFS mitigation active; fast charging power curtailed.

3. **`THERMAL_CRITICAL_BLOCKED` (Status `FAIL`):**
   - Skin temperature $\ge 45^\circ\text{C}$ or SoC max $\ge 116.5^\circ\text{C}$.
   - Emergency cutoff active.

### Safety Invariants
- **Strictly Read-Only:** Queries thermal sysfs attributes (`/sys/class/thermal/thermal_zone*/temp`).
- **Zero Governor Modification:** Never commands frequency changes, never forces cooling devices, never mutates trip points.
- **Double-Gated Live Probes:** Live interrogation over SSH requires explicit `--live --allow-live`.

---

## 4. Test Evidence

```
test_ast_safety_and_no_writes (test_lynx_thermal_zones_validator.TestLynxThermalZonesValidator) ... ok
test_boot_id_mismatch (test_lynx_thermal_zones_validator.TestLynxThermalZonesValidator) ... ok
test_cli_live_safety_gate (test_lynx_thermal_zones_validator.TestLynxThermalZonesValidator) ... ok
test_cli_validate_offline (test_lynx_thermal_zones_validator.TestLynxThermalZonesValidator) ... ok
test_critical_trip (test_lynx_thermal_zones_validator.TestLynxThermalZonesValidator) ... ok
test_missing_zones_warning (test_lynx_thermal_zones_validator.TestLynxThermalZonesValidator) ... ok
test_nominal_quiescent (test_lynx_thermal_zones_validator.TestLynxThermalZonesValidator) ... ok
test_skin_critical_cutoff (test_lynx_thermal_zones_validator.TestLynxThermalZonesValidator) ... ok
test_soc_critical_cutoff (test_lynx_thermal_zones_validator.TestLynxThermalZonesValidator) ... ok
test_throttled_passive (test_lynx_thermal_zones_validator.TestLynxThermalZonesValidator) ... ok

----------------------------------------------------------------------
Ran 10 tests in 0.096s

OK
```
