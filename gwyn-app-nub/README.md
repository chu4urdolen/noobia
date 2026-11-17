# Gwyn App Nub

Gwyn App Nub is Noobia's planned Claude Code coding agent on Nexus. The
workspace is `/noobia/gwyn-app-nub/workspace`, with its own Git repository.
Claude Code 2.1.311 was installed from Anthropic's official native Linux
installer on 2026-11-14. The CLI is `/home/aria/.local/bin/claude`.

`/noobia/gwyn-app-nub/launch` opens Claude Code in Gwyn's workspace. It sets
`CLAUDE_CONFIG_DIR=/noobia/gwyn-app-nub/private/claude`, so Gwyn's sessions,
settings, and authentication are separate from Aria's home configuration.
The private directory is mode 0700 and ignored by Noobia's Git repository.

Authentication is pending. When Noob is ready, run
`/noobia/gwyn-app-nub/auth` in a Nexus terminal. That invokes Claude Code's
own Anthropic Console login flow with API billing. Alternatively, an
`ANTHROPIC_API_KEY` supplied in the launching shell is supported by Claude
Code; do not put a key in Git, a chat message, or a command-line argument.
After login, run `/noobia/gwyn-app-nub/launch` and check `/status` in Claude
Code before any paid coding task.

The initial setup leaves Gwyn unpaired. A Dushich handoff and dashboard
adapter can be added after authentication and a first verified Claude Code
conversation, when the real session format and permission behavior can be
checked. The existing Dushich local GPU runtime does not use Claude API
tokens.

Official references: [installation](https://code.claude.com/docs/en/setup),
[authentication](https://code.claude.com/docs/en/authentication), and
[CLI commands](https://code.claude.com/docs/en/cli-reference).
