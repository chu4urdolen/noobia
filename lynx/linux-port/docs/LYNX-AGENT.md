# Lynx local agent and supervised queue

Prepared and live-tested from 2026-11-06 on native Alpine V53. The one-shot
agent now runs through a supervised queue; jobs still require explicit
submission, and there is no autonomous scheduler.

## Installed path

- `/usr/local/bin/lynx-agent` runs the Responses function-call loop locally on
  Lynx. When Nexus `/health` responds, it uses the authenticated local proxy
  (`gpt-oss-20b`). When Nexus is unreachable it selects OpenAI Responses, but
  no cloud key has been installed, so that path currently fails closed.
- `/usr/local/share/lynx/agent-tools` contains the local Noob hardware
  wrappers plus `lynx_agent_health` and `lynx_queue_health`. Adding a `.json` manifest and
  matching `.sh` script makes a tool available to the agent. An `nrp_id` in
  the reserved 500–999 range also registers it as an NRP/1 native when
  `lynx-noobd` starts. Arguments for NRP plugins use `CALL_TEXT` with compact
  JSON, bounded by the common 255-byte ASCII ABI.
- `/var/log/lynx-agent.jsonl` records backend and tool names/results. It does
  not record prompts, credentials, arguments, or tool output.
- The Nexus proxy credential is stored on Lynx at
  `/etc/lynx/nexus-inference.key`, mode 0600. No credential is in this repo.
- The reviewed pre-catalog NRP daemon remains on Lynx as
  `/usr/local/bin/lynx-noobd.before-agent-catalog`; `boot_a` was not modified.

## Verified

The agent answered a camera status query through Nexus and matched the direct
`lynx-hardware` report (`interface_ready=true`, `validated=false`). A second
request produced an audited `lynx_flashlight` tool call. Local and authenticated
remote NRP/1 `CALL LYNX_AGENT_HEALTH` both returned success. Lynx remained on
the same boot with no health issues. Receipts:

- `lynx/logs/agent-install-1793972962630693997/result.json`
- `lynx/logs/agent-catalog-nrp-1793973194539143940/result.json`

The generic hardware camera inventory still reports `validated=false`; that
status predates separately verified GC02M1 and IMX355 frame trials and should
be reconciled before the agent uses it for camera decisions.

The official ARM64 musl Codex CLI 0.167.0 archive was checksum-verified and
executed from a 384 MiB RAM mount as `codex-cli 0.167.0`. Keeping its 114 MiB
archive on Lynx's 1 GiB root caused `root_space_low`, so the phone-side archive
was removed. The verified copy remains at
`lynx/downloads/codex-aarch64-unknown-linux-musl-rust-v0.167.0.tar.gz` on
Nexus. The RAM binary lasts only until Lynx reboots. Do not treat this as a
persistent Codex installation. The staging tool now removes its temporary
phone-side archive automatically and rechecks health.

On 2026-11-08, the ext4 root was expanded to 218.7 GiB (209.3 GiB free), so
the old root-space blocker is resolved. A persistent Codex installation was
started while Lynx was healthy and charging at 34–35%. The first uncompressed
binary stream lost Wi-Fi contact; SSH on both rescue and Alpine ports then
timed out. The installer stopped before promoting its `.incoming` file, so
`/usr/local/libexec/lynx/codex` and the live `lynx-codex-tool` were not
changed. The host source now targets that persistent path and a revised
installer transfers the verified compressed archive in resumable 4 MiB
chunks. This revised transfer has not yet run on Lynx. Check the phone's live
state and the partial file before retrying; do not infer a completed install
from the presence of an `.incoming` file.

Later on the same boot, Lynx returned to Wi-Fi with a healthy 44% battery. The
resumable compressed transfer completed and installed the verified CLI at
`/usr/local/libexec/lynx/codex` (SHA-256
`2fe94d848540ff2a6868c7ebcc494126a974aa409711676d14fa0379e49e6143`).
The unprivileged `lynx-coder` user executed `codex-cli 0.167.0` there. The
installer updated `/usr/local/bin/lynx-codex-tool` and retained its previous
version at `/usr/local/bin/lynx-codex-tool.before-persistent-20261108`. A
permission error in the first test exposed root-only parent directories; both
were changed to mode 0755 and the installer source was corrected. A direct
bounded Codex test returned `Lynx persistent Codex ready.` An end-to-end local
agent request then invoked `lynx_codex`, returned `Lynx persistent tool ready.`,
and recorded `ok=true` in `/var/log/lynx-agent.jsonl`. Lynx stayed on the same
boot with no health issues. Receipt:
`lynx/logs/codex-persistent-1794174582133290564/result.json`. The Nexus
inference proxy was started manually for this test and subsequently enabled at
boot. No cloud key is installed on Lynx.

