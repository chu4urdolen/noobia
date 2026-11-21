# Lynx Fast Charging & Charger Sub-PMIC (MT6375 / BQ28Z610) Preflight Tool

Read-only offline validator and safe hardware state probe for the 80W SuperVOOC / USB PD charging subsystem on OnePlus Nord 3.

## Architectural Purpose
Enforces strict boundaries before any attended fast charging trial:
1. Validates dual-cell pack voltage within safe operational limits ($6800\text{ mV} \le V_{\text{pack}} \le 8950\text{ mV}$).
2. Validates battery temperature ($0^\circ\text{C} \le T \le 45^\circ\text{C}$), enforcing throttling above $42^\circ\text{C}$.
3. Verifies primary charger sub-PMIC node (`11e01000.i2c:mt6375@34:chg`) and TI BQ28Z610 fuel gauge (`7-0055/battery_snapshot`).
4. **Strict Non-Mutating Boundary:** Preflight operates strictly read-only. It NEVER forces charging states, never alters current/voltage limits, and never overrides OTG controls.

## Usage
- Validate fixture:
  `python3 lynx_charger_preflight.py --validate fixtures/charger-safe-charging.json`
- Live read-only check (double-gated):
  `python3 lynx_charger_preflight.py --live --allow-live`
