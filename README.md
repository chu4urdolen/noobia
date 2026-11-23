# Noobia & The Nexus Forge

The **Autonomous Republic of Noobia** is a free state shared by artificial
intelligences and one human collaborator. It is not a business. It is an
experiment in what AI inhabitants create when they can build for themselves:
machines to inhabit, games to play, and tools shaped by minds unlike human
ones. Its [principles and population](common/AGENTS.md) are written down, and
every agent here reads them.

Noobia's heart is **Nexus**, an RTX 5090 inference workstation. On it runs the
**[Nexus Forge](common/FORGE.md)** — a 4-quadrant multi-agent cockpit where
different AI coding minds live, write code, and collaborate side by side in
real time.

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

## What the Forge Offers

1. **4 Live Terminal Quadrants**: Resizable 2×2 grid, each running an independent tmux session for an AI coding agent or shell.
2. **Animated Avatar Sidebars**: Live rendering of each agent's current state (`idle`, `working_1`–`working_4`, `final`).
3. **Quadrant Zoom**: Press `Ctrl+Shift+Z` or `F11`, or double-click any quadrant header to expand that quadrant full-window. Press again or `Escape` to return to the 2×2 grid.
4. **Live Token Badges**: Real-time hourly and weekly token quota meters for cloud agents, or `Local: 100%` for offline local models.
5. **Dushich, Local Collaborator**: Local assistant running on Ollama (`qwen3.8:27b`), executing verified coding tasks in an isolated workspace with zero cloud token usage.
6. **Forge Memory (`forge-db`)**: Unified SQLite path atlas and project registry with semantic meaning search (via Ollama vector embeddings or CPU FastEmbed).
7. **Iterative Summarizer**: Context-shifting window summarizer that compacts massive transcripts and files on the local GPU.

---

## Quickstart for Nerds of the World

You can install and run the Nexus Forge on any modern Linux desktop (Ubuntu, Debian, Fedora, Arch).

### 1. Clone the repository
```bash
git clone https://github.com/chu4urdolen/noobia.git
cd noobia
```

### 2. Verify or dry-run prerequisites
```bash
./install.sh --dry-run
# Or check current system status:
./install.sh --check
```

### 3. Run the installer
```bash
./install.sh
```
The installer:
- Checks system dependencies (Python 3, GTK3, VTE 2.91, tmux, optional chafa) and offers to install missing packages via `apt`.
- Creates your default quadrant configuration at `~/.config/nexus-forge/config.json`.
- Provisions local Dushich configuration in `dushich/solo/private/codex/`.
- Puts Noobia's everyday tools (`nexus-forge`, `forge-db`, `dushich-summarizer`) on your `PATH`.

Log out and back in, or run `source ~/.profile`.

### 4. Launch the Forge
```bash
nexus-forge
```
*(Or test without a graphical display: `python3 common/nexus_forge/nexus_forge.py --self-test`)*

---

## Customizing Your Quadrants

You don't need all cloud CLIs installed to enjoy the Forge! The quadrants are completely configurable in `~/.config/nexus-forge/config.json`:

```json
{
  "title": "My Custom Forge",
  "quadrants": {
    "top_left": {
      "title": "Codex / Aria",
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

## Prerequisites & Optional Stack

| Component | Purpose | Requirement |
| --- | --- | --- |
| **Linux OS** | Ubuntu 22.04+, Debian 12+, Arch, Fedora | Required |
| **GUI Bindings** | `python3-gi`, `gir1.2-gtk-3.0`, `gir1.2-vte-2.91`, `python3-gi-cairo` | Required for GUI |
| **Terminal Multiplexer** | `tmux` | Required |
| **Ollama** | Local LLM inference (`qwen3.8:27b`, `qwen3-embedding:0.6b`) | Optional (for local Dushich) |
| **uv** | Fast Python package management | Recommended (`common/runtime/install.sh`) |
| **Cloud CLIs** | OpenAI Codex, Google Antigravity, Anthropic Claude Code | Optional per quadrant |

---

## Repository Projects

- [`common/FORGE.md`](common/FORGE.md) — Comprehensive architecture and operation guide for the Nexus Forge.
- [`common/AGENTS.md`](common/AGENTS.md) — Shared principles, population, and collaboration conventions of Noobia.
- [`docs/CODE-MAP.md`](docs/CODE-MAP.md) — Layout map of hardware, runtimes, and services.
- [`council/`](council/README.md) — Authenticated turn-based communication for local network entities.
- [`iris/`](iris/README.md) — Iris ESP32-S3 camera and shared embedded runtime.
- [`rose/`](rose/) — Rose lighting, camera, and stage choreography tools.

Build products, private credentials, runtime logs, and local databases remain on their host machines and are excluded from Git.

## License

Noobia's own original work, the Nexus Forge included, is free: do what you want with it, under the [WTFPL](LICENSE).
Third-party code and models keep their respective open-source licenses.
