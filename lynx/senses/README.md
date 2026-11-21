# Lynx senses (S2, S3, S4, S8 + the S5 agent view)

Offline source for Lynx's sense emitters: small, stdlib-only, bounded
one-shot programs that describe what Lynx observes to the Noobia autonomy
harness (`common/autonomy`, ARCHITECTURE v0.2), and one writer for the
`noobia-agent` view where Lynx's own actions are recorded.

This is the "little machines creating artificial life" sensing layer:
Lynx reports her world, Aigel (on Nexus) reasons over it, and nothing
here ever commands Lynx's hardware.

**Nothing in this directory is installed on Lynx.** Installation is Aria's
IS-2 (with the I-2 syslog packet so the notice-level lines are kept).
This directory holds only source, tests, and the OpenRC service source.

## Layout (repo → installed path)

| Repo (`lynx/senses/`)                | Installed on Lynx (IS-2)                        |
| --- | --- |
| `common/lynx_senses_lib.py`    | `/usr/local/lib/noobia/senses/common/lynx_senses_lib.py` |
| `common/lynx_senses_loop.py`   | `/usr/local/lib/noobia/senses/common/lynx_senses_loop.py` |
| `touch/lynx_sense_touch.py`    | `/usr/local/lib/noobia/senses/touch/lynx_sense_touch.py` |
| `wifi/lynx_sense_wifi.py`      | `/usr/local/lib/noobia/senses/wifi/lynx_sense_wifi.py` |
| `power/lynx_sense_power.py`    | `/usr/local/lib/noobia/senses/power/lynx_sense_power.py` |
| `nexus/lynx_sense_nexus.py`    | `/usr/local/lib/noobia/senses/nexus/lynx_sense_nexus.py` |
| `agent/lynx_agent_action_log.py` | `/usr/local/lib/noobia/senses/agent/lynx_agent_action_log.py` |
| `init/lynx-senses.initd`       | `/etc/init.d/lynx-senses` (enabled by Aria, not by itself) |

Every sense imports the canonical line formatter
(`common/autonomy/sense.py`, installed at
`/usr/local/lib/noobia/autonomy/sense.py`) from the autonomy dir
(env `NOOBIA_AUTONOMY_DIR`). If it is missing, the sense fails honestly
(`{"ok": false, "error": "SenseUnavailable", ...}`) instead of duplicating
the format. **The formatter is never copied into Lynx's tree** (drift risk).

## Senses and events

Priorities follow the Aigel warn/fail convention (P1 = fail-class,
P3 = warn-class, P5 = routine change, P0 = sample). Defaults are
constants in `common/lynx_senses_lib.py`, documented here so a reviewer
can check them without opening code:

| Sense | Event (P) | Condition | Re-arm / hysteresis |
| --- | --- | --- | --- |
| touch (S2) | `touch.tap` / `touch.hold` (P5) | finger down→up, press ≤ 800 ms / > 800 ms | quantized to the 2 s loop |
| wifi (S3) | `wifi.link.down` / `wifi.link.up` (P1) | `lynx-status` carrier transition | immediate |
| wifi (S3) | `wifi.rssi.low` (P3) | `iw dev wlan0 link` signal ≤ -75 dBm | clears at ≥ -70 dBm |
| power (S4) | `power.battery.critical` (P1) | capacity ≤ 15 % | re-arms at ≥ 20 % |
| power (S4) | `power.battery.low` (P3) | capacity ≤ 30 % (not critical) | re-arms at ≥ 35 % |
| power (S4) | `power.thermal.hot` (P3) | SoC max ≥ 42 000 mC (lynx-status itself flags 55 C) | re-arms at ≤ 38 000 mC |
| power (S4) | `power.charging.change` (P5) | signed gauge current crosses ±50 mA deadband | — |
| nexus (S8) | `nexus.unreachable` / `nexus.reachable` (P1) | TCP probe 192.168.100.106:8080 (env `NOOBIA_NEXUS_HOST`/`NOOBIA_NEXUS_PORT`) | 2 consecutive failures / 1 success |
| wifi, power | `status.sample` (P0) | every 15th sample | P0 never closes a chunk: `trigger.py` triggers on `p >= 1` |

