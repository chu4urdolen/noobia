# Lynx Camera Sensor Dependency & Failure Map

This directory provides offline analysis, comparison, and gate verification tooling for the four camera sensors on Lynx (OnePlus 11R 5G / MT6895 / 22823 platform).

## Purpose

Enforces strict hardware and architectural boundaries across all four camera sensors:
1. **Macro (GC02M1)**: Single-cell Bayer `1600x1200 BA81` (RGGB phase) via `seninf-1` -> `CAMSV-0`. Proved in RAM with recognized optical frames under request-scoped `mtk_hdr_ae` controls.
2. **Wide (IMX355)**: Single-cell Bayer `3264x2448 BA81` via `seninf-2` -> `CAMSV-0`. Proved frame completion in RAM (`7,990,296` bytes).
3. **Main (IMX890)**: 50MP Four-cell Quad Bayer via MIPI C-PHY on `seninf-3`. Untested hardware. Hard-refused by `lynx_camera_gate.py`.
4. **Front (S5K3P9SP)**: 16MP Four-cell Tetracell via `seninf-0`. Untested hardware. Hard-refused by `lynx_camera_gate.py`.

## Usage

```bash
# Dump camera dependency map and verify alignment with lynx_camera_gate.py
python3 lynx_camera_dependency_map.py

# Run unit tests
python3 test_lynx_camera_dependency_map.py
```
