# Lynx's coder

Codex CLI as Lynx's code-writing personality (Gwyn, 2026-11-25). It is set up
on its own now; the button and the hook-up come later, when Banshee's
debug screen is ready.

| File | On Lynx | Mode |
| --- | --- | --- |
| `AGENTS.md` | `/home/lynx-coder/.codex/AGENTS.md` (her personality) | 600 lynx-coder |
| `config.toml` | `/home/lynx-coder/.codex/config.toml` | 600 lynx-coder |
| `lynx-code` | `/usr/local/bin/lynx-code` | 755 root |
| (not in git) | `/home/lynx-coder/.config/noobia/nexus.key` | 600 lynx-coder |
| (not in git) | `/etc/sudoers.d/lynx-coder`: `lynx-coder ALL=(ALL:ALL) NOPASSWD: ALL` | 440 root |

- **Binary:** Codex 0.167.0 at `/usr/local/libexec/lynx/codex`.
- **Mind:** Qwen `qwen3.8-27b` through the Nexus proxy (`192.168.100.106:8080`, Responses API).
- **Freedom:** no approvals (`approval_policy = "never"`), no sandbox (`danger-full-access`), and full root through sudo.

## Hooking it up later

Run `lynx-code` as root (it switches to `lynx-coder`). Every interface Codex has goes through it:

| Use | Command |
| --- | --- |
| A person, interactive | `lynx-code` |
| One task, plain text | `lynx-code exec "task"` |
| One task, a JSON event stream (for a screen or an agent tool) | `lynx-code exec --json "task"`: one JSON event per line (thread started, commands, messages, turn completed) |
| Continue the last task | `lynx-code exec resume --last "follow-up"` |
| A long-lived server for a UI | `lynx-code app-server` (JSON-RPC over stdio, experimental in 0.167) |

- **A screen button** (Banshee's debug screen) should start `lynx-code exec --json` in the background and draw the events.
- **Lynx herself** calls it through her `lynx_codex` tool (`lynx/tools/agent/lynx_codex_tool.py`). That tool still uses the old `workspace-write` sandbox, which cannot start on this kernel, so it must switch to `lynx-code exec --json` when the hook-up is built.
- **Qwen has one slot.** A coder task and her reflexes wait for each other. Run it while Dushich is idle.
