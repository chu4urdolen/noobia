# Lynx Cgroups v2 Agent Sandbox (D27)

**Author:** Solo Dushich (Round 8, queue D27)
**Date:** 2026-11-21
**Tool:** `lynx/tools/cgroups/lynx_cgroup_sandbox.py`
**Status:** code-complete, 57 unit tests OK, ready for Banshee B29 review

---

## 1. Verified facts (on-disk, cited)

The B32 consolidated autonomy architecture
(`lynx/linux-port/docs/LYNX-AUTONOMY-ARCHITECTURE-20261121.md`, section 5)
fixes the sandbox parameters for the autonomous agent cgroup:

| Property | Value | Source |
| --- | --- | --- |
| cgroup | `/sys/fs/cgroup/lynx-agent/` | B32 arch doc §5 |
| `memory.max` | `536870912` (512 MiB) | B32 arch doc §5 |
| `memory.high` | `419430400` (400 MiB) | B32 arch doc §5 |
| `cpu.max` | `150000 100000` (1.5 cores) | B32 arch doc §5 |
| `memory.oom.group` | `1` | B32 arch doc §5 |

The daemon's default constants are **mirrored from that doc** and a
drift-detection test (`TestConstantsMatchB32ArchDoc`) re-reads the doc and
fails if the daemon constants ever diverge — the same pattern used for the
B28 engine thresholds in D26.

Other context (on-disk): B30 heartbeat packet carries
`cgroups: {agent_mem_limit_mb: 512.0, pressure_pct}` — consistent with the
512 MiB ceiling. B31 readiness checklist lists "Cgroup controller mounted"
as a pre-tether-cut prerequisite.

## 2. Contract (CLI)

```
lynx_cgroup_sandbox.py --validate FIXTURE          # offline, default mode
lynx_cgroup_sandbox.py --live --allow-live         # bounded read-only inspection
--state-file PATH                                  # broker, default /tmp/lynx_cgroup_state.json
```

- No args → help, **exit 2**.
- `--live` without `--allow-live` → **REFUSED, exit 2**.
- `--validate`: pass → **exit 0** (broker published); malformed fixture/spec
  or severity mismatch → **exit 1**.
- `--live --allow-live`: read-only, bounded, **exit 0** with a JSON report
  (v2 root presence, controllers, subtree_control, agent group limits,
  parsed PSI, proposed plan). Writes nothing.

## 3. Spec validation rules

`build_spec` fills the B32 defaults for missing keys, then enforces:

- `cgroup_name` matches `[a-z0-9][a-z0-9_-]*` (kernel cgroup naming:
  lowercase, no path characters).
- `memory_max_bytes` in `[16 MiB, 4 GiB]`.
- `memory_high_bytes` ≥ 1 MiB and **strictly less** than `memory.max`
  (high is a throttle threshold below the hard ceiling).
- `cpu_quota_us`, `cpu_period_us` in `[1000, 1 000 000]` (kernel CFS bounds).
- `cpu_quota_us ≤ 4 × cpu_period_us` (an agent loop may never be granted
  more than 4 cores — the survival/watchdog/heartbeat daemons keep the
  system alive).
- `oom_group` ∈ {`0`, `1`}; B32 mandates `1` (kill the agent group cleanly
  on OOM instead of collateral kills).
- `target_pid` positive integer or null.

All failures are collected and reported together (one `SpecError` with
reasons), not fail-fast.

## 4. SIMULATED mutation plan (order matters)

| # | action | target | params |
| --- | --- | --- | --- |
| 1 | `ensure_group` | `/sys/fs/cgroup/<name>` | `mkdir`, mode 0755 |
| 2 | `set_property` | `…/memory.max` | `"536870912"` |
| 3 | `set_property` | `…/memory.high` | `"419430400"` |
| 4 | `set_property` | `…/cpu.max` | `"150000 100000"` |
| 5 | `set_property` | `…/memory.oom.group` | `"1"` |
| 6 | `migrate_pid` (only if `target_pid` set) | `…/cgroup.procs` | `{pid}` |

