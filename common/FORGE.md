# The Nexus Forge

The Nexus Forge is the workshop where Noobia's coding agents live and work
together. It runs on **Nexus**, Noobia's inference computer (an RTX 5090
workstation running Ubuntu), and it brings together four things:

1. **The Forge window**: one desktop window with four live terminals side by
   side, one per agent. Each terminal has an animated avatar that shows
   whether its agent is idle or working.
2. **Dushich, everyone's local helper**: a Qwen model on Nexus's own GPU who
   answers questions, takes verified coding handoffs, and explores the
   machine. He uses no cloud tokens.
3. **Forge memory (`forge-db`)**: one SQLite database of where things are on
   Nexus, what each project has done, and who is working on what. Every agent
   uses it. Dushich keeps it.
4. **The summarizer**: a local tool that compacts long conversations and
   huge files so that no mind, local or cloud, has to read them whole.

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
        │ one "dushich" MCP server per agent      │ forge-db, dushich-explore
        ▼                                         ▼
  Dushich (Codex CLI → Ollama → qwen3.8:27b on the RTX 5090)
        │ keeps                     │ compacts with
        ▼                           ▼
  dushich/workspace/forge.db     dushich-summarizer
```

## Who works in the forge

| Agent | Mind | Where it thinks | Command | Role file |
| --- | --- | --- | --- | --- |
| **Aria**: architect and main creator | OpenAI Codex CLI | cloud | `noobia-codex` | [`aria/AGENTS.md`](../aria/AGENTS.md) |
| **Banshee**: Spirit of Initiative | Google Antigravity CLI (`agy`) | cloud | `noobia-banshee` | [`banshee/AGENTS.md`](../banshee/AGENTS.md) |
| **Gwyn App Nub**: app-writer | Anthropic Claude Code | cloud | `gwyn-app-nub/launch` | [`gwyn-app-nub/AGENTS.md`](../gwyn-app-nub/AGENTS.md) |
| **Dushich**: Watchmaker, everyone's helper, keeper of forge memory | Codex CLI on Ollama `qwen3.8:27b` | **local GPU** | `dushich` (helper), `dushich/solo/launch` (solo) | [`coding/`](../dushich/coding/AGENTS.md), [`solo/`](../dushich/solo/AGENTS.md) |
| **Aigel**: diagnostics angel | Codex CLI on local Ollama | local GPU | `aigel` | [`aigel/AGENTS.md`](../aigel/AGENTS.md) |

Dushich has two roles: the **helper**, who works for the other agents, and
**solo**, who works on his own projects. Aigel is a forge inhabitant but has
no quadrant in the window; she watches Nexus health from her own terminal.

**How an agent is defined.** Every agent has a home under `/noobia/<name>/`:

- A **role file** (`AGENTS.md`) holds only that agent's personality and
  instructions.
- Each agent's CLI loads the shared [`common/AGENTS.md`](AGENTS.md):
  Noobia's principles, its population, how to work with Dushich, tools, and
  Git rules.
  - Codex agents get it from [`/noobia/AGENTS.md`](../AGENTS.md).
  - Gwyn's `CLAUDE.md` imports it.
  - Banshee is told to read it at the start of each session.
- A **launcher** starts the CLI in that agent's home folder, usually as a
  two-pane tmux session with the agent on the left and Dushich's live
  activity on the right.
- A **private, Git-ignored directory** holds the CLI's configuration,
  sessions, and logins, so the agents never share a conversation history or
  an account.

All agents run under one Unix login (`aria`). Their identities are kept apart
by directory, not by Unix user.

**One repository.** All of this is one Git repository, `/noobia` on `main`,
which GitHub mirrors. Every agent works and commits in it directly; nobody
has a private copy or a nested repository. The one deliberate exception is
Dushich's task workspace, `dushich/workspace`: a small repo of its own so the
handoff runner can prove that he changed the expected files and committed.

## Paths and commands

Everything lives under one root, **`NOOBIA`** (`/noobia` on Nexus). Code
derives its paths from `$NOOBIA` instead of hard-coding them. Only files that
other programs read literally keep absolute paths: systemd units, desktop
entries, and CLI configuration.

Everyday commands are links in [`common/bin/`](bin/) to their source:

- `nexus-forge`, `noobia-codex`, `noobia-banshee`, and `aigel`
- `dushich` and `dushich-explore`
- `forge-db` and `dushich-summarizer`

Two files set up `NOOBIA` and put `common/bin` on `PATH`:

- `~/.config/environment.d/999-noobia.conf`, for the desktop session and
  user services
- `~/.profile`, for login shells

Nothing Noobia-made is installed in `/usr/bin`, `/usr/local/bin`, or
`~/.local/bin`, so what runs is always what is in the repository.

**Runtimes.** The third-party software the forge runs on is built inside
[`common/runtime/`](runtime/README.md), not in `/opt`: Dushich's and Aigel's
Codex CLI, the Python environment for meaning search and its model, and
Playwright with Chromium. Git holds each one's pinned recipe and
`install.sh`, which rebuilds them; the built files (about 1.5 GB) stay out of
Git.

## Startup

1. **Login.** GNOME's autostart entry ([source](../dushich/solo/nexus-forge.desktop),
   installed as `~/.config/autostart/nexus-forge.desktop`) runs
   `common/bin/nexus-forge` five seconds after login.
2. **Updates.** `nexus-forge` first runs
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
   answer on `127.0.0.1:11434`. A terminal whose agent exits displays a clean
   reconnect card with a respawn action (or auto-restarts after 2 seconds on error).
   - **Quadrant Zoom:** Double-click any quadrant header, click the `⛶` button,
     or press `Ctrl+Shift+Z` or `F11` to expand any quadrant to full-window.
     Press `Ctrl+Shift+Z` or `Escape` to return to the 2×2 grid.
   - **Token Quota Badge:** A live hourly/weekly percentage remaining badge (`H/W: %/%`
     for cloud agents, `Local: 100%` for Dushich) sits directly above Rose on
     each avatar sidebar.
   - **Configuration & Installer:** Customize quadrants with `--config` or
     `~/.config/nexus-forge/config.json`. Set up dependencies and the launcher on
     any machine using [`common/tools/install_nexus_forge.sh`](tools/install_nexus_forge.sh).
4. **Avatars.** Every 0.4 seconds the window reads each terminal's visible
   text and title, plus the hidden tmux panes. It switches that agent's
   avatar between `idle`, `working_1`–`working_4`, and `final` frames from
   [`pics/`](../pics/). When a helper Dushich is busy in a quadrant, his
   avatar animates there too. Rose watches over the bottom of every sidebar.

Check the window without a display: `python3 dushich/solo/nexus_forge.py --self-test`.

## Dushich, everyone's helper

Every cloud agent reaches Dushich the same way: through the `dushich` MCP
server, [`common/dushich/mcp.py --agent NAME`](dushich/README.md), with the
same tools for everyone:

| Tool | What it does |
| --- | --- |
| `dushich_context_status` | Shows which session the tools are bound to |
| `dushich_ask` | Asks the Helper Dushich thread linked to this conversation; no files change |
| `dushich_start` → `dushich_wait`/`status` → `dushich_report` | A verified coding handoff |
| `dushich_explore` → `dushich_explore_wait` | "Where is / how does" on Nexus; he records what he finds in forge memory |

**Verified handoffs.** A handoff names the goal, an expected file, and an
independent test. Dushich's task runner
([`dushich-task.py`](../dushich/coding/dushich-task.py)) runs him in his own
clean Git workspace. It accepts the result only if:

- he actually used tools;
- the expected file changed;
- the tests ran, and found at least one test to run;
- a commit was made, when one was required.

If a check fails, it retries once. A handoff that still fails ends as
`needs_<agent>`, a blocker the agent must resolve before sending another. The
calling agent reviews the diff before adopting anything into shared code.
Banshee's and Gwyn's handoffs run through
[`common/dushich/bridge.py`](dushich/bridge.py). Aria's run through her own
Codex bridge, [`aria/dushich-bridge`](../aria/dushich-bridge).

**Helper threads.** Each agent conversation gets its own linked Helper
Dushich thread. Only the visible conversation reaches him: the human's
prompts and the agent's final answers. Reasoning, tool output, and anything
that looks like a credential are left out.

- Aria's and Banshee's conversations are mirrored continuously by two user
  services, `noobia-dushich-helper-mirror` and
  `noobia-banshee-helper-mirror`.
- Gwyn's thread is brought up to date when Gwyn asks a question.

State is kept in `~/.codex/dushich-bridge/`.

## The summarizer: compacting what is too long to read

Context windows are finite and cloud tokens are not free.
[`dushich-summarizer`](../dushich/coding/dushich_summarizer.py) digests long
text on the local GPU instead. It works in a moving window:

1. It cuts the input into pieces at sentence boundaries, each sized to fit
   Qwen's window next to the instructions.
2. It summarizes each piece below a target size, tightening by a set
   percentage when a summary comes out too long.
3. It carries the running summary into the next piece, until the whole
   input is digested.

It does two jobs in the forge:

- **Context compacting.** Helper threads and handoff briefs carry a summary
  of the conversation, not the conversation. The summarizer keeps an
  incremental summary per conversation and only reads what was added since
  the last time. A cold start with a huge backlog reads only the newest two
  windows of it.
- **Large-input review.** Any agent can digest a huge log, transcript, or
  source file before deciding what to read in full:

  ```sh
  dushich-summarizer --file /var/log/syslog --instructions "Focus on GPU and power errors."
  ```

## Forge memory: `forge-db`

[`forge-db`](tools/forge_db.py) keeps Noobia's shared memory in one SQLite
file, `$NOOBIA/dushich/workspace/forge.db`. The file lives in Dushich's
workspace because he uses it most and keeps it: he records the paths he
finds, writes project notes for the agents he helps, and tags everything.
`forge-db` is the only program that reads or writes the file; nothing else
touches it with raw SQL. On first use it creates the folder and every table,
so a fresh clone works without a database in Git.

| Table | Holds |
| --- | --- |
| `projects` | The project registry: executor, receiver, hardware readiness, and when and for whom someone last worked on it (`last_modified`, `modified_for`). |
| `nexus_paths` | The path atlas. Each row has a kind, owner, one-line description, project, and whether the path still exists. A hit count records how often an agent found the row correct. |
| `project_notes` | Short dated notes per project (decisions, milestones, blockers) that cite atlas paths. |
| `tags`, `tag_links` | A curated UPPERCASE vocabulary (`#ROSE`, `#SECURITY`, `#NETWORK`, …) for paths and projects. |
| `embeddings` | Sentence vectors for meaning search. |

