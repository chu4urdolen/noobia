# Dushich local coding environment

This setup follows [Ollama's Codex CLI integration](https://github.com/ollama/ollama/blob/main/docs/integrations/codex.mdx)
and the separate `CODEX_HOME` pattern in
[Photowalk's example](https://github.com/Photowalk/codex-local-model-switching).

`dushich` starts Codex CLI in `/noobia/dushich/workspace`, using the local
`gpt-oss:20b` model served by Ollama on loopback. `dushich exec "task"` runs a
bounded noninteractive coding task. `dushich resume` resumes a saved session.
`dushich exec resume --last "follow-up"` continues the last noninteractive task.
Use `dushich exec --json "task"` when a caller needs a machine-readable event
stream for delegation.

The separate [solo launcher](../solo/README.md) runs with Aria-level host
permissions. The normal `dushich` launcher and delegated task runner now have
full host access without Codex approvals too. Helper Dushich runs as `aria`,
with that account's passwordless sudo, as Noob requested on 2026-11-17.

Dushich is the primary operator for GitHub-facing repository work in helper
and solo modes. Helper mode uses its dedicated GitHub SSH key at
`/home/aria/.ssh/noobia_dushich_github`; the launcher sets
`GIT_SSH_COMMAND` so Git uses that key without an SSH agent. Solo mode also runs as
Aria. For the outer checkout, clear the helper
launcher's isolated `GIT_DIR` and `GIT_WORK_TREE` before running Git:

```sh
env -u GIT_DIR -u GIT_WORK_TREE git -C /noobia status
```

A separate Dushich GitHub key pair is registered at
`/home/aria/.ssh/noobia_dushich_github{,.pub}` (backed up under `private/ssh/`). Do not commit
or print private key contents. GitHub API actions such as managing issues and pull requests
will need separate authentication; the SSH key covers Git transport.

Aria can invoke the same local runner through `/noobia/aria/delegate-dushich`,
which reads the private verification report and prints Dushich's final reply.
For quiet background work, `/noobia/aria/dushich-bridge start` returns a task
ID; `status`, `report`, and `events` expose progress and audit data. Handoffs
from the same Aria conversation continue one Dushich Codex thread by default;
new Aria conversations start separate Dushich threads. The bridge is also
available as a local MCP server in Aria's default Codex CLI.

For a bounded delegated implementation task, use `dushich task` with explicit
evidence to check:

```sh
dushich task \
  --expect projects/wordcount/wordcount.py \
  --test 'python3 -m unittest discover -s projects/wordcount -q' \
  --require-commit \
  'Improve the word-count CLI and its tests; commit after tests pass.'
```

The task runner requires a clean Git tree at the start. It saves the Codex
event stream and a JSON verification report under
`/noobia/dushich/coding/private/codex/task-runs/`. Codex events stream to
the JSONL file while he works, so Aria's two-pane monitor can show commands and
status before the final report. The runner checks that Codex used tools, an
expected file changed, the requested tests ran and did
not discover zero tests, and a new commit exists when requested. `--test` may
be repeated. It retries once with the verification failure, with per-attempt
timeouts, then returns a failing exit code if the task remains incomplete.
Failed tasks can leave files or commits in Dushich's isolated workspace; review
the saved report and Git history before the next delegated task.

The launcher runs under the shared `aria` Unix account. Its own
`CODEX_HOME` at `/noobia/dushich/coding/private/codex` holds configuration and persistent
session history. Codex is installed separately at
`/opt/noobia/dushich-codex`; Aria's installation and configuration are not
used. Helper instructions live at [`AGENTS.md`](AGENTS.md), linked from
`/noobia/dushich/coding/private/codex/AGENTS.md` so Codex loads
them for helper sessions.
The solo agent has separate instructions in [`../solo/AGENTS.md`](../solo/AGENTS.md),
linked into its own Codex home. The planned foreman role has its own
[`../foreman/AGENTS.md`](../foreman/AGENTS.md); no foreman launcher is active yet.
The workspace has no shared `AGENTS.md`, preventing one role's instructions
from appearing in the other role's context.
The workspace has its own Git history in `.dushich-git/`; this directory is
private and ignored by Noobia's outer repository. The launcher sets `GIT_DIR`
and `GIT_WORK_TREE` so Dushich's commits stay in his own history while his
source files can also be published in the Noobia repository.
On 2026-11-15, the workspace's deleted, obsolete `AGENTS.md` and five Forge
helper scripts were recorded in local commit `f35b450`. The live `forge.db`
and a scratch `test.txt` are ignored, leaving the isolated Git tree clean for
verified handoffs without moving or modifying the database. No GitHub push
was part of that cleanup.

Codex uses `danger-full-access` with approval `never`. The shared `aria` account has
passwordless sudo via `/etc/sudoers.d/90-aria-noobia`; use `sudo -n` for
root-owned paths. The launcher removes inherited API credentials, pins Ollama
and `gpt-oss:20b`, and refuses to run when local Ollama is down.

The 131K context is requested in both Ollama and Codex. Confirm actual allocation
with `ollama ps` after the model loads. Ollama runs only on `127.0.0.1:11434`.
The authenticated Noobia LAN endpoint on port 8080 forwards inference to this
same Ollama runner, so Dushich and LAN clients share one GPU model copy. The
proxy warms the model at boot and keeps it loaded. See
`common/NEXUS-INFERENCE.md` for measured VRAM use and service controls.
The Ollama service override source is `ollama-override.conf` in this directory.
The `gpt-oss:20b` tag is built from the already verified local GGUF conversion
of OpenAI's weights, avoiding a second large network download. The model source
and its SHA-256 are recorded in `common/NEXUS-INFERENCE.md`. `model.json` is the
local Codex model-catalog snapshot generated by Ollama for this model.
The practical coding test and observed limits are recorded in
[`TRIAL-STATUS.md`](TRIAL-STATUS.md).

To update this environment, edit the source files here, then install them:

```sh
sudo install -o aria -g aria -m 600 dushich/coding/config.toml /noobia/dushich/coding/private/codex/config.toml
sudo install -o aria -g aria -m 644 dushich/coding/model.json /noobia/dushich/coding/private/codex/model.json
ln -sfn /noobia/dushich/coding/AGENTS.md /noobia/dushich/coding/private/codex/AGENTS.md
ln -sfn /noobia/dushich/solo/AGENTS.md /noobia/dushich/solo/private/codex/AGENTS.md
sudo install -o root -g root -m 755 dushich/coding/dushich-launcher /usr/local/bin/dushich
sudo install -o root -g root -m 755 dushich/coding/dushich-task.py /usr/local/libexec/dushich-task.py
```

The Codex CLI installation runs as `aria` and can be updated with
`npm install --prefix /opt/noobia/dushich-codex @openai/codex@latest`.
Ollama's service has the context and loopback settings in
`/etc/systemd/system/ollama.service.d/noobia-dushich.conf`, installed from the
override file here. The Ollama model can be reconstructed with
`ollama create gpt-oss:20b -f dushich/coding/Modelfile` after placing the GGUF
at the `FROM` path named in that Modelfile. This installation used a hard link
to the already verified GGUF in `/home/aria/models/gpt-oss-20b/` and invoked
`ollama create` as the `ollama` Unix user so the service could read it.
