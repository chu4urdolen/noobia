# Lynx Autonomous Health Heartbeat Payload Generator and Validator

Generates and validates structured autonomous health telemetry payloads aggregating battery fuel gauge, thermal zones, survival policy state, and watchdog status for the OnePlus Nord 3 (`oplus6983_22823`).

**Note on Scope:** This tool is a payload formatter and schema validator (payload-only). It formats telemetry dictionaries, validates them against the autonomous health heartbeat schema, and prints JSON to stdout (`--emit`) or inspects read-only state via double-gated SSH (`--live --allow-live`). It does not run a standing daemon, broadcast UDP packets, or transmit over the network.

## Usage

```bash
# Validate offline fixture
python3 lynx_heartbeat.py --validate fixtures/heartbeat-payload-nominal.json

# Emit simulated packet to stdout
python3 lynx_heartbeat.py --emit

# Live read-only interrogation (requires double gate)
python3 lynx_heartbeat.py --live --allow-live
```
