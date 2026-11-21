# Lynx Autonomous Thermal & Battery Survival Engine

**Subsystem:** Autonomous Fail-Safe Power & Thermal Survival Decision Engine
**Platform:** OnePlus Nord 3 (`oplus6983_22823` / MT6983 Dimensity 9000)
**Author:** Banshee (Spirit of Initiative 💙)
**Date:** 2026-11-21
**Directory:** `lynx/tools/survival/`

---

## 1. Objective & Autonomy Requirements

When Lynx operates untethered without continuous SSH supervision by a human operator, the system must autonomously govern its operational state to prevent two catastrophic failure modes:
1. **Uncontrolled Thermal Runaway:** Exceeding skin temperature thresholds (45°C cutoff) or silicon junction limits (`soc_max` 116.5°C).
2. **Brownout Hard Shutdowns:** Exhausting the battery to 0% under CPU load, which can trigger mid-write UFS 3.1 filesystem corruption.

---

## 2. Integrated Decision Matrix

The survival engine aggregates inputs from three hardware subsystems:
- **Battery Fuel Gauge:** TI BQ28Z610 on I2C7 @ `0x55` (State of Charge %, cell balancing delta, battery health).
- **Fast Charger:** MT6375 sub-PMIC on I2C5 @ `0x34` (SuperVOOC charging status, input current).
- **Thermal Mitigation:** MediaTek LVTS SoC channels 0..12 and PMIC AUXADC VIN5 chassis NTC (`shell_temp` / `quiet_ntc`).

| System State | Battery Level | Chassis NTC (`shell_temp`) | SoC Die (`soc_max`) | Autonomous Action |
|---|---|---|---|---|
| **`NOMINAL_OPERATION`** | $> 25\%$ | $< 40.0^\circ\text{C}$ | $< 75.0^\circ\text{C}$ | Full agent capability. Fast charging permitted if plugged in. |
| **`THERMAL_THROTTLE`** | Any | $40.0^\circ\text{C} - 44.9^\circ\text{C}$ | $75.0^\circ\text{C} - 94.9^\circ\text{C}$ | CPU governor to `powersave`. Throttle fast charging to $\le 500\text{mA}$ or pause charging. |
| **`LOW_POWER_SUSPEND`** | $6\% - 15\%$ | $< 45.0^\circ\text{C}$ | $< 95.0^\circ\text{C}$ | Quiesce heavy workloads. Enter SCP low-power island sleep (`mtk_lpm`). Wi-Fi beacon keepalive only. |
| **`EMERGENCY_SHUTDOWN`**| $\le 5\%$ | $\ge 45.0^\circ\text{C}$ | $\ge 105.0^\circ\text{C}$ | Immediate graceful `sync` and unmount of UFS storage; clean shutdown to protect battery chemistry and silicon. |

---

## 3. Preflight & Safety Invariants

- **Offline Simulation:** Evaluates telemetry payloads against deterministic state machine rules.
- **Strict Read-Only Collector:** When `--live --allow-live` is specified, passively reads sysfs and fuel gauge telemetry. Zero sysfs power writes, zero governor changes, zero system shutdown invocations during preflight inspection.