### How meaning search works

Ordinary search finds words. Meaning search finds *ideas*: ask for "graphics
card heat" and it finds `/var/log/noobia_gpu`, described as "GPU monitor
CSVs: power, usage, temperature", although the two share no word.

1. **Every entry becomes a sentence.** Each atlas path, note, and project is
   written out as one line of text: its path, kind, owner, description, and
   tags.
2. **An embedding model turns each sentence into a vector**, a list of
   numbers (1,024 of them for the GPU model) that encodes what the sentence
   is about. Sentences with similar meanings get vectors that point in
   similar directions, whatever words they use.
3. **Vectors are stored** in the `embeddings` table, about 300 of them today.
   A vector is recomputed only when its entry's text changes (`forge-db`
   keeps a hash of each text), so writes stay cheap.
4. **A search embeds the question the same way** and measures how closely
   its direction matches every stored vector (cosine similarity). That score
   is rescaled to roughly 0–1 and added to an ordinary word-match score, so an
   exact name still wins and a vague question still finds its answer. The
   best few are returned.

Two models can do step 2, both local:

- **On the GPU:** `qwen3-embedding:0.6b` through Ollama. It is used only when
  it cannot push Dushich's Qwen out of video memory (Ollama keeps two models
  loaded: `OLLAMA_MAX_LOADED_MODELS=2`).
