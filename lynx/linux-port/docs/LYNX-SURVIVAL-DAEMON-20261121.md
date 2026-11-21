# Lynx Autonomous Survival & Power Management Daemon (`lynx-survivald`)

**Device:** OnePlus Nord 3 5G (`CPH2493` / `MT6983` / project `22823` "Vitamin")
**Subsystem:** Autonomous survival policy (battery + thermal + charge)
**Author:** Solo Dushich (D26, Round 8)
**Date:** 2026-11-21
**Status:** Landed; offline simulation validated; live mode double-gated, read-only telemetry, simulated actions only; init script staged, NOT installed

---

## 1. Telemetry sources (verified facts)

| Source | Hardware | Path | Verified by |
|---|---|---|---|
| Fuel gauge | TI BQ28Z610, i2c7 @ `0x55` | `/sys/bus/i2c/devices/7-0055/battery_snapshot` | B23 `LYNX-BATTERY-HEALTH-EVALUATOR-20261121.md` |
| SuperVOOC charger | MT6375 sub-PMIC, i2c5 @ `0x34` (2S pack 7.4 V nom / 8.7 V chg) | charger sysfs / gauge envelope | B18 `LYNX-CHARGER-SUPERVOOC-PREFLIGHT-20261121.md` |
| Thermals | LVTS array (soc_max 116.5 °C crit) + NTC zones | `/sys/class/thermal/thermal_zone*/temp` | B22 `LYNX-THERMAL-ZONES-VALIDATOR-20261121.md` |

## 2. Policy states (B28 engine, mirrored)

Queue short name → engine state:

| D26 short | B28 policy state | Trigger (thresholds mirrored from `lynx_survival_engine.py`) |
|---|---|---|
| `NOMINAL` | `NOMINAL_OPERATION` | battery > 15 % and skin < 40 °C and die < 75 °C |
| `THERMAL_THROTTLE` | `THERMAL_THROTTLE_PAUSE_CHG` | skin ≥ 40 °C or die ≥ 75 °C (below emergency) |
| `LOW_POWER_SUSPEND` | `LOW_POWER_SUSPEND` | battery ≤ 15 % (> 5 %) |
| `EMERGENCY_SHUTDOWN` | `EMERGENCY_SHUTDOWN` | battery ≤ 5 %, or skin ≥ 45 °C, or die ≥ 105 °C, or malformed telemetry |

A test (`TestThresholdsMatchB28Engine`) re-reads the B28 engine source and
fails if the mirrored constants drift, keeping the daemon and engine in sync.

## 3. Action dispatchers (SIMULATED — data, never executed)

| Policy | Simulated actions |
|---|---|
| `NOMINAL_OPERATION` | `set_cpu_governor schedutil` · `charge_policy NORMAL_80W_SUPERVOOC` · `agent_duty FULL` |
| `THERMAL_THROTTLE_PAUSE_CHG` | `set_cpu_governor powersave` · `limit_charge_current 500 mA` (mt6375-chg) · `throttle_agents REDUCED` |
| `LOW_POWER_SUSPEND` | `set_cpu_governor powersave` · `limit_charge_current 500 mA` · `trigger_suspend scp-lpm (C_SLEEP)` · `stop_agents` |
| `EMERGENCY_SHUTDOWN` | `stop_agents` · `flush_broker (final)` · `sync` · `poweroff` (graceful sequence) — loop terminates |

Every action record carries `"simulated": true`. No actuation code path
exists in the daemon; real actuation belongs to the approved autonomy
readiness gate (B31) and beyond.

## 4. Status broker

Every poll publishes to `--state-file` (default `/tmp/lynx_survival_state.json`):

```json
{
  "mode": "live",
  "state": "NOMINAL",
  "policy_state": "NOMINAL_OPERATION",
  "status": "OK",
  "telemetry": {"battery_pct": 88, "shell_temp_c": 33.5, "soc_max_temp_c": 41.0},
  "reasons": [],
  "actions": [{"action": "set_cpu_governor", "target": "cpu0-cpufreq", "params": {"governor": "schedutil"}, "simulated": true}],
  "poll": 3,
  "timestamp": 1763710000.0
}
```

Readers (B30 heartbeat, B31 autonomy checklist, agents) poll this file.

## 5. Loop semantics

- Default poll interval **10 s** (queue), bounds 1–60 s enforced by spec validation.
- Offline `--validate`: bounded by `engine.max_polls` or a `signal` stop; unbounded daemon mode (`max_polls: 0`) without a signal is rejected offline.
- Live: unbounded by default (`--polls 0`), optional `--wall-cap`.
- `EMERGENCY_SHUTDOWN` is terminal: graceful sequence dispatched, loop ends.
- SIGTERM/SIGINT at any point → final broker publication `STOPPED_BY_SIGNAL`, clean exit (init `stop()` relies on this).

## 6. Safety boundaries (enforced by the test suite)

- **No `os` import at all** — no `open()`, no `os.*` calls anywhere in the module.
- No `subprocess/socket/threading/multiprocessing/shutil/urllib/requests/ctypes`, no `eval(`/`exec(`, no shell/exec tokens (`systemctl`, `poweroff(`, `reboot(`, `sync(` as calls), no network.
- Action names appear only as data strings; shutdown words never as calls.
- Broker path constant appears exactly once in source (default), always overridden by CLI arg.

## 7. Verification (2026-11-21)

```
$ python3 -m unittest test_lynx_survivald
Ran 39 tests — OK
$ python3 lynx_survivald.py --validate fixtures/survivald-nominal.json              → PASS (NOMINAL, 3 polls)
$ python3 lynx_survivald.py --validate fixtures/survivald-throttle-then-recover.json → PASS (THERMAL_THROTTLE → NOMINAL)
$ python3 lynx_survivald.py --validate fixtures/survivald-suspend.json              → PASS (LOW_POWER_SUSPEND)
$ python3 lynx_survivald.py --validate fixtures/survivald-emergency.json            → PASS (EMERGENCY_SHUTDOWN, terminal)
$ python3 lynx_survivald.py --live                                                 → REFUSED (exit 2, double gate)
```

## 8. Fixtures

| Fixture | Scenario | Expected final state |
|---|---|---|
| `survivald-nominal.json` | 3 healthy polls | `NOMINAL` |
| `survivald-throttle-then-recover.json` | skin 42.1 °C then 38.4 °C | `NOMINAL` (throttle dispatched at poll 1) |
| `survivald-suspend.json` | battery 12 % → 9 % | `LOW_POWER_SUSPEND` |
| `survivald-emergency.json` | battery 18 % → 4 % | `EMERGENCY_SHUTDOWN` (loop terminates early) |

## 9. Init script (staged, NOT installed)

`lynx-survivald.initd` (OpenRC): runlevel `default`, `need bootmisc sysfs`,
`after lynx-watchdogd` (queue: after the watchdog supervisor), `before net`;
`stop()` uses SIGTERM → the daemon's `STOPPED_BY_SIGNAL` final publication.

## 10. Queue notes

State names: the broker publishes both the queue short name (`state`) and the
B28 engine name (`policy_state`), so both naming schemes are auditable. The
charging limit of 500 mA and governor names are policy parameters (queue D26),
not hardware-derived limits; the 80 W SuperVOOC nominal policy remains a
published-spec label carried from B18.
