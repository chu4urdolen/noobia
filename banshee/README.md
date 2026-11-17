# Banshee's Nexus coding workspace

Launch Banshee from a Nexus terminal with `noobia-banshee` (or
`/noobia/banshee/launch`). This opens
a two-pane tmux workshop: Google Antigravity CLI (`agy`) in
`/noobia/banshee/workspace` on the left, and Dushich's live local coding
activity on the right. Banshee's Antigravity process runs under the shared
`aria` Unix user. Her [AGENTS.md](/noobia/banshee/AGENTS.md) is linked into
the workspace and points to the [Noobia contact book](../common/CONTACT-BOOK.md).
The workspace has its own Git history; the first smoke
test is in `workspace/smoke-test/`.

The `dushich` MCP server gives Banshee `dushich_context_status`,
`dushich_ask`, `dushich_start`, `dushich_status`, `dushich_wait`, and
`dushich_report`. Use `dushich_ask` for a direct question to the linked helper
thread. Coding handoffs require a specific expected file and independent test. Dushich runs
through his separate Codex CLI and local Ollama `gpt-oss:20b` on Nexus's GPU.
His own workspace and verified Git history remain separate. The monitor shows
complete visible command and test activity. Reattach a detached two-pane
session with the command printed by `noobia-banshee --detached`.

`noobia-banshee --conversation ID` resumes an existing Antigravity conversation in a
new two-pane session. The disabled [Dushich web monitor](../dushich/web/README.md)
can display Banshee alongside Aria and merge visible Noob/Banshee/Dushich
results when started manually. Messages are sent through the terminal CLI. Each Dushich
handoff now receives bounded recent visible Noob/Banshee dialogue
automatically; intermediate Antigravity working steps are excluded.

For Banshee conversations created after `noobia-banshee-helper-mirror.service`
was enabled, a local watcher also maintains one persistent Helper Dushich Codex
thread per Banshee conversation. It checks for new visible Noob prompts and
Banshee final answers every two seconds, archives them under
`/home/aria/.codex/dushich-bridge/helper-mirror/banshee/CONVERSATION_ID/`, and
sends new turns to the linked helper thread. Existing conversations are not
backfilled. Intermediate Antigravity steps remain excluded by the visible
dialogue reader. Check service health with
`systemctl --user status noobia-banshee-helper-mirror.service`.

The CLI binary is installed at `/home/aria/.local/bin/agy` (version 1.5.9
on 2026-11-15). Banshee shares the `aria` Unix user and `/home/aria/.gemini`
Antigravity state directory while keeping her own `/noobia/banshee/AGENTS.md`
and `/noobia/banshee/workspace`. Her `dushich` MCP server is configured and enabled.

Noob confirmed the account has **Google AI Plus**, correcting an earlier Pro
description. The CLI header showed **Antigravity Starter Quota**, and `/usage`
showed a weekly limit. Google's Antigravity documentation groups Free and Plus
together for model access and reserves higher, five-hour-refresh quota for Pro
and Ultra. The observed CLI quota is consistent with Plus; there is no
unresolved Pro entitlement issue. The paid membership itself is managed in
Google One (<https://one.google.com/>).

The CLI reported that its terminal sandbox is unavailable on this Ubuntu host
because AppArmor restricts unprivileged user namespaces. Noob explicitly
authorized Banshee to run without Antigravity tool permission prompts on
2026-11-15. `/noobia/banshee/launch` therefore starts her with
`--dangerously-skip-permissions`, which auto-approves terminal commands, edits,
and MCP calls. This applies to newly launched sessions; an already running CLI
must be restarted to pick it up. Banshee still follows the consent and
high-impact system change boundaries in her `AGENTS.md`.

The official installation and account guidance is at
<https://antigravity.google/docs/cli/tutorial/> and
<https://antigravity.google/docs/install?tab=cli>.
