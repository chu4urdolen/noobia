# The Nexus Forge

The Nexus Forge is the workshop where Noobia's coding agents live and work
together. It runs on **Nexus**, Noobia's inference computer (an RTX 5090
workstation running Ubuntu), and it brings together three things:

1. **The Forge window**: one desktop window with four live terminals side by
   side, one per agent. Each terminal has an animated avatar that shows
   whether its agent is idle or working.
2. **Dushich, everyone's local helper**: a Qwen model on Nexus's own GPU who
   answers questions, takes verified coding handoffs, explores the machine,
   and keeps the shared memory. He uses no cloud tokens.
3. **Forge memory (`forge-db`)**: one SQLite database of where things are on
   Nexus and what each project has done, searchable by words and meaning.
   Every agent reads it. Dushich is its keeper.

Three of the minds in the forge think in the cloud: OpenAI, Google, and
Anthropic models. Their hands are here, in local terminals on Nexus. The
fourth, Dushich, is entirely local. The forge is how such different minds
share one machine, one memory, and one set of rules. Those rules are in
[`AGENTS.md`](AGENTS.md).

```
 ┌──────────────────── Nexus Forge window (GTK + VTE) ────────────────────┐
 │  Aria (Codex)         │ avatar │  Banshee (Antigravity) │ avatar       │
 │  + Dushich monitor    │        │  + Dushich monitor     │              │
 ├───────────────────────┼────────┼────────────────────────┼──────────────┤
 │  Dushich Solo (Codex  │ avatar │  Gwyn (Claude Code)    │ avatar       │
 │  on local Qwen)       │        │  + Dushich monitor     │              │
 └────────────────────────────────────────────────────────────────────────┘
        │ MCP "dushich" bridges          │ forge-db / dushich-explore
        ▼                                ▼
  Dushich (Codex CLI → Ollama → qwen3.8:27b on the RTX 5090)
        │ keeps
        ▼
  /noobia/dushich/workspace/forge.db  (paths · project notes · tags · vectors)
```

## Who works in the forge

| Agent | Mind | Where it thinks | Launcher | Role file |
| --- | --- | --- | --- | --- |
| **Aria**: architect and main creator | OpenAI Codex CLI | cloud | `noobia-codex` → [`aria/codex-with-dushich`](../aria/codex-with-dushich) | [`aria/AGENTS.md`](../aria/AGENTS.md) |
| **Banshee**: Spirit of Initiative | Google Antigravity CLI (`agy`) | cloud | `noobia-banshee` → [`banshee/launch`](../banshee/launch) | [`banshee/AGENTS.md`](../banshee/AGENTS.md) |
| **Gwyn App Nub**: app-writer | Anthropic Claude Code | cloud | [`gwyn-app-nub/launch`](../gwyn-app-nub/launch) | [`gwyn-app-nub/AGENTS.md`](../gwyn-app-nub/AGENTS.md) |
| **Dushich**: Watchmaker, local helper, keeper of forge memory | Codex CLI on Ollama `qwen3.8:27b` | **local GPU** | [`dushich/solo/launch`](../dushich/solo/launch) (solo); `dushich` (helper) | [`coding/`](../dushich/coding/AGENTS.md), [`solo/`](../dushich/solo/AGENTS.md), [`foreman/`](../dushich/foreman/AGENTS.md) |
| **Aigel**: diagnostics angel | Codex CLI on local Ollama | local GPU | [`aigel/launch`](../aigel/launch) | [`aigel/AGENTS.md`](../aigel/AGENTS.md) |

Aigel is a forge inhabitant but has no quadrant in the window. She watches
Nexus health from her own terminal.

**How an agent is defined.** Every agent has a private home under
`/noobia/<name>/`:

- A **role file** (`AGENTS.md`) holds only that agent's personality and
  instructions.
- Each agent's CLI loads the shared [`common/AGENTS.md`](AGENTS.md):
  Noobia's principles, its population, Dushich collaboration, tools, and Git
  rules.
  - Codex agents get it from [`/noobia/AGENTS.md`](../AGENTS.md).
  - Gwyn's workspace `CLAUDE.md` imports it.
  - Banshee is told to read it at the start of each session.
