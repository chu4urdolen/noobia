# lynx_cgroup_sandbox — cgroups v2 agent sandbox (D27)

Spec validator, SIMULATED mutation planner, and PSI thrash monitor for the
`/sys/fs/cgroup/lynx-agent/` cgroup on the OnePlus Nord 3.
See `../../linux-port/docs/LYNX-CGROUP-SANDBOX-20261121.md`.

Safety model:

- **Offline by default:** `--validate FIXTURE` validates the spec, plans the
  full mutation sequence (ensure_group → memory.max → memory.high → cpu.max
  → memory.oom.group → optional cgroup.procs PID migration), and evaluates a
  hermetic PSI pressure series in-process. Zero hardware contact.
- **Live is double-gated:** `--live --allow-live` (refused otherwise);
  performs a bounded **read-only** inspection of the cgroup v2 root
  (controllers, subtree_control, the lynx-agent group's limits and PSI
  files). It never writes anything.
- **No `os` import at all** — no device writes, no exec (enforced by
  `test_lynx_cgroup_sandbox.py`).
- Actions are data: `ensure_group`, `set_property`, `migrate_pid` — all
  `simulated: true`, none executed. Execution stays gated behind the B31
  autonomy readiness checklist.
- Parameters mirror the B32 architecture contract (memory.max 512 MiB,
  memory.high 400 MiB, cpu.max 150000/100000 = 1.5 cores, oom.group=1),
  with a drift-detection test re-reading the architecture doc.
- Status broker: `/tmp/lynx_cgroup_state.json`
  (spec, plan, polls, final_severity).
- **No initd ships with D27** (out of the queue's scope); the `lynx-cgroups`
  OpenRC service wraps this tool in a later round and is covered by the D28
  service-tree validator.

```sh
python3 lynx_cgroup_sandbox.py --validate fixtures/cgroup-sandbox-defaults.json
python3 -m unittest test_lynx_cgroup_sandbox
```
