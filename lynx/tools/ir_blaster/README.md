# Lynx Infrared (IR) Blaster Preflight Gate

Strict read-only preflight and topology validator for the Consumer IR (CIR) transmitter / IR blaster on the OnePlus Nord 3 (Dimensity 9000, MT6983).

## Hardware Components
- **Device Tree Nodes:**
  - `consumerIr`: `status = "okay"`, `compatible = "oplus,kookong_ir_pwm"`
  - `consumer_ir_core`: `status = "okay"`, `compatible = "oplus,kookong_ir_core"`
- **Hardware Architecture:** MediaTek SoC PWM modulator, KooKong IR PWM protocol controller.
- **Operating Frequencies:** 30 kHz to 60 kHz (standard 38 kHz NEC/RC5 carrier).
- **Device Node:** `/dev/ir_remote` (read-only enumeration).

## Safety Boundaries
- **Strictly Offline by Default:** Use `--validate <FIXTURE>` to evaluate saved snapshots.
- **Double-Gated Live Mode:** Live queries require `--live --allow-live`.
- **Zero Optical Emission:** Never transmits IR bursts, never modifies carrier frequencies or PWM duty cycles, zero module loads.

## Usage
```bash
# Validate offline snapshot (bound state)
python3 lynx_ir_blaster_preflight.py --validate fixtures/ir-blaster-bound.json

# Validate with JSON output
python3 lynx_ir_blaster_preflight.py --validate fixtures/ir-blaster-bound.json --json

# Run unit tests
python3 -m unittest test_lynx_ir_blaster_preflight.py
```
