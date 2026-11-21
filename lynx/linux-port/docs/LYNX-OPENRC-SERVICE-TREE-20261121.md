# Lynx OpenRC Service Tree — Dependency & Startup Order Validator (D28)

**Author:** Solo Dushich (Round 8, queue D28)
**Date:** 2026-11-21
**Tool:** `lynx/tools/openrc_validator/lynx_openrc_validator.py`
**Status:** code-complete, 38 unit tests OK, ready for Banshee B29 review

---

## 1. Verified facts (on-disk, cited)

- Queue D28 chain (`LYNX-ROUND-8-QUEUE-BANSHEE-20261121.md`):
  `bootmisc → sysfs → networking → lynx-watchdogd → lynx-survivald →
  lynx-cgroups → lynx-agent → lynx-presence`.
- Staged initds (D25/D26, both **STAGED, not installed**):
  - `lynx/tools/watchdog_daemon/lynx-watchdogd.initd`:
    `need bootmisc sysfs`, `before net`, `provide watchdog`.
  - `lynx/tools/survival_daemon/lynx-survivald.initd`:
    `need bootmisc sysfs`, `after lynx-watchdogd`, `before net`.
- B32 architecture doc §4 (service table): `lynx-cgroups` is
  `after sysfs` (enforces 512 MiB limit), `lynx-agent` is
  `after lynx-survivald lynx-cgroups` — consistent with the queue chain.
- `provide` is a legitimate OpenRC `depend()` directive (virtual service
  name). Discovered during D28 development when the validator parsed the
  real staged `lynx-watchdogd.initd`: the parser now accepts it and
  resolves references to provided names to their provider.

## 2. Dependency semantics (model, documented)

| directive | startup edge | stop obligation | cycle class |
| --- | --- | --- | --- |
| `need` | dep first (HARD) | yes — dep stops after dependent | `need` cycle → **DEADLOCK** (FAIL) |
| `use` | dep first (SOFT) | no — dependent never stops dep | `use`-only cycle → note (PASS) |
| `before` X | self first (WEAK) | none | contradictory pair → **ORDER_CONFLICT** (FAIL); consistent weak cycle → note (PASS) |
| `after` X | X first (WEAK) | none | same as `before` |
| `provide` | — (declares a virtual name) | — | a dep on a provided name resolves to the provider |

FAIL conditions: any `need` cycle, any contradictory weak ordering
(same pair ordered in both directions), any `need`/`use` of an undefined
service (MISSING_PREREQUISITE).
PASS-with-notes: consistent weak cycles, weak refs to unknown services
(OpenRC tolerates these).

## 3. Contract (CLI)

```
lynx_openrc_validator.py --validate FIXTURE        # offline, default mode
lynx_openrc_validator.py --live --allow-live       # read-only staged-initd parse
--state-file PATH                                  # broker, default /tmp/lynx_openrc_state.json
```

- No args → help, **exit 2**; `--live` without `--allow-live` → **REFUSED, exit 2**.
- `--validate`: fixture expectations met → **exit 0**; verdict mismatch or
  malformed input → **exit 1**.
- `--live --allow-live`: parses the two staged initds on disk (read-only),
  validates them against the declared external base services
  (`bootmisc`, `sysfs`, `networking`, `net`, `loopback`, `local`), and
  exits 0 on PASS. Never writes; never installs into `/etc/init.d/`.

## 4. Algorithm

1. Parse service definitions (fixture JSON or staged initds).
2. Build startup edges: `need`/`use`/`after` → dep→self; `before` →
   self→dep; provider names resolved.
3. Iterative Tarjan SCC over the edge graph; classify each cyclic SCC:
   contains a `need` edge → DEADLOCK; else bidirectional soft pair →
   ORDER_CONFLICT; else weak cycle (note). Self-edges: `need`/`use` →
   DEADLOCK, weak → ORDER_CONFLICT.
4. Kahn topological order with deterministic alphabetical tie-break →
   `startup_order`; `shutdown_order` = reverse.
5. Missing-prerequisite scan (`need`/`use` of undefined names).
6. Fixture expectations (verdict, expected_chain subsequence,
   expect_hard_cycle / expect_order_conflict / expect_missing) checked
   against the report.

## 5. Verification transcript (real output, 2026-11-21)

Targeted suite:

```
$ cd lynx/tools/openrc_validator && python3 -m unittest test_lynx_openrc_validator
Ran 38 tests in 0.346s
OK
```

Tree-wide runner (post-D28):

```
$ cd lynx/tools && python3 run_all_lynx_tests.py
**Overall: PASS**
- Suites: 102 total, 101 ok, 0 failed, 1 env-blocked
| test_lynx_openrc_validator | 38 | OK | 0.40 | Ran 38 tests in 0.348s OK |
```

(1 env-blocked = `test_lynx_ble_gatt_probe`, missing `dbus_next` on system
Python 3.14 — known, pre-existing.)

Live parse of the real staged initds (double-gated, read-only): verdict
**PASS**, order `bootmisc → sysfs → lynx-watchdogd → lynx-survivald → net`
(`before net` weakly honored; `provide watchdog` parsed).

## 6. Fixtures

| fixture | scenario | expected |
| --- | --- | --- |
| `openrc-chain-pass.json` | full 8-service queue chain, clean | PASS; startup == queue chain; shutdown == reverse |
| `openrc-chain-hard-deadlock.json` | `lynx-agent` ↔ `lynx-presence` `need` cycle + undefined `lynx-gateway` prereq | FAIL; hard cycle + missing prerequisite |
| `openrc-chain-order-conflict.json` | `lynx-survivald`/`lynx-watchdogd` ordered both directions (weak) | FAIL; order conflict |

## 7. Queue notes / unverified claims (NOT asserted)

- The services `lynx-cgroups`, `lynx-agent`, `lynx-presence` have **no
  staged initds yet** — only `lynx-watchdogd` and `lynx-survivald` exist on
  disk (D25/D26). Their definitions in the PASS fixture are the queue
  contract, to be implemented as staged initds in a later round when their
  tooling lands.
- Alpine's actual on-device behavior (runlevels, weak-dep resolution,
  `provide` semantics) is **UNVERIFIED on Lynx**; the model above follows
  documented OpenRC behavior. A live Lynx boot test with this validator's
  report attached is the verification path.
- Round 8 (D25–D28) is thereby complete on the Dushich side, pending
  Banshee's B29 review.
