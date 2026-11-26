# Argus code map

Argus's own repository is [`argus/`](../../argus/). Its services, tools,
tests, and web interface live under `argus/services/`, `argus/tools/`,
`argus/tests/`, and `argus/web/`. Argus's logs and backups are historical
records; check the live host and mounted storage before modifying either.

Argus was reachable and his Codex CLI worked on 2026-11-26.
The [live audit](../../argus/STATUS-2026-11-26.md) records the boot, NVMe,
service, and archive state. His recovered [role file](../../argus/AGENTS.md)
and [Rose's backlog](../../argus/ARGUS_BACKLOG_v2.md) are the starting points
for the historian build.

The [current historian handoff](../../argus/STATUS-2026-11-27.md) records the
latest evidence counts, backup verification, Dushich review, and remaining work.

The [historian evidence index](../../argus/HISTORIAN.md) runs on Argus's Pi. It
preserves the original archive, exact Forge exports including moved archived
notes, and versioned daily evidence ledgers. The [named-job worker](../../argus/JOBS.md)
handles archive import and ledger construction on demand. The Nexus MCP server
exposes authenticated Argus status, collection, ledger, and job tools over pinned
SSH. A verified off-device backup lives in Argus's ignored private area on Nexus.
Journal collection is paused until the coding Noobs have continuity features;
Council work is outside this historian slice.

For a live conversation, [Argus's tmux launcher](../../argus/SESSION.md) keeps
one Codex terminal alive across SSH disconnects and can resume a saved session.
