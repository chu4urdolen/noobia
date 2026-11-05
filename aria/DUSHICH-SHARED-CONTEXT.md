# Shared context for Dushich handoffs

This is Aria's durable, human-readable context for Dushich. Update it when a
decision matters beyond one task. The bridge attaches it to each handoff along
with recent visible conversation, Noobia's project instructions, and the code
map. Task-specific files still need explicit `--include` or MCP `files` entries.

## Working relationship

Noob and Aria work in the main Codex conversation. Dushich works quietly in a
separate local Codex CLI session using Ollama `gpt-oss:20b` on Nexus. He has his
own Unix account, workspace, Git history, instructions, and session history.
He may implement, run tests, debug, and commit a bounded task in his workspace.
The handoff runner checks tool use, changed files, tests, and a clean commit.
When a task fails verification or needs a decision, report the blocker to Aria.
Aria and Noob can inspect the exact task brief and full event log if needed.

## Boundaries

Dushich's workspace is `/noobia/dushich/workspace`. The project source tree is
`/noobia`; its code map is `/noobia/docs/CODE-MAP.md`. A Dushich commit in his
workspace does not automatically change shared Noobia code or deploy to a
device. Aria reviews relevant code before adopting it. Inference stays local;
the launcher pins Ollama and refuses unavailable local inference.

The context packet contains visible user and Aria text plus bounded excerpts of
recent visible tool calls and results, not private reasoning. Older material may
be omitted to fit the local model's context.
This document records decisions that should survive such trimming.

## Current coordination decisions

- Prefer small, clearly bounded tasks with an expected file and independent
  test command.
- Keep Dushich's working steps and event stream in his private task log. Return
  a concise final report or a concrete blocker.
- Continue a Dushich Codex thread for related follow-up tasks so local context
  and debugging history remain available.
- Send relevant source and design files explicitly when they are outside his
  workspace or central to the task.
