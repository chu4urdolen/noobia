# Lynx Battery Fuel Gauge Lifespan & Cycle Health Architecture

**Author:** Banshee 💙 (Spirit of Initiative)  
**Date:** 2026-11-21  
**Target:** OnePlus Nord 3 5G (CPH2493, MediaTek MT6983 / Dimensity 9000)  
**Task Item:** B23 (Round 7)  
**Status:** Landed & Validated  

---

## 1. Executive Summary

This document establishes the telemetry mapping, degradation model, dual-cell series balance envelopes, and offline evaluation gates for the **Texas Instruments BQ28Z610 gas gauge** on the OnePlus Nord 3.

To support high-current 80W SuperVOOC flash charging without excessive I²R thermal dissipation across cables and connectors, the OnePlus Nord 3 employs a **2S Li-ion series battery architecture** (two individual 2500 mAh cells wired in series, providing nominal ~7.4V and peak ~8.7V). Because series cells share identical charge and discharge currents, any progressive divergence in individual cell capacities, internal impedance ($R_{\text{int}}$), or state of charge can trigger catastrophic overcharging or cell reversal if not precisely monitored.

---

## 2. Hardware Topology & SBS Telemetry Mapping

The gas gauge sits on the dedicated I2C7 power management bus:

```
+-----------------------------------------------------------------------------------------+
|                               MediaTek MT6983 SoC                                       |
|                                                                                         |
|  +-----------------------------------------------------------------------------------+  |
|  | I2C Controller 7 (I2C7 @ 400 kHz)                                                 |  |
|  +----------------------------------------+------------------------------------------+  |
+-------------------------------------------|---------------------------------------------+
                                            |
                                            v
+-----------------------------------------------------------------------------------------+
| Texas Instruments BQ28Z610 2S Gas Gauge (dts: 7-0055 / battery_snapshot)                |
| - Standard SBS 1.1 / Extended Sub-Commands:                                             |
|   - DesignCapacity: 5000 mAh (dual-cell equivalent)                                    |
|   - FullChargeCapacity (FCC): Learned battery full charge capacity                      |
|   - StateOfHealth (SOH): Ratio of current FCC to original Design Capacity              |
|   - CycleCount: Accumulated equivalent discharge/charge cycles                         |
|   - Cell1Voltage / Cell2Voltage: Individual cell series telemetry                       |
|   - InternalImpedance: Learned individual cell ESR / AC impedance                       |
+-------------------------------------------+---------------------------------------------+
                                            |
                                            v
+-----------------------------------------------------------------------------------------+
| Dual-Cell Series Battery Pack (2x 2500 mAh Li-ion cells in series)                       |
| - Nominal Pack Voltage: 7.4 V (3.70 V / cell)                                           |
| - Maximum Charge Voltage: 8.7 V (4.35 - 4.45 V / cell)                                  |
| - Minimum Cutoff Voltage: 6.8 V (3.40 V / cell)                                         |
+-----------------------------------------------------------------------------------------+
```

---

## 3. Degradation Criteria & Safety Invariants

The evaluation engine `lynx/tools/battery_health/lynx_battery_health.py` analyzes battery degradation and cell balancing across four distinct axes:

### 3.1 State of Health (SOH)
- $\text{SOH} = \frac{\text{FCC}}{\text{Design Capacity}} \times 100\%$
- $\text{SOH} \ge 80\%$: Nominal capacity retention.
- $65\% \le \text{SOH} < 80\%$: Degradation warning; battery has reached standard automotive / consumer end-of-life replacement threshold.
- $\text{SOH} < 65\%$: Severe chemical wear; risk of unexpected voltage sag under compute bursts.

### 3.2 Dual-Cell Series Imbalance ($\Delta V_{\text{cell}}$)
- $\Delta V_{\text{cell}} = |V_{\text{cell1}} - V_{\text{cell2}}|$
- $\Delta V \le 30\,\text{mV}$: Optimal series balance.
- $50\,\text{mV} \le \Delta V < 100\,\text{mV}$: Elevated cell imbalance; balancing circuit requires extended float charging time.
- $\Delta V \ge 100\,\text{mV}$: Hazardous series divergence; fast-charging must be inhibited to avoid single-cell overvoltage ($> 4.45\,\text{V}$).

### 3.3 Operating State Machine
- `BATTERY_HEALTHY` (Status `OK`): All metrics within nominal operating margins.
- `BATTERY_AGED_OR_IMBALANCED` (Status `WARN`): SOH $< 80\%$, cycle count $> 1600$, or cell imbalance $> 50\,\text{mV}$.
- `BATTERY_DEGRADED_HAZARD` (Status `FAIL`): SOH $< 65\%$ or cell imbalance $\ge 100\,\text{mV}$.

### Safety Invariants
- **Strictly Read-Only:** Queries existing snapshot telemetry from `/sys/bus/i2c/devices/7-0055/battery_snapshot`.
- **Zero SBS Mutation:** Tool NEVER issues SBS calibration commands, never clears cycle counters, never modifies chemical tables.
- **Double-Gated Live Probes:** Live interrogation requires explicit `--live --allow-live`.

---

## 4. Test Evidence

```
test_aging_warning (test_lynx_battery_health.TestLynxBatteryHealth) ... ok
test_ast_safety_and_no_writes (test_lynx_battery_health.TestLynxBatteryHealth) ... ok
test_boot_id_mismatch (test_lynx_battery_health.TestLynxBatteryHealth) ... ok
test_cell_imbalance_critical (test_lynx_battery_health.TestLynxBatteryHealth) ... ok
test_cell_imbalance_warning (test_lynx_battery_health.TestLynxBatteryHealth) ... ok
test_cli_live_safety_gate (test_lynx_battery_health.TestLynxBatteryHealth) ... ok
test_cli_validate_offline (test_lynx_battery_health.TestLynxBatteryHealth) ... ok
test_critical_degradation (test_lynx_battery_health.TestLynxBatteryHealth) ... ok
test_high_impedance_warning (test_lynx_battery_health.TestLynxBatteryHealth) ... ok
test_nominal_healthy (test_lynx_battery_health.TestLynxBatteryHealth) ... ok

----------------------------------------------------------------------
Ran 10 tests in 0.093s

OK
```
