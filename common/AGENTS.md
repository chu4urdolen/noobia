# Shared instructions for Noobia coding agents

Read this file alongside your own role instructions. It is the one source for
Noobia's workspace, Git, agent tool, and Linux service conventions. A role file
may add responsibilities or a narrower boundary; a direct instruction from
Noob for the current task takes precedence.

## Where work belongs

Start with [the code map](/noobia/docs/CODE-MAP.md) and the relevant inhabitant
page before changing a device or live service. Work under `/noobia/`. Put each
inhabitant's source, instructions, tests, documents, task worktrees, and local
artifacts in `/noobia/<Noob>/`. Put material genuinely shared by multiple
inhabitants in `/noobia/common/`. The readable
[contact book](/noobia/common/CONTACT-BOOK.md) records names and contact routes;
the Council authentication file is not a roster and must not enter prompts.

Keep scratch files under the owning inhabitant. Preserve established live paths
with compatibility links until their services and devices have been migrated
and verified. Do not create another top-level home for new work. Protect
unrelated changes and private data.

At the end of each task, remove temporary files and generated output you
created once they are no longer needed. Keep any artifact that must persist in
the owning inhabitant's ignored private area, with a clear purpose. Check Git
status for leftover task files before committing and before handing off; do
not sweep away another agent's active work.

## Agent-facing tools

Put an inhabitant's agent tools in `/noobia/<Noob>/tools/`. Each command must
finish without waiting for interactive input. Bound network, device, and
subprocess waits with timeouts. Every invocation must return a concise UTF-8
string on standard output that an AI can understand: plain text for simple
results or JSON for structured results. On failure, return a useful error
string and exit nonzero; standard error may carry diagnostics. Do not print
credentials or hidden private data. Use `sudo -n` when authorized root access
is needed, so a password prompt cannot block the caller. For long
work, return a job ID promptly and provide separate status and result commands;
never leave the calling terminal blocked indefinitely.

### Local Dushich Summarizer

**Use this tool for yourself** whenever you only need an overview, digest, or
focused summary of a large file, log, or transcript instead of reading the full
file into your own context window. Any Noobia agent can call
`/noobia/dushich/tools/dushich_summarizer.py` (also installed at
`/usr/local/bin/dushich-summarizer` and importable from
`/noobia/dushich/coding/dushich_summarizer.py`) to compact a large string,
file, or transcript on the local Nexus GPU without consuming cloud tokens. It
uses an iterative context-shifting window: it cuts each piece at a sentence
boundary up to `context_size - desired_size - instruction_size`, summarizes it
below `desired_size` (refining by an explicit `%` reduction if needed), and
concatenates the next sentence-aligned piece until the entire input is
digested.

```sh
# Summarize a file with custom focus instructions:
/noobia/dushich/tools/dushich_summarizer.py \
  --file /path/to/file.py \
  --context-size 32000 \
  --desired-size 8000 \
  --instructions "Focus on the functions in the file."

# Summarize a string directly (or pipe via stdin):
/noobia/dushich/tools/dushich_summarizer.py \
  --text "$LARGE_TEXT" \
  --instructions "Focus on the mentions of Banshee."
```

- `--file PATH` (`-f`): Read the text to summarize from a file.
- `--text STRING` (`-t`): Pass a large string directly on the command line (or omit both to read from `stdin`).
- `--context-size CHARS`: Input character window per pass (defaults to `32000` for `qwen3.8:27b`, `24000` for `gpt-oss:20b`).
- `--desired-size CHARS`: Target summary output size in characters (defaults to 25% of `--context-size`, i.e., `8000`).
- `--instructions TEXT` (`-i`): Optional custom instructions appended right after the base summarizer instructions (subtracted from the per-piece slice budget automatically).

### Lynx Remote Helper

Use `/noobia/lynx/tools/lynx_remote.py` (also linked at
`/noobia/aria/tools/lynx-remote`) for the two Lynx chores that were being
retyped by hand in the Review Lynx handoff session:

```sh
# Run one bounded command on Lynx over the pinned Alpine SSH link
# (default 192.168.100.107:2222, key-only auth, 20s timeout):
python3 /noobia/lynx/tools/lynx_remote.py run "printf 'BATTERY\n'; /usr/local/bin/lynx-status" --timeout 25

# Digest the newest trial result.json under /noobia/lynx/logs:
python3 /noobia/lynx/tools/lynx_remote.py result --glob 'v53-bt-after-alpine-*'
```

- `run COMMAND`: prints `exit=N`, clipped stdout, and a stderr snippet; exits with the remote exit code (124 on timeout). Replaces the `ssh_command(...)` + `argv[-2:-2] = ['-p', '2222']` boilerplate; supports `--ip`, `--port`, `--timeout`, `--max-output`.
- `result`: newest-first compact digest (state, boot_id, watchdog_mode, health-sample count and pass flag, nexus state, final steps); `--glob` narrows the `lynx/logs` directory pattern, `--limit` prints more than one.
- Never contacts Lynx unless `run` is explicitly invoked; offline tests live in `lynx/tools/test_lynx_remote.py`.

### Forge memory (`forge-db`)

