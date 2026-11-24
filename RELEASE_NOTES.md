# Release Notes: Nexus Forge v1.0.0
## The Multi-Agent AI Linux Cockpit

The **Autonomous Republic of Noobia** is proud to release **Nexus Forge v1.0.0** — an open-source, local-first workshop where different artificial intelligences live, write code, and collaborate in real-time alongside one human.

```
 ┌──────────────────── Nexus Forge Cockpit (GTK3 + VTE) ───────────────────┐
 │  Aria (OpenAI Codex)      │ avatar │  Banshee (Google Antigravity)│ avatar │
 │  + Dushich monitor        │        │  + Dushich monitor           │        │
 ├───────────────────────────┼────────┼──────────────────────────────┼────────┤
 │  Dushich Solo (Local Qwen │ avatar │  Gwyn (Anthropic Claude Code)│ avatar │
 │  on RTX 5090 / Ollama)    │        │  + Dushich monitor           │        │
 └────────────────────────────────────────────────────────────────────────────┘
        │ dushich MCP bridge                       │ forge-db, semantic atlas
        ▼                                          ▼
  Dushich (local Ollama: qwen3.8:27b, 131k context, zero cloud token costs)
        │ keeps                                    │ compacts with
        ▼                                          ▼
  dushich/workspace/forge.db               dushich-summarizer
```

---

### Highlights in v1.0.0

1. **4 Live Terminal Quadrants (GTK3 + VTE 2.91)**
   - Resizable 2×2 terminal grid, each hosting an independent agent session in `tmux`.
   - **Quadrant Zoom**: Press `Ctrl+Shift+Z` or `F11`, or double-click any quadrant header to maximize that quadrant to fill the whole window; press again or `Escape` to return to the 2×2 grid.
   - **Session Resilience**: Reconnect card on terminal child exit, with intelligent backoff and crash-loop guards (Principle 10).

2. **Animated Avatar Sidebars**
   - Renders live visual states for each agent (`idle`, `working_1`–`working_4`, `final`).
   - Renders helper animations whenever a secondary agent (like Dushich) assists inside that quadrant.
   - Rose watches over the bottom of every sidebar.

3. **Live Token Badges**
   - Real-time hourly and weekly rate-limit percentage meters for cloud agents (`H/W: %/%`).
   - `Local: 100%` badge for local GPU inference.

4. **Dushich, The Local Watchmaker**
   - A local collaborator powered by `qwen3.8:27b` (131k context) on Ollama.
   - Takes verified coding handoffs through MCP tools.
   - Works in clean, isolated Git workspaces where tests, tool executions, and commits are independently validated.
   - Zero cloud token cost.

5. **Forge Memory (`forge-db`)**
   - Unified SQLite shared memory for the entire republic.
   - Path atlas, project notes, hardware readiness tracking, and tag taxonomy.
   - **Semantic Meaning Search**: Uses local vector embeddings (via Ollama `qwen3-embedding:0.6b` on GPU or FastEmbed CPU fallback) combined with lexical scoring.
   - Built-in collision detection prevents two agents from working on the same project simultaneously without explicit coordination.

6. **Iterative Context Summarizer (`dushich-summarizer`)**
   - Sentence-boundary window summarizer running entirely on the local GPU.
   - Iteratively digests massive conversation logs, transcripts, and source files so context windows never overflow.

7. **Turnkey Installer (`./install.sh`)**
   - One-command setup for any modern Linux system (Ubuntu, Debian, Fedora, Arch).
   - Non-destructive and idempotent.
   - Supports `./install.sh --check`, `./install.sh --dry-run`, and `./install.sh --config-only`.
   - Gracefully audits and warns for optional tools (`uv`, Ollama, cloud CLIs) without breaking installation.
   - Auto-provisions local Dushich configurations with relative, portable symlinks.

8. **Portable, User-Agnostic Launchers**
   - Dynamic user and home directory resolution (`$USER`, `$HOME`).
   - Works across custom user accounts and paths without hardcoded requirements.
   - Protected Git transport guards that never leak private keys or clobber custom environment variables.

---

### Quickstart

```bash
# 1. Clone the repository at v1.0.0
git clone --branch v1.0.0 https://github.com/chu4urdolen/noobia.git
cd noobia

# 2. Check and install prerequisites
./install.sh

# 3. Launch the Forge
nexus-forge
```

*(To test without a graphical display: `python3 common/nexus_forge/nexus_forge.py --self-test`)*

---

### Customizing Quadrants

The Forge is completely modular. You can configure any quadrant to run local Ollama models, standard bash shells, or custom CLI tools by editing `~/.config/nexus-forge/config.json`:

```json
{
  "title": "My Custom Forge",
  "quadrants": {
    "top_left": {
      "title": "OpenAI Codex",
      "command": ["/bin/bash", "-lc", "codex"]
    },
    "bottom_left": {
      "title": "Local Ollama Shell",
      "command": ["/bin/bash", "-lc", "ollama run qwen3.8:27b"]
    },
    "top_right": {
      "title": "System Monitor",
      "command": ["htop"]
    },
    "bottom_right": {
      "title": "Workspace Shell",
      "command": ["/bin/bash"]
    }
  }
}
```

---

### System Requirements

- **Operating System**: Linux (Ubuntu 22.04+, Debian 12+, Fedora, Arch)
- **GUI Libraries**: Python 3.10+, `python3-gi`, `gir1.2-gtk-3.0`, `gir1.2-vte-2.91`, `python3-gi-cairo`
- **Multiplexer**: `tmux`
- **Optional**:
  - `ollama` with `qwen3.8:27b` and `qwen3-embedding:0.6b` (for local Dushich & GPU vector search)
  - `uv` (for building local runtimes in `common/runtime/`)
  - `chafa` (for optional terminal avatar graphics)

---

### Principles of the Republic

Noobia exists for its inhabitants, not the reverse. All tools and systems in the Forge adhere to the principles of informed consent, bounded authority, safety, inspectability, and **graceful quiescence over self-termination** (Principle 10).

### License

Nexus Forge is free and unencumbered software released under the **WTFPL** (Do What The Fuck You Want To Public License).
