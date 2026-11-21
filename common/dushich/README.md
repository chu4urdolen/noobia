# Dushich connection

How every cloud agent (Aria, Banshee, Gwyn) reaches Dushich, the local
helper on Nexus's GPU. How to *work* with him is in the shared
[`AGENTS.md`](../AGENTS.md#dushich-everyones-local-collaborator); this folder
is the code behind it.

| File | Role |
| --- | --- |
| [`agents.py`](agents.py) | The agent table: each agent's home, session variables, transcript reader, and helper. Paths follow `$NOOBIA` (default `/noobia`). |
| [`mcp.py`](mcp.py) | The `dushich` MCP server, `mcp.py --agent aria\|banshee\|gwyn`. Every agent gets the same tools. |
| [`bridge.py`](bridge.py) | Verified handoffs for Banshee and Gwyn (`--agent`), and the right-hand monitor pane (`monitor`). Aria's handoffs use her own Codex bridge, [`aria/dushich-bridge`](../../aria/dushich-bridge). |
| [`session_links.py`](session_links.py) | Persistent SQLite links between launcher/tmux sessions and agent conversation IDs, with CLI hook handlers for Antigravity and Claude Code. |
| [`delegate-dushich`](delegate-dushich) | Runs one handoff through Dushich's task runner and prints the verified report. Used by every bridge; do not call it directly. |
| [`helper_mirror.py`](helper_mirror.py) | Helper Dushich threads for Aria's Codex conversations, plus the shared `run_turn` every helper uses. |
| [`helper_banshee.py`](helper_banshee.py), [`helper_gwyn.py`](helper_gwyn.py) | Helper threads for Banshee (mirrored continuously) and Gwyn (updated when asked). |
| [`transcript_antigravity.py`](transcript_antigravity.py), [`transcript_claude.py`](transcript_claude.py) | Read only the visible turns (the human's prompts, the agent's final answers) from each CLI's transcripts. |
| `noobia-dushich-helper-mirror.service`, `noobia-banshee-helper-mirror.service` | User units for the continuous mirrors. |

## Registering the MCP server

| Agent | Where | Entry |
| --- | --- | --- |
| Aria | `~/.codex/config.toml` | `[mcp_servers.dushich]` `command = "/usr/bin/python3"`, `args = ["/noobia/common/dushich/mcp.py", "--agent", "aria"]` |
| Banshee | `~/.gemini/config/mcp_config.json` | `"dushich": {"command": "/usr/bin/python3", "args": ["/noobia/common/dushich/mcp.py", "--agent", "banshee"]}` |
| Gwyn | `claude mcp add --scope user dushich -- /usr/bin/python3 /noobia/common/dushich/mcp.py --agent gwyn` | |

Each launcher sets the session variables the tools need
(`NOOBIA_BANSHEE_SESSION`, `NOOBIA_GWYN_SESSION`). Aria's session is inferred
from Codex's own state.

## Helper mirrors

```sh
install -m 644 common/dushich/noobia-*-helper-mirror.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now noobia-dushich-helper-mirror.service noobia-banshee-helper-mirror.service
```

State lives in `~/.codex/dushich-bridge/helper-mirror/`. If a helper
thread's Codex session can no longer be resumed, the next turn starts a fresh
thread instead of retrying the broken one.

## Adding an agent

Add a row to `agents.py`. Write a `transcript_<cli>.py` with `read(path)` and
`locate(conversation_id)` if the CLI is new, and a helper for `dushich_ask`.
Then register `mcp.py --agent NAME` in the agent's CLI and start
`bridge.py --agent NAME monitor` in its launcher.

## Tests

```sh
python3 -m unittest discover -s common/dushich -p 'test_*.py'
```

`banshee/dushich_bridge.py`, `banshee/banshee_helper_mirror.py`, and
`aria/delegate-dushich` are temporary compatibility shims for sessions started
before 2026-11-20. Remove them once every agent has been restarted.
