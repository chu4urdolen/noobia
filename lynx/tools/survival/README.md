# Lynx Autonomous Survival Engine

Decision engine evaluating multi-sensor thermal and power telemetry to enforce autonomous self-preservation policies (nominal, thermal throttling, low-power suspend, emergency shutdown) on the OnePlus Nord 3 (`oplus6983_22823`).

## Usage

```bash
# Validate offline fixture
python3 lynx_survival_engine.py --validate fixtures/survival-state-nominal.json

# Read-only live evaluation (requires double gate)
python3 lynx_survival_engine.py --live --allow-live
```
