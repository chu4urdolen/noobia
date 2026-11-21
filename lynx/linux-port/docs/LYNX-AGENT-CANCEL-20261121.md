# Lynx agent cancellation: `AGENT_CANCEL` and `lynx_codex` (2026-11-21)

Gwyn, backlog item 1 (`LYNX-GWYN-BACKLOG-20261121.md`). Offline source
analysis. No phone contact, no job cancelled, no live queue touched.

## Verdict

**No-go:** an agent-facing cancel for `lynx_codex` cannot be built on NRP
`AGENT_CANCEL`, because `lynx_codex` never enters the queue that
`AGENT_CANCEL` controls. A wrapper would always answer `cancelled=0` and stop
nothing, which would be a dishonest stop button. A real `lynx_codex` stop
needs a change to deployed code (`lynx_codex_tool.py`), so it is written
below as a proposal for Aria's review, not implemented.

## What `AGENT_CANCEL` actually does

| Step | Source | Behaviour |
| --- | --- | --- |
| Registration | `lynx/tools/lynx_noob_runtime.py:734` | Native 512 `AGENT_CANCEL` → `agent_cancel` |
| Handler | `lynx_noob_runtime.py:763` | Rejects numeric args (`usage: job ID text`); calls `JobQueue(AGENT_JOBS).cancel(text.strip())`; any queue error becomes `agent job unavailable` |
| Queue | `lynx_noob_runtime.py:31`, `:52` | `/var/lib/lynx-agent/jobs`, the spool fed by `AGENT_SUBMIT` (510) |
| ID scope | `lynx/tools/agent/lynx_agent_queue.py:13` | Exactly 32 lowercase hex characters, so no paths or other names |
| Cancel | `lynx_agent_queue.py:129` | Under the queue lock, unlinks `<id>.pending` only. Returns `False` for missing, running, or finished jobs, and refuses a symlinked pending file |
| Result | handler | `1, cancelled=1` when a pending job was removed; otherwise `0, cancelled=0` |

So `AGENT_CANCEL` is a **pending-job withdrawal, not a stop**. Once the
worker has claimed a job (`lynx_agent_queue.py:94`), the only ways to end it
are:
- the worker's own 180 s timeout, which kills the process group
  (`lynx_agent_worker.py:100-102`);
- stopping the whole worker with `lynx-agentctl stop`, which runs
  `rc-service lynx-agent-worker stop` (`lynx_agentctl.py:24-34`). The worker
  then sends SIGTERM to the running job's process group
  (`lynx_agent_worker.py:32-37`, `:96`).

**Authorization** is enforced before any native call, in `serve()`
(`lynx_noob_runtime.py:1373`):
- the TCP peer must match the configured address (`:1428`);
- the local socket checks the caller's UID with `SO_PEERCRED` (`:1433`);
- remote callers must pass the Nexus HMAC challenge (`:1437`).

The cancel handler itself has no per-job owner check. Any authorized NRP
caller who knows a job ID can withdraw it. IDs are random 128-bit values, so
knowing one implies having submitted the job or read the spool.

## Why it cannot stop `lynx_codex`

- `lynx_codex` runs Codex **synchronously** inside one tool call: `Popen`
  as `lynx-coder` in a new session, then `communicate(timeout=120)`, then
  `killpg(SIGKILL)` on timeout (`lynx/tools/agent/lynx_codex_tool.py:33-41`).
- It takes only `prompt` and `model`, has no `nrp_id`
  (`local_calls/lynx_codex.json`), and never imports the job queue.
- There is therefore no job ID to give `AGENT_CANCEL`. A wrapper would always
  answer `cancelled=0`.
- It is already bounded: 120 s inside the tool, and 130 s in the manifest.

## Proposal for a real `lynx_codex` stop (not implemented; needs Aria)

1. **Run record.** In `lynx_codex_tool.py`, after `Popen`, atomically write
   a root-owned 0600 run record to `/run/lynx/codex-run.json` containing
   `pid`, `pgid`, `uid`, and the process start time
   (`/proc/<pid>/stat` field 22). Remove it when the run finishes.
2. **Stop tool.** Add `lynx_codex_stop` (effect `stops`, no inputs).
   It reads the record and confirms all of the following before acting:
   - `/proc/<pid>` exists;
   - its start time matches, so the PID was not reused;
   - its UID is `lynx-coder`;
   - its executable is `/usr/local/libexec/lynx/codex`.

   Only then does it send `killpg(pgid, SIGTERM)`, waits up to 3 s, then
   sends `SIGKILL`. It reports one of `stopped`, `not_running`, or
   `refused:<reason>`.
3. **Tests** would cover: no record, stale record, reused PID, wrong UID or
   executable, a process that ignores SIGTERM, and two stops in a row. All
   would use fixture `/proc` trees.
4. **Caller behaviour.** The `lynx_codex` call that was stopped returns the
   existing "Codex task failed" error. Callers block during `lynx_codex`, so
   a stop must come from a second, concurrent session, for example an
   operator on Nexus.

Optional, separately: if the agent queue is later exposed to agents through
`AGENT_SUBMIT`/`STATUS`/`RESULT` tools, a `lynx_agent_cancel` wrapper becomes
meaningful. It should describe itself as "withdraw a pending job", never as
"stop".

## Evidence

`lynx/tools/agent/test_agent_cancel_contract.py` pins these claims against the
real handler and queue, using a temporary spool:
- a pending job is removed, and cancelling again is idempotent;
- missing, running and finished jobs all give `cancelled=0` and are left
  unchanged;
- invalid IDs and numeric arguments are rejected;
- a symlinked pending file is refused;
- `lynx_codex` takes no job ID, has no NRP ID, and never imports the queue.

```sh
python3 -m unittest discover -s lynx/tools/agent -p 'test_agent_cancel_contract.py'
```