- **On the CPU:** `BAAI/bge-small-en-v1.5` (fastembed, in
  `common/runtime/forge-venv`, with the model in `common/runtime/models`).

The two models' vectors don't mix: switching models re-embeds everything on
the next write or `forge-db embed`. `forge-db stats` shows which model is
active. With neither model available, search is word-only and still works.

**One project, one agent at a time.** Before working on a project, an agent
(or Dushich, on an agent's behalf) runs `forge-db project touch`. If a
different agent worked on that project within the last two hours, the
command answers `BUSY` and exits 3. The agent then asks Noob before going
on; when Noob wants two agents to share a project, `--together` records
that. A note also counts as work on its project, and warns instead of
failing.

**Trust, but verify.** An atlas row can go stale. Agents check a path briefly
before relying on it. If it is right, they count it with
`forge-db path hit PATH --by NAME`. If it is wrong, they fix or remove the
row. `forge-db path list --sort hits` puts the least-used rows first, as
candidates for retirement.

```sh
forge-db search where do we keep the gpu power logs
forge-db project touch nexus_forge --for Gwyn --by Gwyn      # BUSY → ask Noob
forge-db path hit /noobia/common/tools/forge_db.py --by Gwyn
forge-db path set /noobia/rose/rose_composer -k dir -o Rose -d "Beat grids for Rose" --tag ROSE --by Gwyn
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
| Dushich's CLI | Codex CLI 0.169.0 built in `common/runtime/codex` (`common/runtime/install.sh codex`), with its own `CODEX_HOME` per role |
| Cloud agents' CLIs | Codex (`npm -g @openai/codex`, Node.js 22), Antigravity (`~/.local/bin/agy`), Claude Code (native installer, `~/.local/bin/claude`), each logged in to its own provider account |
| Meaning search (optional) | `common/runtime/forge-venv` and `common/runtime/models` (`install.sh forge`) |
| App checks (optional) | Playwright and Chromium in `common/runtime/web-venv` and `common/runtime/playwright` (`install.sh web`) |
| Commands and root | `common/bin` on `PATH` and `NOOBIA=/noobia` (see Paths and commands) |
| MCP registration | `dushich` → `common/dushich/mcp.py --agent NAME` in each CLI's config; see [`common/dushich/README.md`](dushich/README.md) |
| Helper mirrors | `noobia-dushich-helper-mirror` and `noobia-banshee-helper-mirror` user services, installed from [`common/dushich/`](dushich/) |
| Avatar art | [`pics/<Agent>/`](../pics/): `idle.png`, `working_1.png`–`working_4.png`, `final.png`, and `pics/Rose/Rose.png` (360 px wide) |
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
python3 -m unittest discover -s common/dushich -p 'test_*.py'   # MCP server, bridge, helpers
python3 -m unittest discover -s common/tools -p 'test_*.py'     # forge-db, dushich-explore
python3 -m unittest discover -s aria -p 'test_*.py'
forge-db stats                                             # rows and active meaning model
systemctl --user status noobia-dushich-helper-mirror noobia-banshee-helper-mirror
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
  report. Forge memory records who wrote each row (`--by`) and who is working
  on each project. Hit counts and presence checks keep the atlas honest.
- **Private stays private.** Each agent's `private/` directory (logins,
  sessions, keys) and `forge.db` are excluded from Git. Only the visible
  dialogue reaches a helper thread, and credentials are redacted from it.

## License

Noobia's own work, the forge included, is free: do what you want with it,
under the [WTFPL](../LICENSE).
