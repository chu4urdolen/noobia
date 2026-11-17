# Dushich code map

Dushich uses he/him pronouns.

The local [`dushich/`](../../dushich/) directory contains physical design work
under `3dprint/`. The Nexus coding agent is documented in
[`dushich/coding/README.md`](../../dushich/coding/README.md), with its launcher
and configuration sources beside it. Its live workspace is
`/noobia/dushich/workspace`; its separate Codex history is in
`/noobia/dushich/coding/private/codex`. This is a Nexus runtime, not phone firmware.
The workspace now holds only the clean verified-task Git repository and Forge
runtime data. Older task projects are archived under
`/noobia/dushich/private/backups/task-workspace-files-20261117/`.
The [duplicate-filename tool](../../dushich/tools/README.md) can scan
`/noobia` without blocking a terminal and writes complete private JSON reports.
The [coding trial](../../dushich/coding/TRIAL-STATUS.md) records verified tool,
test, Git, memory, performance, and limitation evidence.

The Nexus web front page at `http://127.0.0.1:8765/` now controls a separate,
off-by-default [Foreman role](../../dushich/foreman/AGENTS.md). Its project
registry is `/noobia/dushich/workspace/forge.db`; `conversation_id` links a
project to a coding-agent conversation. The front-page liaison watches
`/noobia/dushich/workspace/human-help-flags/` and shows requests for Noob's
physical help. The [web operating notes](../../dushich/web/README.md) describe
the control flow. The [helper role](../../dushich/coding/AGENTS.md) can access
the project database, while [Solo Dushich](../../dushich/solo/AGENTS.md) has
his own instructions. Noob granted both roles full Codex host access and
passwordless sudo for the `dushich` Unix account on 2026-11-14.

No Council or Argus integration has been granted to this runtime yet. Add the
phone's actual firmware or runtime path here when it is located.
