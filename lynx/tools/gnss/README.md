# Lynx GNSS Fix-Trial Readiness Tools

This directory provides offline analysis, readiness evaluation, and gated live collection for GNSS fix trials on Lynx (OnePlus Nord 3 5G CPH2493 / MT6983 / project 22823 "Vitamin").

## Purpose

Enforces strict hardware, power, driver, and sky-view readiness boundaries before live attended GNSS trials:
1. **Power & Thermal Safety Gate**: Verifies battery capacity >= 20% (cutoff) / >= 35% (nominal), voltage >= 7400 mV, temperature <= 40°C, and zero gauge read errors.
2. **Driver & Device Node Gate**: Audits presence of `conninfra`, `connadp`, `gps_drv`, `/dev/stpgps`, and `/dev/ccci_c2k_agps`.
3. **Sky-View & Signal Gate**: Validates >= 4 tracking satellites in view, C/No >= 28 dB-Hz, and HDOP <= 4.0.
4. **NMEA Receipt Integrity**: Parses and verifies checksums, fix quality (GGA >= 1), and valid navigation status (RMC 'A').

Aria runs the actual live fix trial.

## Usage

```bash
# Run readiness evaluator against offline fixture
python3 lynx_gnss_readiness.py fixtures/gnss-readiness-quiescent.json

# Perform read-only live query of running state on Lynx (requires both flags)
python3 lynx_gnss_readiness.py --live --allow-live

# Run unit tests
python3 test_lynx_gnss_readiness.py
```
