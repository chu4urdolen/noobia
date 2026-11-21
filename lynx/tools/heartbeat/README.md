# Lynx Autonomous Health Heartbeat Publisher

Publishes structured autonomous telemetry packets aggregating battery fuel gauge, thermal zones, survival policy state, and watchdog status for the OnePlus Nord 3 (`oplus6983_22823`).

## Usage

```bash
# Validate offline fixture
python3 lynx_heartbeat.py --validate fixtures/heartbeat-payload-nominal.json

# Emit simulated packet to stdout
python3 lynx_heartbeat.py --emit

# Live read-only interrogation (requires double gate)
python3 lynx_heartbeat.py --live --allow-live
```
