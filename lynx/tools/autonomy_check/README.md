# Lynx Untethered Autonomy Readiness Checklist

Unified preflight tool verifying that all 6 system safety gates (Battery, Cell Balancing, Thermals, UFS Health, Watchdog, Survival Engine) are satisfied before cutting the tether on the OnePlus Nord 3 (`oplus6983_22823`).

## Usage

```bash
# Validate offline fixture
python3 lynx_autonomy_preflight.py --validate fixtures/autonomy-readiness-ready.json

# Run live readiness audit (requires double gate)
python3 lynx_autonomy_preflight.py --live --allow-live
```