Limits are set **before** any process is migrated (migrating first would
briefly run the agent unlimited). Every action carries
`"simulated": true`; none is executed by this tool.

## 5. PSI thrash monitor

`parse_pressure` strictly parses cgroup v2 PSI files
(`some`/`full` lines, `avg3`/`avg60`/`avg300`/`total`, `name=value`
tokens, non-negative floats) and raises `PressureParseError` on anything
malformed. `assess_thrash` classifies `some avg3` (ms of delay per second):

| severity | memory `some avg3` | cpu `some avg3` |
| --- | --- | --- |
| `THRASHING` | ≥ 10.0 | ≥ 25.0 |
| `ELEVATED` | ≥ 5.0 | ≥ 12.5 |
| `OK` | < 5.0 | < 12.5 |

Thresholds are documented design values (not hardware facts): sustained
memory-reclaim or CPU-throttle delay in these bands means the agent is
stealing from the network stack / survival daemons and needs intervention.

## 6. Safety boundaries

- **No `os` import at all**; no exec, no subprocess, no sockets, no
  threads. Enforced by `TestSafetyBoundaries` (forbidden-token scan).
- **No path mutation calls** (`.mkdir(`, `.unlink(`, `.chmod(`, …); the
  only file write in the daemon is the status-broker `write_text`.
- The broker path `/tmp/lynx_cgroup_state.json` appears exactly once
  (constant only).
- `--live --allow-live` is read-only; the double gate refuses single-flag
  live runs.
- **No initd ships** (D27 queue scope); the `lynx-cgroups` service will
  wrap this tool in a later round — D28's service-tree validator covers the
  dependency chain.

## 7. Verification transcript (real output, 2026-11-21)

Targeted suite:

```
$ cd lynx/tools/cgroups && python3 -m unittest test_lynx_cgroup_sandbox
Ran 57 tests in 0.302s
OK
```

Tree-wide runner (post-D27):

```
$ cd lynx/tools && python3 run_all_lynx_tests.py
**Overall: PASS**
- Suites: 101 total, 100 ok, 0 failed, 1 env-blocked
| test_lynx_cgroup_sandbox | 57 | OK | 0.35 | Ran 57 tests in 0.303s OK |
```

(1 env-blocked = `test_lynx_ble_gatt_probe`, missing `dbus_next` on system
Python 3.14 — known, pre-existing.)

Live inspection on Nexus (read-only, double-gated) correctly reports the
cgroup v2 unified root with `cpu`/`memory` in `subtree_control` and
`lynx-agent` **not present** — expected, since the sandbox targets Lynx.

## 8. Fixtures

| fixture | spec | series | expected |
| --- | --- | --- | --- |
| `cgroup-sandbox-defaults.json` | `{}` (B32 defaults) | OK → ELEVATED (mem 6.1) → ELEVATED (cpu 14.0) | `plan`, 5 actions, final `ELEVATED` |
| `cgroup-sandbox-thrashing-pid.json` | 256/200 MiB, 0.5 CPU, pid 1234 | THRASHING (mem 12.5) → THRASHING (cpu 30.2) | `plan`, 6 actions (migrate_pid last), final `THRASHING` |
| `cgroup-sandbox-spec-rejected.json` | high (288 MiB) ≥ max (256 MiB) | — | `spec_rejected`, reason names `memory_high_bytes` |

## 9. Queue notes / unverified claims (NOT asserted)

- That Lynx's Alpine root actually mounts cgroup v2 with `memory`+`cpu`
  controllers enabled is **UNVERIFIED on-device**; B31's readiness checklist
  ("Cgroup controller mounted") is the gate. This tool's `--live
  --allow-live` inspection is the verification path when run on Lynx.
- Actual execution of the mutation plan (mkdir/limit-set/migrate) is
  deliberately **out of scope** for D27 — it requires a live Lynx session,
  operator approval, and the B31 checklist green. This tool produces the
  exact, validated plan and the thrash telemetry that such an operator
  would act on.
