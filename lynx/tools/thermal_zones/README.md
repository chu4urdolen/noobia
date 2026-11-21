# Lynx Thermal Mitigation Zones & Trip Points Validator

Strict read-only preflight validator and telemetry evaluator for SoC (LVTS) and board-level (PMIC NTC shell) thermal zones on the OnePlus Nord 3 (Dimensity 9000, MT6983).

## Hardware Components
- **MediaTek Low Voltage Thermal Sensor (LVTS):**
  - `lvts 0`: `soc_max` (critical trip 116.5°C, hysteresis 2.0°C)
  - `lvts 6, 8`: Cortex-X2 prime/super-big core (`cpu_bigbig`)
  - `lvts 1..5, 7`: Cortex-A710 performance cores (`cpu_big1..6`)
  - `lvts 9..12`: Cortex-A510 efficiency cores (`cpu_little1..4`)
- **Chassis / Skin Thermal Sensor:**
  - `shell_temp` / `quiet_ntc`: PMIC AUXADC_VIN5 with 100K NTC pull-up resistor.
  - Passive throttling trip: 42.0°C.
  - Critical skin cutoff: 45.0°C.

## Safety Boundaries
- **Strictly Offline by Default:** Use `--validate <FIXTURE>` to evaluate saved snapshots.
- **Double-Gated Live Mode:** Live queries require `--live --allow-live`.
- **Zero Governor Modification:** Never alters cooling device bindings or governor policies.

## Usage
```bash
# Validate offline snapshot (nominal state)
python3 lynx_thermal_zones_validator.py --validate fixtures/thermal-nominal-quiescent.json

# Validate with JSON output
python3 lynx_thermal_zones_validator.py --validate fixtures/thermal-throttled-passive.json --json

# Run unit tests
python3 -m unittest test_lynx_thermal_zones_validator.py
```
