# Lynx Bluetooth Acceptance Gate

This directory contains offline validation tooling for Bluetooth cold-boot and sustained-uptime trials on the OnePlus 11R 5G (Lynx / MT6895 platform).

## Purpose

Enforces strict acceptance gates on Bluetooth trial receipts without issuing network calls or device mutations:
1. **Fresh Boot ID**: Proves evidence originates from a new boot cycle rather than stale logs or prior sessions.
2. **Sustained System Health**: Enforces unbroken healthy status samples across the trial hold (zero issues, battery $\ge 15\%$, temperature $< 55^\circ\text{C}$).
3. **Verified Radio Teardown**: Confirms radio power-off at trial completion (`rc-service lynx-bluetooth stop` succeeded, `hci0` removed).
4. **Bounded Recovery Boundary**: Proves zero partition writes, zero runlevel alterations, and disarmed watchdogs.

## Usage

```bash
# Evaluate a trial receipt
python3 lynx_bt_acceptance_gate.py fixtures/passing-trial-receipt.json --reference-boot-id "<prior-boot-uuid>"

# Run unit tests
python3 test_lynx_bt_acceptance_gate.py
```