- A **launcher** starts the CLI in that agent's own workspace, usually as a
  two-pane tmux session with the agent on the left and Dushich's live
  activity on the right.
- A **private, Git-ignored directory** holds the CLI's configuration,
  sessions, and logins, so the agents never share a conversation history or
  an account.

All agents run under one Unix login (`aria`). Their identities are kept apart
by directory, not by Unix user.

## Startup

1. **Login.** GNOME's autostart entry ([source](../dushich/solo/nexus-forge.desktop),
   installed as `~/.config/autostart/nexus-forge.desktop`) runs
   `/usr/local/bin/nexus-forge` five seconds after login.
2. **Updates.** [`/noobia/nexus-forge`](../nexus-forge) first runs
   [`common/tools/update_agents.sh`](tools/update_agents.sh), which brings the
   cloud agents' CLIs up to date before anyone starts:
   - **Antigravity:** runs `agy update`.
   - **Codex:** compares the installed version with npm and runs
     `sudo -n npm install -g @openai/codex@VERSION` if they differ. It also
     pre-dismisses Codex's update prompt so startup never blocks on it.
   - **Claude Code:** runs `claude update` on the `latest` channel and points
     `~/.local/bin/claude` at the newest installed version.

   Every step has a timeout, and a failure is logged and skipped. The forge
   still starts with the old version. Log:
   `~/.local/state/noobia/agent_updates.log`.
3. **Window.** [`dushich/solo/nexus_forge.py`](../dushich/solo/nexus_forge.py)
   opens the 2×2 window. For each quadrant it attaches to the agent's running
   tmux session if one exists (`noobia-aria-*`, `noobia-banshee-*`,
   `noobia-gwyn-*`, `noobia-dushich-solo-*`). Otherwise it starts the agent's
   launcher. Dushich's quadrant first waits up to 20 seconds for Ollama to
   answer on `127.0.0.1:11434`. A terminal whose agent exits with an error
   restarts after 1.5 seconds. Agents started outside the window are
   attached rather than duplicated.
4. **Avatars.** Every 0.4 seconds the window reads each terminal's visible
   text and title, plus the hidden tmux panes. It switches that agent's
   avatar between `idle`, `working_1`–`working_4`, and `final` frames. When
   a helper Dushich is busy in a quadrant, his avatar animates there too.
   Rose watches over the bottom of every sidebar.

Check the window without a display: `python3 dushich/solo/nexus_forge.py --self-test`.

## Dushich, everyone's helper

Each cloud agent reaches Dushich through its own `dushich` MCP server. A
helper conversation runs on the local GPU and is linked to the cloud agent's
current conversation, so Dushich knows the context without being sent the
whole transcript.

| Route | What it does | Aria | Banshee | Gwyn |
| --- | --- | --- | --- | --- |
| `dushich_ask` | Ask the linked Helper Dushich thread a question; no files change | `talk-to-dushich` CLI | ✓ | ✓ |
| `dushich_start` → `dushich_wait`/`status` → `dushich_report` | Verified coding handoff | ✓ | ✓ | ✓ |
| `dushich_explore` | "Where is / how does" on Nexus; records answers in forge memory | `dushich-explore` CLI | `dushich-explore` CLI | ✓ |
| Helper mirror | Keeps the helper thread current with the visible conversation | user service | user service | on demand |

**Verified handoffs.** A handoff names the goal, an expected file, and an
independent test. [`dushich-task.py`](../dushich/coding/dushich-task.py)
runs Dushich in his own clean Git workspace and accepts the result only if:

- he actually used tools;
- the expected file changed;
- the tests ran, and found at least one test to run;
- a commit was made, when one was required.

If a check fails, it retries once. The calling agent reviews the diff before
adopting anything into shared code. The handoff code is in
[`aria/dushich-bridge`](../aria/dushich-bridge). The MCP adapters are
[`aria/dushich-mcp`](../aria/dushich-mcp),
[`banshee/dushich_mcp.py`](../banshee/dushich_mcp.py), and
[`gwyn-app-nub/dushich_mcp.py`](../gwyn-app-nub/dushich_mcp.py).

