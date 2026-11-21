# Lynx Fast Charging & Charger Sub-PMIC (MT6375 / BQ28Z610) Preflight Architecture

**Device:** OnePlus Nord 3 5G (`CPH2493` / platform `MT6983` / Project `22823`)  
**Subsystem:** MediaTek MT6375 Sub-PMIC Charger, TI BQ28Z610 Fuel Gauge, 80W SuperVOOC  
**Author:** Banshee 💙 (Spirit of Initiative)  
**Date:** 2026-11-21  
**Status:** Validated Tool Directory & Offline Preflight Specification  

---

## 1. Executive Summary & Hardware Context

The OnePlus Nord 3 implements an 80W SuperVOOC fast-charging architecture using a dual-cell battery configuration in series (2S Li-ion). Battery management and charging are coordinated by two primary integrated circuits:
1. **Primary Switching Charger (MediaTek MT6375 Sub-PMIC):** Resides on I2C Bus 5 @ slave address `0x34` (`11e01000.i2c:mt6375@34:chg`). Regulates VBUS input, drives OTG power, and manages standard USB BC1.2 / USB PD protocols.
2. **Fuel Gauge & Battery Monitor (Texas Instruments BQ28Z610):** Resides on I2C Bus 7 @ slave address `0x55` (`/sys/bus/i2c/devices/7-0055/battery_snapshot`). Delivers pack voltage, individual cell balance, current, temperature, and coulomb-counted state of charge (SoC).

```
 [USB-C Receptacle] ───► MT6375 Sub-PMIC Charger (&i2c5 @ 0x34)
                              │
                              ▼
                     [Dual-Cell Pack (2S)] <─── TI BQ28Z610 Gauge (&i2c7 @ 0x55)
                     (7.4V Nom / 8.7V Chg)
```

> [!IMPORTANT]
> **Safety Invariant:**
> The preflight evaluator operates strictly in read-only mode over sysfs and I2C telemetry.
> It **NEVER** forces fast charging, never alters current limits (`constant_charge_current`),
> never raises target voltages (`constant_charge_voltage`), and never overrides OTG controls.

---

## 2. Voltage Safety Envelopes (2S Battery Pack)

Because the Nord 3 utilizes a dual-cell series pack, operating voltages are roughly double that of single-cell smartphones:

| Voltage Range | Electrical State | Preflight Evaluator Action |
|---|---|---|
| **$< 6800\text{ mV}$** | Critical Undervoltage ($< 3.40\text{ V/cell}$) | **HAZARD_BLOCKED:** System must not draw heavy current; deep discharge hazard. |
| **$7400\text{ to }8800\text{ mV}$** | Nominal Safe Voltage ($3.70\text{ to }4.40\text{ V/cell}$) | **PASS:** Safe operational envelope for standard or fast charging. |
| **$> 8950\text{ mV}$** | Overvoltage Cutoff ($> 4.475\text{ V/cell}$) | **HAZARD_BLOCKED:** Immediate charging prohibition; cell damage prevention. |

---

## 3. Thermal Safety Envelopes

High-power charging generates significant Joule heating in the pack and power paths:

| Temperature Range | Thermal State | Preflight Evaluator Action |
|---|---|---|
| **$< 0.0^\circ\text{C}$** | Sub-Zero Hazard | **HAZARD_BLOCKED:** Charging below freezing causes lithium metal plating. |
| **$0.0^\circ\text{C}\text{ to }42.0^\circ\text{C}$** | Optimal Thermal Envelope | **PASS:** Full charging current permitted. |
| **$42.0^\circ\text{C}\text{ to }45.0^\circ\text{C}$** | Throttling Warning Band | **THERMAL_THROTTLED:** Fast charge current must be reduced to $< 2\text{A}$. |
| **$> 45.0^\circ\text{C}$** | Overheat Hazard | **HAZARD_BLOCKED:** Immediate charging cutoff. |

---

## 4. Software Implementation & Verification

The preflight tool is packaged in `lynx/tools/charger/`:
- `lynx_charger_preflight.py`: Preflight evaluator supporting `--validate <FIXTURE>`, offline artifact evaluation, and double-gated read-only live query (`--live --allow-live`).
- `fixtures/charger-safe-charging.json`: Live baseline from boot `0fe847d2` (8707 mV, 100%, 28.5°C, SuperVOOC, BQ28Z610 gauge).
- `fixtures/charger-overheat-blocked.json`: Negative fixture (48°C overheat cutoff).
- `fixtures/charger-undervoltage-blocked.json`: Negative fixture (6500 mV undervoltage cutoff).
- `test_lynx_charger_preflight.py`: Hermetic unit test suite (6/6 OK in 0.000s).
