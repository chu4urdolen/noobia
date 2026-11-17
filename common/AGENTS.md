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
feature branches for routine work. Existing branches and worktrees contain
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