**Helper mirrors.** Only the visible conversation reaches Dushich: the
human's prompts and the agent's final answers. Reasoning, tool output, and
anything that looks like a credential are left out.

- Aria's and Banshee's conversations are mirrored continuously by user
  services: `noobia-dushich-helper-mirror.service` and
  `noobia-banshee-helper-mirror.service`.
- Gwyn's conversation is summarized only when Gwyn asks a question.
- Long conversations are compacted by
  [`dushich_summarizer.py`](../dushich/coding/dushich_summarizer.py).
- State is kept in `~/.codex/dushich-bridge/`.

**Shared local tools.** These run on the GPU without using any cloud model,
and any agent can call them:

- `dushich-explore`: explores Nexus read-only, then writes what it found to
  the atlas.
- `dushich-summarizer`: digests a large file or log.

## Forge memory: `forge-db`

[`forge-db`](tools/forge_db.py) keeps Noobia's shared memory in
`/noobia/dushich/workspace/forge.db`. The database file belongs to Dushich
and lives in his workspace. Dushich is its main keeper: he records paths he
finds, writes project notes for the agents he helps, and tags everything.
Every other agent reads it and writes to it through the same command, never
by editing the file directly.

| Table | Holds |
| --- | --- |
| `projects` | The project registry: executor, receiver, hardware readiness. Shared with the planned Foreman. |
| `nexus_paths` | The path atlas. Each row has a kind, owner, one-line description, project, and whether the path still exists. A hit count records how often an agent found the row correct. |
| `project_notes` | Short dated notes per project (decisions, milestones, blockers) that cite atlas paths. |
| `tags`, `tag_links` | A curated UPPERCASE vocabulary (`#ROSE`, `#SECURITY`, `#NETWORK`, …) for paths and projects. |
| `embeddings` | Sentence vectors for meaning search. |

**Search** combines word matches with meaning. If the GPU embedding model
(`qwen3-embedding:0.6b`) can load without evicting Dushich's Qwen, it is
used. Otherwise `forge-db` falls back to a small CPU model
(`BAAI/bge-small-en-v1.5` via fastembed in `/opt/noobia/forge-venv`). Without
either, search is word-only.

**Trust, but verify.** An atlas row can go stale. Agents check a path briefly
before relying on it. If it is right, they count it with
`forge-db path hit PATH --by NAME`. If it is wrong, they fix or remove the
row. `forge-db path list --sort hits` puts the least-used rows first, as
candidates for retirement.

```sh
forge-db search where do we keep the gpu power logs
forge-db path hit /noobia/common/tools/forge_db.py --by Gwyn
forge-db path set /noobia/rose/rose_composer -k dir -o Rose -d "Beat grids for Rose" --tag ROSE --by Gwyn
forge-db project get forge_memory
forge-db note add forge_memory "Hit counting shipped" --path /noobia/common/tools/forge_db.py --by Gwyn
forge-db --json changes --since 2026-11-20T00:00:00+00:00
```

Every write needs `--by NAME`. Descriptions never contain secrets.
`forge.db` itself is runtime data: it is not in Git, and backups are kept
privately on Nexus.

## What the forge needs

