# Lynx Second Rear Light Topology Gate

This directory contains offline device-tree and kernel driver topology analysis tools for evaluating rear flashlight light sources on Lynx (OnePlus Nord 3 5G CPH2493 / MT6983 / project 22823 "Vitamin").

## Purpose

Enforces strict, source-cited determination of flashlight channel availability:
- Proves whether an independent second rear light source / channel exists in device tree or driver control structures.
- Strictly read-only: issues zero I2C transactions, zero module loads, and zero sysfs writes.

## Usage

```bash
# Evaluate device tree topology fixture
python3 lynx_second_light_gate.py fixtures/lynx-22823-flashlight-dt.json

# Run unit tests
python3 test_lynx_second_light_gate.py
```
