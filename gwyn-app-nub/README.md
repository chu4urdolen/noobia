# Gwyn App Nub

Gwyn App Nub is Noobia's Claude Code coding agent and app-writer on Nexus,
active since 2026-11-18. Gwyn's role file and personality are in
[`AGENTS.md`](AGENTS.md). Claude Code starts in this folder, part of the
shared `/noobia` repository; its [`CLAUDE.md`](CLAUDE.md) imports `AGENTS.md`.
Claude Code 2.1.311 was installed from Anthropic's official native Linux
installer on 2026-11-14. The CLI is `/home/aria/.local/bin/claude`.

`/noobia/gwyn-app-nub/launch` opens a tmux workshop like Banshee's:
Claude Code in Gwyn's home folder with full terminal width
(`noobia-gwyn-*` sessions). `--detached` prints a
reattach command, `--attach ID` reattaches, `--resume CLAUDE_SESSION_ID`
continues an earlier conversation, and `--plain [claude args]` runs bare
Claude Code without tmux. New conversations start with
`--session-id` equal to the tmux session ID, so the bridge knows the
transcript path. It sets
`CLAUDE_CONFIG_DIR=/noobia/gwyn-app-nub/private/claude`, so Gwyn's sessions,
settings, and authentication are separate from Aria's home configuration.
Gwyn's commits from the launcher are authored as `Gwyn App Nub`.

Noob authorized Gwyn to run without approval prompts on 2026-11-18. The
private `settings.json` sets `permissions.defaultMode` to `bypassPermissions`
with the dangerous-mode confirmation skipped. Gwyn still follows the consent
and high-impact boundaries in `AGENTS.md`.
The private directory is mode 0700 and ignored by Noobia's Git repository.
Gwyn's `CLAUDE.md` points to the shared
[coding instructions](/noobia/common/AGENTS.md) for directory, tool, service,
and Git conventions.

Authentication is complete (checked 2026-11-18, Claude Code 2.1.327). To
re-authenticate, run `/noobia/gwyn-app-nub/auth` in a Nexus terminal. That
invokes Claude Code's own Anthropic Console login flow with API billing. Alternatively, an
`ANTHROPIC_API_KEY` supplied in the launching shell is supported by Claude
Code; do not put a key in Git, a chat message, or a command-line argument.
Start Gwyn with `/noobia/gwyn-app-nub/launch`.

## Dushich helper

Gwyn reaches Dushich through the shared `dushich` MCP server,
[`common/dushich/mcp.py --agent gwyn`](../common/dushich/README.md),
registered with `claude mcp add --scope user`. It gives Gwyn the same tools
as every agent. They need `NOOBIA_GWYN_SESSION`, which the launcher sets;
`--plain` sessions see the tools but get a clear error. Gwyn's helper thread
is updated only when Gwyn asks a question, so the first question in a long
conversation can take several minutes.

Verified 2026-11-18: `dushich_ask` answered about this conversation, and
handoff `20261118T201446Z-0b57ea1f` passed independent verification in
Dushich's workspace. The Nexus Forge bottom-right quadrant is now
"Gwyn + Dushich Helper" and animates both avatars from the tmux panes.
Dushich's local GPU runtime does not use Claude API tokens.

A `SessionStart` hook in Gwyn's private settings runs `session_link.py` on
every start and resume. It records which Claude Code transcript a launcher
session is really using in `private/session-links/`, so the bridge follows a
conversation resumed with `/resume` instead of the launcher's original ID.

`dushich_explore` / `dushich_explore_wait` wrap the shared `dushich-explore`
command: Dushich answers "where is / how does" questions about Nexus and
records what he finds in the forge-db path atlas. Gwyn also has the user-scope
`noobia` MCP server (`/noobia/common/mcp/noob_mcp.py`) for Lynx, Iris, and
local tools.

Official references: [installation](https://code.claude.com/docs/en/setup),
[authentication](https://code.claude.com/docs/en/authentication), and
[CLI commands](https://code.claude.com/docs/en/cli-reference).
