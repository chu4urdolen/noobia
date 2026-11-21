# lynx_openrc_validator — OpenRC service-tree validator (D28)

Offline validator for the untethered-boot OpenRC dependency graph on Lynx
(Alpine): `bootmisc → sysfs → networking → lynx-watchdogd → lynx-survivald
→ lynx-cgroups → lynx-agent → lynx-presence`.
See `../../linux-port/docs/LYNX-OPENRC-SERVICE-TREE-20261121.md`.

Semantics (documented):

- `need` — HARD prerequisite; a `need` cycle is a **DEADLOCK** (FAIL).
- `use` — SOFT prerequisite (best-effort start, never stops the other side);
  `use`-only cycles are notes, not deadlocks.
- `before`/`after` — WEAK ordering only; a contradictory weak ordering
  (both directions between a pair) is an **ORDER_CONFLICT** (FAIL); a
  consistent weak cycle is informational (PASS).
- References to a name another service `provide`s resolve to the provider
  (e.g. `lynx-watchdogd` provides `watchdog`).
- `need`/`use` of an undefined service → **MISSING_PREREQUISITE** (FAIL);
  weak refs to unknown services are notes.
- Deterministic startup order (Kahn, alphabetical tie-break) and the
  reverse shutdown order.

Safety model:

- **Offline by default:** `--validate FIXTURE` validates hermetic JSON
  service definitions. Zero hardware contact.
- **Live is double-gated:** `--live --allow-live` (refused otherwise);
  performs a bounded **read-only** parse of the staged initds on disk
  (`lynx-watchdogd.initd`, `lynx-survivald.initd`) plus the declared
  external base services. It never writes, never installs anything into
  `/etc/init.d/`.
- **No `os` import at all** — no exec, no installs (enforced by
  `test_lynx_openrc_validator.py`).
- Status broker: `/tmp/lynx_openrc_state.json`
  (orders, cycles, verdict, reasons).

```sh
python3 lynx_openrc_validator.py --validate fixtures/openrc-chain-pass.json
python3 lynx_openrc_validator.py --live --allow-live
python3 -m unittest test_lynx_openrc_validator
```
