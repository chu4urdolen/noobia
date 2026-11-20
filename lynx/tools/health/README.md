# Lynx health — portable passive diagnostics

First deliverable of Solo Dushich's Lynx lane (team handoff 2026-11-21):
portable passive diagnostics in the spirit of Aigel's vitals board, but
built to be **portable and offline**:

- `portable_health.py` is a pure evaluator. It takes a **captured snapshot**
  (JSON of observed facts), judges it against per-profile checks, and prints
  a compact verdict. It never opens a network connection, never reads a live
  device, and never spawns a process — so it runs identically on Nexus, on
  Lynx, or in a test.
- **Common checks** (battery, thermal, storage, network, services) are
  machine-agnostic. A **profile** selects which apply: Lynx declares a
  battery, a desktop does not.
- **Machine-specific checks** live separately: Lynx gets modem MD1 state
  (no-SIM policy) and agent-queue liveness; the Nexus profile keeps GPU,
  RAM, and SMART out of the common set, mirroring Aigel's thresholds.
- Missing facts are `unknown`, never `ok`. If every check is unknown the
  verdict is `unknown`.

## Status

Prototype. **Nothing here is installed on any device.** Aria reviews before
install. A snapshot collector (phone-side script or Nexus-side SSH capture)
is the follow-up; the snapshot schema is the seam for it.

## Usage

```sh
python3 lynx/tools/health/portable_health.py --snapshot examples/lynx-warn.json --text
python3 lynx/tools/health/portable_health.py --snapshot - < examples/lynx-healthy.json
python3 lynx/tools/health/portable_health.py --snapshot snap.json --max-age 3600
```

Exit codes: `0` ok, `1` warn, `2` fail, `3` all checks unknown,
`4` invalid snapshot/schema.

## Tests (offline, fixture-only)

```sh
python3 -m unittest discover -s lynx/tools/health -p 'test_*.py'
```

## Snapshot schema (v1)

```json
{
  "schema": "portable-health/1",
  "host": "lynx",
  "profile": "lynx",
  "captured_at": "2026-11-21T10:00:00+03:00",
  "facts": {
    "battery":  {"capacity_percent": 22, "current_ma": -151,
                 "charging": false, "temperature_mc": 24800,
                 "gauge_read_errors": 0},
    "thermal":  {"max_c": 31.2, "throttled": false},
    "storage":  {"used_percent": 41, "free_mib": 12345, "fs_errors": 0},
    "network":  {"link_state": "wifi", "carrier": true, "ipv4": "192.168.100.107"},
    "services": {"required": ["sshd", "lynx-noobd"],
                 "running": ["sshd", "lynx-noobd", "audio"], "failed": []}
  },
  "machine": {
    "lynx": {"modem_md1_state": 0, "pending": 0, "running": 0,
             "oldest_pending_seconds": 0}
  }
}
```

Every section and field is optional; a check without its facts reports
`unknown`. `profile` defaults to `host`; an unregistered host still
evaluates the common checks (facts-driven, self-limiting) and reports the
missing profile in its own check.

## Thresholds (Lynx profile)

| Check | ok | warn | fail |
| --- | --- | --- | --- |
| battery | ≥ 35% | 20–35% (trial-recheck band) | < 20% (reserve guard may power off, even while charging) |
| battery gauge | — | read errors > 0 | — |
| thermal | < 43 C | ≥ 43 C, or throttled | ≥ 50 C |
| storage | used < 85%, free ≥ 512 MiB | used ≥ 85% or free < 512 MiB | used ≥ 95%, free < 128 MiB, or fs_errors > 0 |
| network (wifi) | carrier + IPv4 | carrier, no IPv4 | no carrier, or link none |
| network (usb) | IPv4 present | no IPv4 (gadget may not be enumerated) | link none |
| services | all required running, none failed | — | required missing or failed |
| lynx_modem (no-SIM policy) | MD1 = 0 | MD1 ≠ 0 (confirm authorized trial) | — |
| lynx_agent_queue | counts fine | oldest pending > 1800 s | — |

Nexus profile (separate machine section): GPU warn ≥ 85 C / fail ≥ 95 C,
Xid events ≥ warn, uncorrectable ECC fail; RAM < 10% warn / < 2% fail;
SMART any FAILED device fail — the same conventions Aigel's board uses.

## Design notes

- **Bounded**: the text board truncates each line; JSON reports are small by
  construction (evidence is only what the snapshot carried).
- **Accurate**: an observed interface is never upgraded to a validated
  capability; this board reports state, and the handoff's receipts remain
  the source of what has been physically proven.
- **Staleness**: `--max-age` flags a report `stale` when `captured_at` is
  older than the window. A stale snapshot is context, not a live guarantee —
  the same rule CURRENT-HANDOFF.md applies to itself.
