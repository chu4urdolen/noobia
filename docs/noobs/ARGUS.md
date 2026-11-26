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

The first [local historical index](../../argus/HISTORIAN.md) now runs on Argus's
Pi and indexes his existing event archive without changing its originals.