Nexus now has `noobia-gpu-power-limit.service` enabled before `ollama.service`.
It reapplies the attended 400 W RTX 5090 cap after a Nexus reboot. Ollama
requires that unit, and `noobia-inference-proxy.service` is enabled at boot.
All three services were active after the configuration; the proxy answered
`/health`. This establishes the startup configuration, not a reboot trial.

## Supervised local queue, 2026-11-09

The agent now accepts `--stdin`, so private prompts are not placed in process
arguments. A root-owned queue at `/var/lib/lynx-agent/jobs` uses mode 0700;
job and result files use mode 0600 and atomic writes. The worker checks Lynx
health, battery, charging current, and temperatures before claiming a job. It
runs one one-shot agent process at a time, with a three-minute timeout and an
OpenRC `supervise-daemon` supervisor. Its logs contain job IDs and outcomes,
not prompts or credentials. The queue status command omits prompt and result
text; result retrieval is a separate root-only command.

The local control is `/usr/local/bin/lynx-agentctl`. Submit a prompt through
stdin; use `status JOB_ID` and `result JOB_ID` to inspect it. `stop` creates a
persistent stop marker and stops the OpenRC worker. `start` removes that marker
and starts the worker; `cancel JOB_ID` removes a pending job. The phone power
control remains an independent physical override. OpenRC starts the worker
on future Alpine boots, but no job runs until one is explicitly submitted.

The install receipt is
`lynx/logs/agent-worker-install-1794175331068288154/result.json`. Twelve
Nexus tests passed before installation. On Lynx, one queued prompt returned
`Lynx queue works.`. A second job remained pending while the worker was
stopped, then returned `Lynx resume works.` after restart. The queue directory
and both result files had the expected private modes; OpenRC reported the
service started in the default runlevel. Lynx remained healthy at 48% battery
on the same boot. This verifies the same-boot queue and local stop; cold-boot
startup and in-flight cancellation still need a separate attended check.
An isolated in-flight stop test now sends SIGTERM to a worker executing a
sleeping fake agent. The worker terminates the child process group, records a
failed result, and exits promptly. This checks the signal path offline; it
does not replace a live hardware stop trial.

The worker now waits for an available inference backend before claiming a
pending job. A healthy Nexus proxy and its local key permit execution; a Nexus
HTTP error leaves the job pending instead of spending cloud credits. If Nexus
is unreachable, a separately installed cloud key would permit the cloud path.
Four isolated worker tests pass. The first same-boot update briefly left the
worker restarting because its import used the source module name
`lynx_agent` while the installed file is `lynx-agent`. The queue retained the
pending job. A second guarded update fixed the import, and that job returned
`Lynx gate ready.` The worker is active and health is clear. Receipts:
`lynx/logs/agent-worker-gate-1794176850342902270/result.json` and
`lynx/logs/agent-worker-gate-1794176912492163085/result.json`. The guarded
installer now checks a staged worker import before stopping the service.

Dushich contributed an isolated queue prototype (commit `174a3ab0ad67`), but
its first security revision failed the independent symlink test. That revision
was preserved at `lynx/logs/dushich-agent-queue-failed-20261108/` and was not
installed. The deployed queue is the separately reviewed implementation in
`lynx/tools/agent/lynx_agent_queue.py`.

## Authenticated remote agent queue, 2026-11-09

The existing Nexus-authenticated NRP/1 connection exposes four asynchronous
agent calls: `AGENT_SUBMIT` (native 510), `AGENT_STATUS` (511), `AGENT_CANCEL`
(512), and `AGENT_RESULT` (513). Submission accepts at most 255 printable ASCII
characters because it uses the common `CALL_TEXT` ABI. Result retrieval uses
bounded 96-byte pages with `CALL_MIXED`, so the NRP request does not block on
inference. The phone still executes one queued job at a time and keeps the
local stop marker and health gate. These calls use the existing authenticated
NRP server; there is no unauthenticated agent endpoint.

On Nexus, use `lynx/tools/lynx_agent_remote.py`:

```sh
printf 'Reply exactly Lynx ready.\n' | python3 /noobia/lynx/tools/lynx_agent_remote.py submit
python3 /noobia/lynx/tools/lynx_agent_remote.py status JOB_ID
python3 /noobia/lynx/tools/lynx_agent_remote.py result JOB_ID
python3 /noobia/lynx/tools/lynx_agent_remote.py cancel JOB_ID
```

