# Dushich coding trial, 2026-11-04

## Installed runtime

`dushich` launches Codex CLI 0.166.0 under a separate, unprivileged Unix
account, with its own `/home/dushich/.codex` history and
`/noobia/dushich/workspace` (migrated from `/home/dushich/workspace` on 2026-11-05). Inference goes to loopback Ollama 0.40.14, model
`gpt-oss:20b`. The tag was imported from the verified MXFP4 GGUF conversion
already used by Nexus llama.cpp (see `docs/NEXUS-INFERENCE.md`), so it is not
Ollama's separately downloaded model package. Ollama reports tool, completion,
and thinking capability, a 131,072-token model maximum, and 65,536 allocated
context tokens at 100% GPU placement.

With Ollama alone, GPU memory use was about 13.5 GiB. With the existing
llama.cpp service also loaded, total GPU memory use was about 24.9-25.3 GiB of
31.8 GiB. Ollama runner RSS was about 2.2 GiB (some model pages are shared or
mapped); system RAM remained about 53 GiB available. A longer trial reached
about 425 W and 53°C, with no noise reported by Noob during that trial.

## Practical coding evidence

- Dushich created `projects/mini_ledgers/ledger.py`, added tests, ran them, and
  improved validation of non-finite Decimal amounts. Independently rerun:
  `python3 -m unittest discover -s projects/mini_ledgers/tests -q` → 7 tests OK.
  Dushich committed the project and root `.gitignore` as `2b8b044`.
- Dushich created `projects/seekline/` with a regex-search CLI, tests, and a
  README. Its first response only described files; on a resumed Codex session
  it actually created them with terminal tools. In another turn it fixed a
  trailing-whitespace/CRLF bug after a failing test, reran the suite, and made
  commit `799a1b8`. Independently rerun:
  `python3 -m unittest discover -s projects/seekline -q` → 10 tests OK.
- The Codex sandbox was tested directly with `git add` and `git commit` under
  `dushich-workspace`. The profile gives `.git` write access only in Dushich's
  workspace. It does not give the Unix account sudo rights or enable terminal
  network access. The workspace Git tree was clean after the two project
  commits.
- Measured wall times: 9.25 s for a one-test edit, 10.30 s for the corrected
  initial seekline creation, 29.99 s for the failing-test fix and Git commit,
  and 19.19 s for the ledger package markers, tests, and Git commit. The first
  simple Ollama generation took about 64 s including a 31 s cold load; warm
  coding tasks were substantially quicker.

## Delegated task runner trial

`dushich task` now runs bounded Codex turns and verifies real tool calls,
changed expected files, sandboxed test commands, and optional clean commits.
It stores private JSONL events and a verification report in
`/home/dushich/.codex/task-runs/`. A word-count task deliberately exposed a
failure: Dushich committed tests with a wrong script path, then duplicated the
tests in a second directory. The runner returned `FAIL` after two attempts
because independent tests failed. That failure remained visible in its report.

A narrow follow-up Codex task repaired the path. Another task consolidated the
tests under a discoverable package and committed the cleanup. A fresh delegated
task then improved punctuation-aware tokenization, added a test, passed two
independent test commands in one attempt, and committed as `964c637` in 11.83 s.
Independent final verification found a clean Git tree and 5 word-count tests,
7 ledger tests, and 10 seekline tests passing (22 total). The runner was then
tightened to reject zero discovered tests and unchanged expected files, and to
offer `--require-commit`; those changes passed syntax and CLI checks, while the
prior successful run exercised the main task verification path.

## Limits and operating guidance

`gpt-oss:20b` is useful for bounded coding tasks, but it is less reliable than
Aria's cloud model on broad, multi-step prompts. It initially confused a
directory with a Python package, looped over harmless empty directories, twice
claimed work or a commit that did not exist, and on one large prompt returned
code in a message without creating files. The persistent `AGENTS.md` now
requires tool-backed file, test, and commit verification. For delegated work,
give one bounded task at a time and independently verify the resulting files,
test output, and Git history. Do not treat a prose success claim as proof.

Nexus was powered off after a reported loud noise earlier in the evening.
Software logs showed an orderly shutdown and no thermal or GPU fault. Noob
reported quiet during subsequent brief and longer GPU coding trials. A physical
fan or cable cause cannot be ruled out by software telemetry alone.

Council and Argus integration are not configured. Dushich currently works via
the local terminal launcher only.

## 2026-11-05 idea_spark handoff incident

The two-pane monitor initially displayed Aria's earlier `seekline` trial until
a new handoff arrived. A later user-initiated `idea_spark` task failed after two
runner attempts. Its Codex event log records repeated nested `bash -lc` patch
commands with unbalanced single quotes (`unexpected EOF while looking for
matching`), plus repeated delete/recreate operations. The log has 66 nested
shell commands, 10 quote failures, and 168 stream-fd warning lines. The final main file was
missing; the untracked test file was preserved under
`/home/dushich/.codex/task-runs/recovery-idea_spark-20261105/` before retry.

`Failed to create stream fd: Operation not permitted` was reproduced with a
sandboxed login shell. Ubuntu's `im-config` profile calls `systemd-cat`, whose
logging stream is denied in the restricted sandbox. The same commands could
still exit 0 and write inside the workspace. This message was separate from
the shell quoting failure. Dushich's workspace instructions now forbid nested
shell wrappers and direct him to report repeated quoting errors. The task
runner also stops a turn after four such errors; a synthetic event-stream test
confirmed the stop condition.

The sparse failed handoff had `no_session_context=true` and only 270 bytes of
context. That opt-out has been removed from the MCP and bridge interfaces so
future handoffs require a readable Aria session ID. This was a separate context
gap; the evidence does not prove it caused the quoting loop.

The utility was retried as smaller tasks. `idea_spark.py` was created and
committed as `613e26e`; the sentence template and initial tests were committed
as `cfe5c10`; stronger CLI/function and invalid-input tests were committed as
`bbe4893`. Independent verification ran 3 tests successfully, checked
`--seed 7` output, and found Dushich's Git tree clean.
