# Lynx Battery Fuel Gauge Lifespan & Cycle Health Evaluator

Strict read-only evaluator for battery State of Health (SOH), 2S cell series balancing, and cycle degradation for the Texas Instruments BQ28Z610 gas gauge on the OnePlus Nord 3 (Dimensity 9000, MT6983).

## Hardware Components
- **Gas Gauge:** Texas Instruments BQ28Z610 on I2C7 @ 0x55 (`/sys/bus/i2c/devices/7-0055/battery_snapshot`).
- **Battery Pack:** 2S Li-ion series pack (5000 mAh dual-cell equivalent, ~7.4V nominal).
- **Evaluated Metrics:**
  - State of Health (SOH %): Full Charge Capacity vs Design Capacity.
  - Cell Balancing: Voltage delta between series cells $|V_{\text{cell1}} - V_{\text{cell2}}|$ ($\le 30\text{mV}$ nominal, $> 50\text{mV}$ warning, $> 100\text{mV}$ critical).
  - Cycle count and internal series impedance ($R_{\text{int}}$).

## Safety Boundaries
- **Strictly Offline by Default:** Use `--validate <FIXTURE>` to evaluate saved snapshots.
- **Double-Gated Live Mode:** Live queries require `--live --allow-live`.
- **Zero SBS Register Writes:** Never resets cycle counters, never modifies chemical profiles.

## Usage
```bash
# Validate offline snapshot (healthy state)
python3 lynx_battery_health.py --validate fixtures/battery-health-nominal.json

# Validate with JSON output
python3 lynx_battery_health.py --validate fixtures/battery-aging-warning.json --json

# Run unit tests
python3 -m unittest test_lynx_battery_health.py
```
