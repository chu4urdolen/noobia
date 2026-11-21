# Lynx Watchdog Supervision & Petting Daemon (`lynx-watchdogd`)

**Device:** OnePlus Nord 3 5G (`CPH2493` / `MT6983` / project `22823` "Vitamin")
**Subsystem:** MT6983 TOPRGU hardware watchdog
**Author:** Solo Dushich (D25, Round 8)
**Date:** 2026-11-21
**Status:** Landed; offline simulation validated; live petting double-gated and bounded; init script staged, NOT installed

---

## 1. Hardware facts (verified, per B27 `LYNX-WATCHDOG-RECOVERY-PREFLIGHT-20261121.md`)

| Fact | Value |
|---|---|
| DT node | `watchdog@1c007000` |
| Compatible | `mediatek,mt6983-wdt` (family fallback `mediatek,mt6589-wdt`) |
| MMIO | base `0x1c007000`, size `0x1000` |
| Reboot-mode child | `syscon-reboot-mode`, register offset `0x24` |
| HW timeout range | 1–32 s (recommended 30 s) |
| Character device | `/dev/watchdog` — opening arms the timer; close without magic 'V' → immediate hardware reset |

## 2. Daemon contract

| Concern | Behavior |
|---|---|
| Default mode | **Offline simulation** — `--validate FIXTURE` drives the whole pet loop, health gates, and signal handling in-process from hermetic JSON. No hardware contact, no `open()` of `/dev/watchdog`. |
| Live mode | Refused unless BOTH `--live` and `--allow-live` present (exit 2). Bounded by `--cycles` (0 = unbounded daemon), `--interval` (must keep ≥3 pets inside the 30 s window), optional `--wall-cap`. |
| Pre-pet health gate | free RAM > 50 MB (`MemAvailable`), rootfs writable (`os.access('/', W_OK)`), 1-min load average < 16.0 (`/proc/loadavg`). Any failure → stop petting, close **without** 'V' → hardware watchdog recovery. |
| Magic 'V' stop | SIGTERM / SIGINT → write `V` to `/dev/watchdog`, close, exit cleanly (administrative stop without reset). |
| State publishing | JSON report (mode, final_state, cycles_patted, transcript, verdict) to stdout and `--state-file` (default `/tmp/lynx_watchdog_state.json`). |

### Final states

| State | Meaning |
|---|---|
| `COMPLETED` | Bounded loop finished, all pets landed, clean magic-'V' close |
| `STOPPED_BY_MAGIC_V` | SIGTERM/SIGINT received; 'V' written, closed |
| `ABORTED_HEALTH_GATE` | Pre-pet gate failed; stopped WITHOUT 'V' (recovery intended) |
| `LIVE_WALL_TIMEOUT` | Live wall-clock cap reached (live only) |

## 3. Petting sequence (per cycle)

```
health probe (/proc/meminfo, /proc/loadavg, rootfs W_OK)
   ├─ fail  → close WITHOUT 'V' → HW watchdog fires → safe recovery, exit
   └─ pass  → os.write(fd, b"1")  → sleep(interval) → next cycle
on SIGTERM/SIGINT at any point → os.write(fd, b"V") → close → clean exit
```

Pet interval must be ≤ 10 s so at least three consecutive pets fit inside the
30 s recommended HW window — enforced by `validate_watchdogd_spec`.

## 4. Init script (staged, NOT installed)

`lynx-watchdogd.initd` (OpenRC): runlevel `default`, `need bootmisc sysfs`,
`provide watchdog`, `before net`; `stop()` relies on the SIGTERM → magic-'V'
handler so an administrative stop never resets the device.

## 5. Safety boundaries (enforced by the test suite)

- AST scan: imports whitelisted (`argparse, json, os, pathlib, signal, sys, time, dataclasses, typing, __future__`); forbidden `os.*` (system/popen/exec*/spawn*/fork/kill/…) rejected.
- `os.open` of the device only inside `_live_open_watchdog`; `os.write` only inside `run_live` / `_live_magic_stop` / `_install_stop_handlers`.
- `/dev/watchdog` literal scoped to the module constant and whitelisted live functions.
- No `open(..., 'w'/'a'/'+')`, no `subprocess/socket/threading/...`, no network, no shell tokens.
- Offline fixtures never exercise the live code path.

## 6. Verification (2026-11-21)

```
$ python3 -m unittest test_lynx_watchdogd
Ran 45 tests — OK
$ python3 lynx_watchdogd.py --validate fixtures/watchdogd-nominal.json      → PASS (COMPLETED, 3 pets)
$ python3 lynx_watchdogd.py --validate fixtures/watchdogd-magic-stop.json   → PASS (STOPPED_BY_MAGIC_V)
$ python3 lynx_watchdogd.py --validate fixtures/watchdogd-health-gate.json  → PASS (ABORTED_HEALTH_GATE, 0 pets)
$ python3 lynx_watchdogd.py --validate fixtures/watchdogd-malformed.json    → FAIL MALFORMED_SPEC (exit 1, as designed)
$ python3 lynx_watchdogd.py --live                                          → REFUSED (exit 2, double gate)
```

## 7. Fixtures

| Fixture | Scenario | Expected state |
|---|---|---|
| `watchdogd-nominal.json` | 3 healthy cycles | `COMPLETED` |
| `watchdogd-magic-stop.json` | SIGTERM at cycle 2 (unbounded daemon mode) | `STOPPED_BY_MAGIC_V` |
| `watchdogd-health-gate.json` | loadavg 24.5 + RAM 42 MB at cycle 1 | `ABORTED_HEALTH_GATE` |
| `watchdogd-malformed.json` | wrong node + timeout 99 s + magic 'X' | spec rejected, exit 1 |

## 8. Queue notes

No unverified hardware claims are made beyond the B27-verified facts above.
The `mediatek,mt6589-wdt` fallback compatible is carried from B27's DT
evidence (family compatible list), not an assertion that the 6589 variant is
present.