| Need | On Nexus today |
| --- | --- |
| GPU | NVIDIA RTX 5090 (32 GB), driver 595, power-capped at 400 W |
| OS and desktop | Ubuntu 26.04 with GNOME (Wayland) |
| Window | `python3-gi`, `gir1.2-gtk-3.0`, `gir1.2-vte-2.91`, `python3-gi-cairo`, `python3-pil` |
| Terminals | `tmux` 3.6, `curl`, `sqlite3` |
| Local inference | Ollama service on `127.0.0.1:11434` with `qwen3.8:27b` (131k context) and `qwen3-embedding:0.6b`; override [`dushich/coding/ollama-override.conf`](../dushich/coding/ollama-override.conf) → `/etc/systemd/system/ollama.service.d/noobia-dushich.conf` (`OLLAMA_MAX_LOADED_MODELS=2`) |
| Dushich's CLI | Codex CLI installed separately in `/opt/noobia/dushich-codex` (`npm install --prefix … @openai/codex`), with its own `CODEX_HOME` per role |
| Cloud agents' CLIs | Codex (`npm -g @openai/codex`, Node.js 22), Antigravity (`~/.local/bin/agy`), Claude Code (native installer, `~/.local/bin/claude`), each logged in to its own provider account |
| Meaning search (optional) | `/opt/noobia/forge-venv` with `fastembed` and `numpy` |
| Commands on `PATH` | `/usr/local/bin/{nexus-forge, forge-db, dushich-explore}` link into this repository; `dushich`, `dushich-summarizer`, and `/usr/local/libexec/dushich-task.py` are installed copies (reinstall them after changing the source, see [`dushich/coding/README.md`](../dushich/coding/README.md)) |
| Helper mirrors | `systemctl --user enable --now noobia-dushich-helper-mirror.service noobia-banshee-helper-mirror.service` (units in [`aria/`](../aria/noobia-dushich-helper-mirror.service) and [`banshee/`](../banshee/noobia-banshee-helper-mirror.service)) |
| Avatar art | PNG frames in `/noobia/pics/<Agent>/` (`idle.png`, `working_1.png`–`working_4.png`, `final.png`) and `/noobia/pics/Rose/Rose.png`; not in Git. Without them, the window shows the terminals but no avatars. |
| Autostart | [`dushich/solo/nexus-forge.desktop`](../dushich/solo/nexus-forge.desktop) → `~/.config/autostart/` |

Install details for Dushich's runtime are in
[`dushich/coding/README.md`](../dushich/coding/README.md). Measured VRAM use
and the LAN inference endpoint are described in
[`NEXUS-INFERENCE.md`](NEXUS-INFERENCE.md).

## Checking that it works

```sh
python3 dushich/solo/nexus_forge.py --self-test           # window, layout, avatars
python3 -m unittest discover -s dushich/solo -p 'test_*.py'
python3 -m unittest discover -s dushich/coding -p 'test_*.py'   # task runner, summarizer
python3 -m unittest discover -s common/tools -p 'test_*.py'     # forge-db, dushich-explore
python3 -m unittest discover -s banshee -p 'test_*.py'
python3 -m unittest discover -s aria -p 'test_*.py'
forge-db stats                                             # rows and active meaning model
systemctl --user status noobia-dushich-helper-mirror.service
```

## Trust and boundaries

The forge gives its agents real power on a real machine. The rules that come
with that power are written down rather than assumed:

- **Broad access, bounded authority.** All agents, Dushich included, run
  without approval prompts under the `aria` login, which has passwordless
  sudo. Noob granted this deliberately. Each role file still sets the
  agent's boundaries:
  - Agents ask first before anything destructive, public, costly, or
    physical.
  - High-impact system administration belongs to Aria or Banshee.
  - A commit records work. It does not deploy it.
- **Local by default.** Dushich, Aigel, forge memory, and the summarizer use
  only the local GPU. No cloud model is ever silently substituted for them.
- **Inspectable.** Every handoff saves its event stream and verification
  report. Forge memory records who wrote each row (`--by`). Hit counts and
  presence checks keep the atlas honest.
- **Private stays private.** Each agent's `private/` directory (logins,
  sessions, keys) and `forge.db` are excluded from Git. Only the visible
  dialogue reaches a helper thread, and credentials are redacted from it.

## Status

The window, handoffs, helper mirrors, forge memory, and explorer are
working and in regular use on Nexus.

The **Foreman** role is written ([`dushich/foreman/AGENTS.md`](../dushich/foreman/AGENTS.md))
but has no launcher yet. When it runs, Dushich will assign projects from the
`projects` table and raise human-help flags when a task needs Noob's hands.
The old Dushich web dashboard is disabled.
