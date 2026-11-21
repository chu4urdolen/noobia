# Lynx Untethered Autonomy Readiness Preflight Checklist

**Subsystem:** Untethered Execution & System Independence Verification
**Platform:** OnePlus Nord 3 (`oplus6983_22823`)
**Author:** Banshee (Spirit of Initiative 💙)
**Date:** 2026-11-21
**Directory:** `lynx/tools/autonomy_check/`

---

## 1. Objective & Readiness Gates

Before disconnecting Lynx from tethered terminal monitoring, the system must satisfy six strict hardware and software prerequisites. The `lynx_autonomy_preflight.py` tool audits all six gates to deliver a deterministic verdict: `READY_FOR_AUTONOMY`, `AUTONOMY_DEGRADED`, or `BLOCKED`.

### 1.1 The Six Autonomy Gates

| Gate # | Subsystem | Requirement | Pass Threshold | Fail / Block Threshold |
|---|---|---|---|---|
| **Gate 1** | Battery Capacity | State of Charge (SoC) % | $\ge 50\%$ | $< 25\%$ (Blocked) |
| **Gate 2** | Cell Balancing | 2S Series Cell Voltage Delta | $\Delta V \le 50\text{mV}$ | $\ge 100\text{mV}$ (Fire/Explosion Hazard) |
| **Gate 3** | Thermal Envelope | Shell Temp & SoC Junction Temp | $T_{\text{shell}} < 40^\circ\text{C}$, $T_{\text{soc}} < 75^\circ\text{C}$ | $T_{\text{shell}} \ge 45^\circ\text{C}$ or $T_{\text{soc}} \ge 105^\circ\text{C}$ |
| **Gate 4** | Storage Health | UFS 3.1 Health Descriptors | `bPreEOLInfo` == 1, Life Time Est $\le 7$ | `bPreEOLInfo` $\ge 3$ or Life Time Est $\ge 10$ |
| **Gate 5** | Watchdog Recovery | MTK-WDT TOPRGU Configuration | Configured timeout $\le 32\text{s}$, petting $\le 10\text{s}$ | Watchdog driver unbound or timeout $> 32\text{s}$ |
| **Gate 6** | Survival Engine | Policy Decision Engine Status | Evaluates to `NOMINAL_OPERATION` | Evaluates to `EMERGENCY_SHUTDOWN` |
| **Gate 7** | Actuation Interlocks (B36) | Live Actuation Override & Hardware E-Stop | Switch absent, service stoppable, Alert Slider checked | Override switch present (Locks actuation to `simulated: true`) |

---

### 1.2 Gate 7 Details: Hardware Actuation Guard (B36)

Before moving any survival action from simulated mode (`simulated: true`) to live execution on the physical phone, Gate 7 must be verified per `LYNX-SURVIVAL-LOCAL-OVERRIDE-DESIGN-20261121.md`:
1. **Layer 1 (File Switch):** `/etc/lynx/disable-survival-actuation` blocks any hardware actuation.
2. **Layer 2 (Service E-Stop):** Clean OpenRC daemon termination (`rc-service lynx-survivald stop`) within 2 seconds.
3. **Layer 3 (Physical E-Stop):** Alert Slider (tri-state key) position check; SILENT position locks out autonomous sleep/shutdown.

---

## 2. Verdict Classifications

- **`READY_FOR_AUTONOMY` (Exit Code 0):** Gates 1-6 pass cleanly (and Gate 7 verified if live actuation is enabled). The phone is cleared to execute unattended background autonomous loops.
- **`AUTONOMY_DEGRADED` (Exit Code 0):** All safety gates pass, but operational warnings exist (e.g., battery between 25% and 50%, or shell temperature between 40°C and 42°C). Autonomous operation permitted with throttled duty cycle.
- **`BLOCKED` (Exit Code 1):** One or more critical safety gates breached. Cutting the tether is strictly prohibited.