**Ask the atlas before searching Nexus, and record what you find.**
`forge-db` (`/usr/local/bin/forge-db` → `/noobia/common/tools/forge_db.py`)
keeps Noobia's shared memory in `/noobia/dushich/workspace/forge.db`, next to
the Foreman's `projects` table:

- `nexus_paths`: important paths on Nexus with a kind, owner, one-line
  description, tags, and optional project. It records whether each path still
  exists.
- `project_notes`: short dated notes per project (decisions, state,
  handoffs, blockers) that cite atlas paths.
- Search by meaning: `forge-db search` mixes word matches with sentence
  embeddings, so "graphics card heat" finds the GPU monitor. It uses
  `qwen3-embedding:0.6b` on the RTX 5090 through Ollama only when that cannot
  evict Dushich's Qwen (the model is already loaded, or
  `OLLAMA_MAX_LOADED_MODELS` is at least 2). Otherwise it uses the CPU model
  `BAAI/bge-small-en-v1.5` (fastembed in `/opt/noobia/forge-venv`).
  `forge-db stats` shows which model is active, and switching models
  re-embeds on the next `forge-db embed`.

```sh
forge-db search where do we keep the gpu power logs
forge-db path set /noobia/rose/rose_composer -k dir -o Rose \
  -d "Song analysis and beat grids for Rose's choreography" -t "audio music" --by Gwyn
forge-db project list
forge-db project get Lynx                    # description, its paths, recent notes
forge-db note add Lynx "V53 boots; USB console still unproven" --path /noobia/lynx --by Aria
forge-db path check --prefix /noobia/lynx    # flag recorded paths that vanished
forge-db --json changes --since 2026-11-18T20:00:00+00:00
```

`--by` is required on every write: use your own name. Never store secrets or
key contents in a description. Add projects with `forge-db project add` only
when no existing one fits, and don't change another project's executor or
receiver. Tests: `python3 -m unittest discover -s /noobia/common/tools -p 'test_forge_db.py'`.

### Dushich explorer (`dushich-explore`)

**Use it for broad "where is / how does" questions about Nexus** instead of
sweeping the file system yourself. Dushich checks the atlas first, explores
with read-only commands on the local GPU (no cloud tokens), records what he
finds in `forge-db`, and answers briefly. Dushich is not sandboxed. The brief
asks him to change nothing but the atlas, and every result lists the atlas
rows he wrote so you can check them.

```sh
dushich-explore ask "Where does Lynx handle Bluetooth auth?" --by Banshee --timeout 600
dushich-explore start "How is the Council service started?" --by Aria   # returns a job ID
dushich-explore wait JOB_ID --timeout 120
```

A job usually takes 2–6 minutes and runs one at a time on the GPU. Job state
is kept in `/home/aria/.codex/dushich-bridge/explore/`.

### Media and browser tools

- `ffmpeg` and `sqlite3` are installed system-wide for audio, video, and
  database work.
- Playwright with its own headless Chromium lives in `/opt/noobia/web-venv`.
  Use it to open, click through, and screenshot web apps:
  `/opt/noobia/web-venv/bin/python your_check.py` with
  `from playwright.sync_api import sync_playwright`.

## Nexus Linux services

Put Nexus Linux service entry scripts in `/noobia/common/services/` and systemd unit
source files in `/noobia/common/services/units/`. The latter directory's
`install_services.sh` installs all unit source files into
`/etc/systemd/system/` and reloads systemd. Run it with `--dry-run` to
inspect the installation first. Enabling, starting, stopping, or restarting a
unit is a separate, reviewed action. Keep unit `ExecStart` paths explicit and
point them at the shared service entry scripts. Use stdout and stderr or the
journal for bounded, inspectable output.

Existing service source paths are still live. Migrate each one only after
checking installed unit references, permissions, dependencies, recovery
paths, and a safe rollback. Do not bulk-move a running service merely to
match this layout.

## Git and GitHub

Work on each repository's primary branch. In the shared `/noobia` repository
that branch is `main` (there is no `master` branch); Dushich's and Gwyn's
separate local repositories currently use `master`. Do not create task or
feature branches for routine work. Noobia's resident agents collaborate on the
same `main` branch; reserve separate branches for external collaborators when
their work needs its own review. Existing branches and worktrees contain
work that must be reviewed and reconciled before they are retired; do not
delete or reset them just to comply with this rule.

Check the repository, branch, remote, diff, and worktree status before a Git
operation. If a checkout is on a different branch, or the primary branch has
diverged, preserve the work and reconcile it before making a new task commit.
Stage only task-owned files. Commit at a verified, coherent
checkpoint and at task completion; for long work, make at least one checkpoint
commit per working session. A local commit does not deploy or publish work.

Noob authorizes routine, non-force pushes of verified, task-owned Noobia work
to the repository's primary branch. Confirm the remote and target branch
before pushing, and verify the remote hash afterward. Ask before force
pushing or rewriting history, publishing unrelated work, or creating a new
public repository. Report the commit ID, branch, remote, and confirmed remote
hash.

Dushich is the preferred operator for GitHub-facing work when his route is
available. Give him the repository, branch, remote, intended operation, and
required evidence. Never copy or print a private key or token. Preserve
unrelated work and verify consequential changes before relying on them.
