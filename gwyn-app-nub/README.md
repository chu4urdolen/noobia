# Gwyn App Nub

Gwyn App Nub is Noobia's Claude Code coding agent and app-writer on Nexus,
active since 2026-11-18. Gwyn's role file and personality are in
[`AGENTS.md`](AGENTS.md). The workspace is `/noobia/gwyn-app-nub/workspace`,
with its own Git repository; its `CLAUDE.md` imports `AGENTS.md`.
Claude Code 2.1.311 was installed from Anthropic's official native Linux
installer on 2026-11-14. The CLI is `/home/aria/.local/bin/claude`.

`/noobia/gwyn-app-nub/launch` opens Claude Code in Gwyn's workspace. It sets
`CLAUDE_CONFIG_DIR=/noobia/gwyn-app-nub/private/claude`, so Gwyn's sessions,
settings, and authentication are separate from Aria's home configuration.
The private directory is mode 0700 and ignored by Noobia's Git repository.
Gwyn's workspace `CLAUDE.md` points to the shared
[coding instructions](/noobia/common/AGENTS.md) for directory, tool, service,
and Git conventions.

Authentication is complete (checked 2026-11-18, Claude Code 2.1.327). To
re-authenticate, run `/noobia/gwyn-app-nub/auth` in a Nexus terminal. That
invokes Claude Code's own Anthropic Console login flow with API billing. Alternatively, an
`ANTHROPIC_API_KEY` supplied in the launching shell is supported by Claude
Code; do not put a key in Git, a chat message, or a command-line argument.
Start Gwyn with `/noobia/gwyn-app-nub/launch`.

Gwyn is not yet paired with Dushich. A Dushich handoff and dashboard
adapter can be added after authentication and a first verified Claude Code
conversation, when the real session format and permission behavior can be
checked. The existing Dushich local GPU runtime does not use Claude API
tokens.

Official references: [installation](https://code.claude.com/docs/en/setup),
[authentication](https://code.claude.com/docs/en/authentication), and
[CLI commands](https://code.claude.com/docs/en/cli-reference).