The NRP installation receipts are
`lynx/logs/agent-nrp-queue-1794175602897947773/result.json` and
`lynx/logs/agent-nrp-queue-1794175724344289207/result.json`. Nexus tests
covered submission bounds, status, cancellation, and result paging. A live
Nexus request returned `Lynx remote queue works.` via both the local phone
result file and authenticated NRP result paging. A queued job was remotely
cancelled while the worker was stopped; the worker was then restarted. The
Nexus client retrieved the same completed result and status successfully.
The client then submitted a fresh live job, observed `finished` through
`status`, and retrieved the exact reply `Lynx client ready.` through `result`.
Its result reader rejects malformed pages and inconsistent page metadata;
three isolated paging tests pass in `lynx/tools/test_lynx_agent_remote.py`.
An unprivileged `lynx-coder` account and workspace now exist on the phone.
Codex CLI used its Nexus Responses provider to complete a short task there,
replying `Lynx coding ready.` with `sandbox=workspace-write` and network access
to the proxy. The `lynx_codex` agent tool then ran a second bounded task as
that user and returned `Codex tool ready.` An end-to-end agent request invoked
`lynx_codex` and its audit log recorded `ok=true`; the nested Codex reply was
`Nested Codex ready.` It accepts only `gpt-oss-20b` for
now and is not exposed as a synchronous NRP native, because a long coding job
would stall the Noobia protocol loop. It was agent-callable during the first
RAM trial; the persistent CLI and agent tool installation above supersedes
that trial. Codex warned that the proxy model catalog
could not be decoded and used fallback metadata for `gpt-oss-20b`; the task
still completed. The tested config is `lynx/tools/agent/codex-config.toml`.

Dushich independently added three mocked backend-selection tests in his own
workspace (commit `90b3941`); after review and a portable-path correction,
these were added to `lynx/tools/agent/test_backend_selection.py`. Five agent
tests passed on Nexus at that checkpoint. His earlier interrupted architecture draft is preserved
as an unreviewed checkpoint and contains wrong service paths.

## Next gates

On 2026-11-15 Lynx returned on a new boot
`0aa70b0f-1449-43e7-acf5-1bb5680c2a0f`. Alpine 3.24.2 reported no health
issues, 63% battery, and the OpenRC agent worker started. An authenticated NRP
submission on that boot finished with the exact reply `Lynx reboot ready.`
This verifies worker startup and Nexus inference on a subsequent boot. The
record does not establish whether the boot was from full power-off or a warm
reboot; a controlled cold-boot trial remains separate.

On that same boot, Dushich reviewed the worker path without changing files.
Aria adopted a focused spawn-failure check: the worker now records a failed
result if starting the agent process raises `OSError`, and its signal path
handles a process-exit race. Five isolated worker tests passed. The guarded
update retained the old worker at
`/usr/local/bin/lynx-agent-worker.before-spawn-recovery-20261115`; receipt
`lynx/logs/agent-worker-spawn-recovery-1794770627307090055/result.json`.
After installation, an authenticated queued job returned `Lynx worker healthy`,
the service remained started, and Alpine reported no health issues.

The read-only `/usr/local/bin/lynx-agent-health` command now summarizes queue
counts, oldest pending age, stop state, and metadata integrity. It does not
read job payloads or print IDs, prompts, replies, or credentials. Three
isolated tests passed before guarded installation. On Lynx it reported seven
finished jobs, zero pending or running, no stop marker, and no privacy issues.
Receipt: `lynx/logs/agent-health-install-1794770775201797701/result.json`.
The same `lynx_queue_health` manifest is now available to Lynx's local agent
and as authenticated NRP/1 native 514. The NRP response carries only the four
validated aggregate fields (`counts`, `oldest_pending_seconds`, `stopped`,
`issues`) as bounded base64url JSON. Unexpected fields or issue names are
rejected before transmission. Nexus reads it with
`python3 /noobia/lynx/tools/lynx_agent_remote.py health`. Dushich's read-only
review found that the first wrapper would hide reports when it detected an
issue; the deployed wrapper returns the issue list instead. Nineteen host
runtime/client tests passed. The local agent call and authenticated NRP call
both returned seven finished jobs, none pending or running, and no issues.
The pre-update daemon is preserved at
`/usr/local/bin/lynx-noobd.before-queue-health-20261115`; receipt:
`lynx/logs/queue-health-catalog-1794771569794646349/result.json`.

1. Keep the verified V53 boot and V50 rescue images untouched. Test a
   controlled cold boot and a live in-flight local stop when Lynx is attended.
2. Supply a separately scoped phone cloud credential and test fallback only
   with Nexus unreachable. A healthy Nexus with a failed credential must not
   silently switch to cloud.
3. Define an explicit local stop and service recovery policy before running
   the agent continuously. Keep physical hardware controls bounded.
4. Complete the camera module cold-boot persistence gate, then main/front
   camera and SIM trials as separate kernel/hardware work.

Official [Codex CLI](https://learn.chatgpt.com/docs/codex/cli) and
[custom provider configuration](https://learn.chatgpt.com/docs/config-file/config-advanced)
documentation were checked for the later Codex step.
