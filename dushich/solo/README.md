# Solo Dushich

`/noobia/dushich/solo/launch` starts Dushich's separate Codex CLI in his
own `/noobia/dushich/workspace`, backed by local Ollama `gpt-oss:20b` on the
Nexus GPU. Noob granted the solo agent Aria-level host permissions on
2026-11-14. The solo launcher therefore runs under Aria's Unix account with
Full Access (`danger-full-access`, approval `never`) and a separate Codex home
at `private/codex`. This is full host authority, including Aria's existing
passwordless sudo; use it only for solo work. The paired Dushich handoff
runner now has full Codex and Unix account access too.

Solo role instructions are in [`AGENTS.md`](AGENTS.md), linked into
`private/codex/AGENTS.md`. The helper has separate instructions in
[`../coding/AGENTS.md`](../coding/AGENTS.md). The shared workspace no longer
contains an `AGENTS.md`; the foreman role is prepared separately in
[`../foreman/AGENTS.md`](../foreman/AGENTS.md) and has no active launcher.

The launcher opens a single tmux pane for a conversation that belongs to
Dushich alone. Use `--detached` for a background terminal and `--resume ID`
or `--attach ID` for an earlier or running conversation. The earlier solo
conversation was copied into the separate Codex home so it can resume with
its history; the original transcript remains in Dushich's home as a backup.

The Dushich web page has a **Solo Dushich** panel with the same conversation
selector and input. It reads visible user and assistant messages from
Dushich's Codex transcripts. Paired Aria/Banshee handoffs continue to appear
in their own panels; the solo panel excludes known handoff threads.

Solo conversation IDs are registered in `private/conversations.json` (mode
0600), which is excluded from Git. The web service reads migrated solo
transcripts from `private/codex/sessions` and opens only IDs in the solo
registry. Historical home data is archived under `coding/private/`.
