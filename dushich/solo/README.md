# Solo Dushich

`/noobia/dushich/solo/launch` starts Dushich's separate Codex CLI in his
own `/noobia`, backed by local Ollama `qwen3.8:27b` on the
Nexus GPU. Noob granted the solo agent Aria-level host permissions on
2026-11-14. The solo launcher therefore runs under Aria's Unix account with
Full Access (`danger-full-access`, approval `never`) and a separate Codex home
at `private/codex`. This is full host authority, including Aria's existing
passwordless sudo; use it only for solo work. The paired Dushich handoff
runner now has full Codex and Unix account access too.

This directory also holds the [Nexus Forge](../../common/FORGE.md) window
(`nexus_forge.py`, its avatar helpers, and the `nexus-forge.desktop`
autostart source).

Solo role instructions are in [`AGENTS.md`](AGENTS.md), linked into
`private/codex/AGENTS.md`. The helper has separate instructions in
[`../coding/AGENTS.md`](../coding/AGENTS.md). The shared workspace no longer
contains an `AGENTS.md`.

The launcher opens a single tmux pane for a conversation that belongs to
Dushich alone. Use `--detached` for a background terminal and `--resume ID`
or `--attach ID` for an earlier or running conversation. The earlier solo
conversation was copied into the separate Codex home so it can resume with
its history; the original transcript remains in Dushich's home as a backup.

Solo conversation IDs are registered in `private/conversations.json` (mode
0600), which is excluded from Git. Historical home data is archived under `coding/private/`.
