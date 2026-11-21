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
install.

- Evaluator (`portable_health.py`): done, 62 offline fixture tests.
- Collector (`lynx_health_collect.py`): done, 35 offline fixture tests. It
  runs **three** bounded, read-only commands on Lynx over the pinned SSH
  route, sharing one total timeout budget:
  1. `/usr/local/bin/lynx-status` — the phone's status JSON (schema 2) ->
     the common facts (battery, thermal, storage, network, services);
  2. `/usr/local/bin/lynx-platform-status cellular` — the read-only CCCI
     inventory -> `machine.lynx.modem_md1_state` (MD1 boot code from
     `/sys/kernel/ccci/boot`; no CCCI ioctl, no radio);
  3. `/usr/local/bin/lynx-agent-health` — the read-only scan of
     `/var/lib/lynx-agent` -> `machine.lynx.pending`, `running`,
     `oldest_pending_seconds`.

  Live captures (verdict ok, exit 0): `examples/lynx-live-20261121.json`
  (the interim collector that left modem/queue `unknown`) and
  `examples/lynx-live-20261121-full.json` (all seven checks evaluated).
  Nexus GPU/RAM/SMART collection stays with Aigel's board.
- Report diff (`portable_health_diff.py`): offline, bounded diff of two
  **saved** evaluator reports — changed check statuses, new unknowns,
  resolved unknowns, added/removed checks, verdict change. Reads only the
  two given files (512 KiB cap each, 256-check cap), never contacts a
  machine, no periodic job.
  Suite: 114 offline fixture tests.

## Usage

```sh
python3 lynx/tools/health/portable_health.py --snapshot examples/lynx-warn.json --text
python3 lynx/tools/health/portable_health.py --snapshot - < examples/lynx-healthy.json
python3 lynx/tools/health/portable_health.py --snapshot snap.json --max-age 3600
```

Exit codes: `0` ok, `1` warn, `2` fail, `3` all checks unknown,
`4` invalid snapshot/schema.

### Diffing two saved reports (offline)

```sh
python3 lynx/tools/health/portable_health_diff.py report-early.json report-late.json
python3 lynx/tools/health/portable_health_diff.py report-early.json report-late.json --json
```

Exit codes: `0` diff computed (whether or not anything changed),
`2` usage error, `4` invalid report (schema, shape, or size/check bounds).

### Collecting a snapshot from Lynx (read-only)

```sh
# One bounded, read-only command on Lynx (pinned key, port 2222, BatchMode):
python3 lynx/tools/health/lynx_health_collect.py            # snapshot JSON
python3 lynx/tools/health/lynx_health_collect.py --evaluate # verdict; exit = verdict
python3 lynx/tools/health/lynx_health_collect.py --evaluate --max-age 300
```

Guarantees: per-command (15 s default) and total (45 s default) timeouts —
the three commands share **one** total deadline, so when the budget is
spent the remaining commands are skipped and their facts stay absent;
stdout capped (12000 chars default); no writes, no prompts, no interactive
input (BatchMode). A missing, failing, timed-out, runner-error, or
unparseable source leaves that section of `facts` **absent**, so the
evaluator reports `unknown`, never `ok` — nothing is fabricated. No
exception from the runner escapes `collect()` (Aria #103): a runner
failure is recorded on the command entry and its facts stay absent.
The runner is injectable, which is how the tests stay offline.
`--evaluate` exit codes match the evaluator's (0/1/2/3/4).

Collector limits (honest, current):

- `charging` is not reported by `lynx-status`; the field stays absent.
- `used_percent` is not reported; storage is judged on free space.
- `link_state` reflects the **wifi interface** as Lynx reports it; a USB
  link (if the host reached Lynx over USB) is not observable from this
  snapshot, so `carrier: false` maps to `link_state: none` (fail) even if
  the SSH hop itself went over USB.
- `throttled` is derived from a nonzero cpufreq cooling state; absence of
  cooling data means the flag is absent, not false.
- The output cap clips captured stdout, but `subprocess.run` buffers the
  complete output first (Aria #103): memory is not strictly bounded by
  `max_output` for a pathological command. The three commands are the
  phone's own bounded status tools, so the cap is a guard, not a memory
  guarantee.
- `modem_md1_state` comes from the CCCI **boot evidence**
  (`/sys/kernel/ccci/boot`); the phone reports `validated: false`. It is
  interface evidence, not proof of a working modem — no CCCI ioctl, no
  radio, consistent with the MD1 no-go.
- Agent-queue `stopped` and `issues` are context notes, not judged facts;
  only `counts.pending/running` and `oldest_pending_seconds` are mapped,
  and only when they are well-typed non-negative integers.
  Phone-side `error` objects are rejected the same way.

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
    "services": {"required": ["lynx-health", "lynx-battery-reserve", "..."],
                 "running": ["lynx-health", "..."], "failed": []}
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
