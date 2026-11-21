# Lynx Camera Sensor Dependency & Failure Map

This directory provides offline analysis, comparison, and gate verification tooling for the four camera sensors on Lynx (OnePlus Nord 3 5G CPH2493 / MT6983 / project 22823 "Vitamin").

## Purpose

Enforces strict hardware and architectural boundaries across all four camera sensors:
1. **Macro (GC02M1)**: Single-cell Bayer `1600x1200 BA81` (RGGB phase) via `seninf-1` -> `CAMSV-0`. Proved in RAM with recognized optical frames under request-scoped `mtk_hdr_ae` controls.
2. **Wide (IMX355)**: Single-cell Bayer `3264x2448 BA81` via `seninf-2` -> `CAMSV-0`. Proved frame completion in RAM (`7,990,296` bytes).
3. **Main (IMX890)**: 50MP Four-cell Quad Bayer via MIPI C-PHY on `seninf-3`. Untested hardware. Hard-refused by `lynx_camera_gate.py`.
4. **Front (S5K3P9SP)**: 16MP Four-cell Tetracell via `seninf-0`. Untested hardware. Hard-refused by `lynx_camera_gate.py`.

The aux-camera pair (IMX355 + GC02M1) has a dedicated bring-up preflight gate: `lynx_aux_camera_preflight.py` (Round 6, item D19).

## Usage

```bash
# Dump camera dependency map and verify alignment with lynx_camera_gate.py
python3 lynx_camera_dependency_map.py

# Run IMX890 main camera bring-up preflight against offline fixture
python3 lynx_imx890_preflight.py fixtures/imx890-preflight-unbound.json

# Run S5K3P9SP front camera bring-up preflight against offline fixture
python3 lynx_s5k3p9sp_preflight.py fixtures/s5k3p9sp-preflight-unbound.json

# Perform read-only live query of running DT & sysfs on Lynx (requires both flags)
python3 lynx_imx890_preflight.py --live --allow-live
python3 lynx_s5k3p9sp_preflight.py --live --allow-live

# Run aux camera (IMX355 ultrawide + GC02M1 macro) preflight against offline fixture
python3 lynx_aux_camera_preflight.py fixtures/aux-cameras-preflight-unbound.json

# Perform read-only live query of aux camera DT & sysfs on Lynx (requires both flags)
python3 lynx_aux_camera_preflight.py --live --allow-live

# Run camera dependency & preflight unit tests
python3 test_lynx_camera_dependency_map.py
python3 test_lynx_imx890_preflight.py
python3 test_lynx_s5k3p9sp_preflight.py
python3 test_lynx_aux_camera_preflight.py
```
