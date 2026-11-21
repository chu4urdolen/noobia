# lynx-survivald — autonomous survival & power daemon (D26)

Background polling daemon executing the **B28 4-state survival engine**
(`lynx/tools/survival/lynx_survival_engine.py`) on the OnePlus Nord 3.
See `../../linux-port/docs/LYNX-SURVIVAL-DAEMON-20261121.md`.

Safety model:

- **Offline by default:** `--validate FIXTURE` runs the full polling loop
  (evaluate → dispatch → broker publish) in-process from hermetic JSON.
- **Live is double-gated:** `--live --allow-live` (refused otherwise); polls
  read-only sysfs (BQ28Z610 gauge, MT6375 charger, LVTS/NTC thermal zones)
  and dispatches **simulated** actions only.
- **No `os` import at all** — no device writes, no exec, no shutdown calls
  (enforced by `test_lynx_survivald.py`).
- Actions are data: `set_cpu_governor` (schedutil/powersave),
  `limit_charge_current` (≤500 mA), `trigger_suspend` (SCP/LPM C_SLEEP),
  `poweroff` (graceful sequence) — all `simulated: true`, none executed.
- Status broker: `/tmp/lynx_survival_state.json`
  (`state`, `policy_state`, `status`, `actions`, `reasons`, `poll`).
- SIGTERM/SIGINT → final broker publication `STOPPED_BY_SIGNAL`, clean exit.

`lynx-survivald.initd` is STAGED for review — not installed into
`/etc/init.d/` until approved (runlevel `default`, `after lynx-watchdogd`).

```sh
python3 lynx_survivald.py --validate fixtures/survivald-nominal.json
python3 -m unittest test_lynx_survivald
```