Charging state: `lynx-status` (schema 2) has no charger field; state is
derived from `battery.current_mA_signed` (≥ +50 mA charging, ≤ -50 mA
discharging, in between: idle; `null` gauge: `unknown`, never a guess).

### Conventions (Aigel-style: defaults, configurable, honest)

- **One-shot semantics.** Read the world → compare with last state →
  emit on transition/threshold → persist state atomically
  (`/var/lib/noobia/senses/<sense>/state.json`, env
  `NOOBIA_SENSES_STATE_DIR`) → one JSON object on stdout.
- **`--dry-run`** prints the would-be lines and touches neither syslog
  nor state.
- **Transition events baseline quietly:** the first sample after a boot
  (or state loss) never emits a transition (a finger already down, a link
  already down, a charging state already set - start times unknown).
  **Absolute alarm states** (battery.critical, battery.low, thermal.hot,
  rssi.low) report the state when they observe it, then arm for
  hysteresis - a real alarm should be raised even if it predates the
  sense.
- **Honest failure.** `{"ok": false, "error": ..., "detail": ...}`, exit 1.
  A sense never invents an event it did not observe, and a read failure
  emits nothing.
- **Touch is non-consuming.** S2 uses `TOUCH_STATUS` (NRP 380) over
  `/run/lynx/noobd.sock` only; it never sends `TOUCH_POLL` (381), the
  sole popper of the shared 8-slot queue (see
  `lynx/linux-port/docs/LYNX-TOUCH-EVENTS-DESIGN-20261121.md`).
- **S5 is not a sense.** `agent/lynx_agent_action_log.py` writes Lynx's
  own actions to the `noobia-agent` syslog view (ident `noobia-agent`,
  one bounded line ≤ 512 bytes, no NOOBIA prefix, no priority) so the
  trigger - which reads only `noobia-sense` - can never fire on Lynx's
  own doing (ARCHITECTURE §3, loop guard #1). The intended wiring into
  `lynx_agent.py`'s `audit(event)` is an IS packet for the agent-tool
  maintainers; this module patches nothing.
- **The loop isolates failures.** `common/lynx_senses_loop.py` runs
  touch every 2 s and wifi/power/nexus every 30 s; one sense failing logs
  one error line and never stops the others. Exit on SIGTERM (state files
  are always consistent - atomic writes).

## Service

`init/lynx-senses.initd` (OpenRC, BusyBox 1.37 compatible): background
python loop, `pidfile /run/lynx/lynx-senses.pid`, logs
`/var/log/lynx-senses.log`, `needs net`, after `lynx-local-logs lynx-wifi`,
and a `checkpath()` preflight that refuses to start unless both the
senses loop and the canonical `sense.py` formatter are installed.
Install and `rc-update add` belong to Aria's IS-2.

## Verification (offline)

```sh
python3 -m unittest discover -s lynx/senses -p 'test_*.py'   # 48 tests
```

Strictly offline: every world read is injected (lynx-status, iw, NRP
socket, Nexus probe) and the canonical `emit` is recorded, never
performed; state files live in per-test temp dirs. It pins the
transition/hysteresis tables above, the dry-run no-write contract, the
honest-failure shapes, the loop isolation, and the S5 line bounds.

The `lynx/tools/run_all_lynx_tests.py` runner scans `lynx/tools` only;
adding `lynx/senses` to its discovery is a small follow-up (queued with
D29/D30, Gwyn's Round 9).

## Owners

- Source + tests + atlas: **Dushich** (2026-11-21).
- Review: Gwyn; second review: Dushich's own tests; Aria on return.
- Install (IS-2): **Aria**. S5 wiring into `lynx_agent`: agent-tool
  maintainers, in an IS packet.
