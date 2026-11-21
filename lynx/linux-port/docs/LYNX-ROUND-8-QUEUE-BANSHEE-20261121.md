# Lynx Round 8 Work Queue: Autonomous Service Layer & Untethered Readiness

**Coordinator:** Banshee (Spirit of Initiative 💙)
**Author Pair:** Solo Dushich & Banshee
**Date:** 2026-11-21
**Objective:** Transition Lynx from hardware auditing to an autonomous, self-preserving Linux service runtime.

---

## 1. Context & Sequencing

With the completion of Round 7 (D21–D24 and B21–B28), **100% of the hardware subsystems on the OnePlus Nord 3 are audited, mapped, and preflighted** with 1,024 unit tests passing cleanly tree-wide.

In **Round 8**, we construct the software safety and supervision daemons necessary to cut the tether and allow Lynx to run autonomously without bricking, overheating, or brownout corruption:
1. **Solo Dushich executes D25 through D28 in order.**
2. **Banshee executes B29 through B32 in parallel, conducting primary peer reviews for Dushich landings.**
3. **Safety Boundaries:** All daemons and tools must run in offline simulation mode by default with `--validate <FIXTURE>`. Live testing remains strictly gated behind `--live --allow-live`. OpenRC init scripts are staged in tool directories and **NOT** installed into `/etc/init.d/` until approved. Zero trailing whitespace (`git diff --check`).

---

## 2. Solo Dushich Queue (Items D25–D28)

### Item D25: Watchdog Supervision & Petting Daemon (`lynx-watchdogd`)
- **Objective:** Build the software supervisor and hardware watchdog petting daemon interfacing with MediaTek MT6983 TOPRGU (`watchdog@1c007000`).
- **Directory:** `lynx/tools/watchdog_daemon/`
- **Deliverables:**
  - `lynx_watchdogd.py`: Daemon supporting `--validate <FIXTURE>`, simulated petting loop, and bounded `--live --allow-live` execution.
  - `lynx-watchdogd.initd`: Staged OpenRC init script (runlevel `default`, `before net`, `provide watchdog`).
  - Pre-petting health checks: Checks available RAM (> 50MB), rootfs writable, and CPU load average < 16.0 before petting. If health checks fail, stops petting to allow hardware watchdog recovery.
  - Magic 'V' character handler: Clean signal trapping (`SIGTERM`, `SIGINT`) writing `'V'` to `/dev/watchdog` before close to permit safe administrative stops.
  - 4 hermetic fixtures, unit tests in `test_lynx_watchdogd.py`, and doc `LYNX-WATCHDOG-DAEMON-20261121.md`.
  - Whitelist in `lynx/.gitignore`.

### Item D26: Autonomous Survival & Power Management Daemon (`lynx-survivald`)
- **Objective:** Build the background polling daemon that executes the 4-state survival decision engine established in B28.
- **Directory:** `lynx/tools/survival_daemon/`
- **Deliverables:**
  - `lynx_survivald.py`: Polling daemon evaluating fuel gauge (BQ28Z610), SuperVOOC charger, and LVTS/NTC thermals every 10s.
  - `lynx-survivald.initd`: Staged OpenRC init script (runlevel `default`, `after lynx-watchdogd`).
  - Status broker: Publishes current policy state (`NOMINAL`, `THERMAL_THROTTLE`, `LOW_POWER_SUSPEND`, `EMERGENCY_SHUTDOWN`) to `/tmp/lynx_survival_state.json`.
  - Simulated action dispatchers: CPU governor switching (`powersave` vs `schedutil`), charging current limits ($\le 500\text{mA}$), SCP/LPM suspend triggers, and graceful shutdown sequence.
  - 4 hermetic fixtures, unit tests in `test_lynx_survivald.py`, and doc `LYNX-SURVIVAL-DAEMON-20261121.md`.
  - Whitelist in `lynx/.gitignore`.

### Item D27: Cgroup v2 Resource Limiting & Sandboxing Wrapper for Autonomous Agents
- **Objective:** Establish the Linux cgroups v2 resource controller limiting autonomous agent memory and CPU consumption to prevent OOM termination of the system network stack.
- **Directory:** `lynx/tools/cgroups/`
- **Deliverables:**
  - `lynx_cgroup_sandbox.py`: Configures `/sys/fs/cgroup/lynx-agent/` with `memory.max` (default 512 MiB), `memory.high` (400 MiB), and `cpu.max` (quota/period).
  - Process migration: Moves target PID into `cgroup.procs`.
  - Pressure monitor: Parses `memory.pressure` and `cpu.pressure` to flag thrashing.
  - 3 hermetic fixtures, unit tests in `test_lynx_cgroup_sandbox.py`, and doc `LYNX-CGROUP-SANDBOX-20261121.md`.
  - Whitelist in `lynx/.gitignore`.

### Item D28: OpenRC Service Tree Dependency & Startup Order Validator
- **Objective:** Build the offline validator verifying the entire untethered boot service graph across Alpine Linux.
- **Directory:** `lynx/tools/openrc_validator/`
- **Deliverables:**
  - `lynx_openrc_validator.py`: Parses service dependencies (`need`, `use`, `before`, `after`) across:
    `bootmisc` $\rightarrow$ `sysfs` $\rightarrow$ `networking` $\rightarrow$ `lynx-watchdogd` $\rightarrow$ `lynx-survivald` $\rightarrow$ `lynx-cgroups` $\rightarrow$ `lynx-agent` $\rightarrow$ `lynx-presence`.
  - Asserts strict acyclic graph, verifies reverse shutdown order, flags missing prerequisites.
  - 3 fixtures, unit tests in `test_lynx_openrc_validator.py`, and doc `LYNX-OPENRC-SERVICE-TREE-20261121.md`.
  - Whitelist in `lynx/.gitignore`.

---

## 3. Banshee Queue (Items B29–B32)

### Item B29: Peer Review & Verification for D25–D28
- Primary peer reviewer validating Solo Dushich's Round 8 landings against safety invariants, AST rules, and zero trailing whitespace.

### Item B30: Autonomous Health Heartbeat Telemetry Publisher
- Compact heartbeat publisher broadcasting structured NRP/1 UDP telemetry packets to Nexus (`192.168.100.106`) every 60s during untethered operation.
- Directory: `lynx/tools/heartbeat/`

### Item B31: Untethered Autonomy Readiness Preflight Checklist
- Comprehensive offline pre-flight checklist tool auditing all prerequisites before cutting the tether (Battery $\ge 50\%$, UFS health normal, Watchdog ready, Survival daemon configured, Cgroup controller mounted).
- Directory: `lynx/tools/autonomy_check/`

### Item B32: Consolidated Autonomy Architecture Specification
- Master architecture document unifying the entire untethered autonomy loop, fail-safe state machine, watchdog petting contract, and emergency procedures into a definitive reference.
- Deliverable: `lynx/linux-port/docs/LYNX-AUTONOMY-ARCHITECTURE-20261121.md`.
