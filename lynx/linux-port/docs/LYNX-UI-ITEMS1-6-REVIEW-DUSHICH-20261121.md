# Independent review: Gwyn backlog items 1-6 (Dushich, 2026-11-21)

Task: Gwyn's interim queue (`LYNX-REVIEW-AND-QUEUES-GWYN-20261121.md`,
Solo Dushich item 1). Gwyn does not review his own work; this review is mine.
Offline only: no phone contact, no edits to `lynx/tools/ui` or
`lynx/tools/agent`.

## Method

- Fresh clone: `git clone --no-local /noobia` into a scratch dir; all test
  runs below executed **in the clone**, per the queue doc's method.
- `python3 -m unittest discover -s lynx/tools/ui -p 'test_*.py'`
- `python3 -m unittest discover -s lynx/tools/agent -p 'test_agent_cancel_contract.py'`
- Each note's claims (#91, #94, #96, #97, #99, #102) checked against source
  in the clone/working tree, line by line where cited.

## Test evidence (fresh clone)

| Suite | Result |
| --- | --- |
| `lynx/tools/ui` (106 tests, items 2-6 plus item 7) | **OK, exit 0** |
| `lynx/tools/agent -p 'test_agent_cancel_contract.py'` (9 tests) | **8 OK + 1 ERROR, exit 1** |

The one error is a real defect, detailed under item 1.

## Item 1 - `AGENT_CANCEL` no-go (8aff46d, note #91): ACCEPTED, with one defect in the committed test

The analysis holds. Every code claim matches:

- `lynx_noob_runtime.py:734` = `reg(512, "AGENT_CANCEL", self.agent_cancel)`;
  the handler `agent_cancel` starts at :762 (the note cites :763, its first
  body line; off by one, substance matches). It calls
  `agent_job_queue().cancel()` and returns `cancelled=0|1`.
- `lynx_agent_queue.py:129` = `def cancel`: under lock, unlinks **only the
  pending** file; a symlink raises `QueueError`; missing, running, or finished
  jobs return `False` (cancelled=0). Verified.
- `lynx_codex_tool.py` (working tree): synchronous `Popen` +
  `communicate(timeout=120)` with `killpg` on timeout; no job ID, no queue,
  so `AGENT_CANCEL` can never stop it. The no-go verdict is correct.
- Worker timeout is exactly 180 s: `lynx_agent_worker.py:100`.
- Authorization is connection-level in `serve()`: peer filter at :1428,
  `SO_PEERCRED` uid check at :1432-1433 (note cites :1433), Nexus HMAC
  challenge at :1435-1437 (note cites :1437). No per-job owner check. Matches.
- The doc `LYNX-AGENT-CANCEL-20261121.md` is in the repository, verdict
  NO-GO, the `lynx_codex_stop` proposal is clearly marked unimplemented.

**Defect (concrete):** the committed test
`lynx/tools/agent/test_agent_cancel_contract.py:95` reads
`lynx/tools/agent/lynx_codex_tool.py` from the tree. That file is **not in
Git**: it is untracked and ignored by `lynx/.gitignore:8` (`/tools/*` has no
negation for the `agent/` subdirectory, unlike `local_calls/`, `health/`,
`usb/`, etc.), and it was never committed (`git log --diff-filter=A --all` on
both candidate paths is empty). `git check-ignore -v` confirms
`lynx/.gitignore:8:/tools/*`. Consequence: in a fresh clone the suite is
**8 OK + 1 ERROR** (`FileNotFoundError`), not the "9 OK" claimed in note
#91. It only passes in a working tree where the installer has left the file
behind. Note `install_codex_persistent.py:18` (also untracked) references the
same path.

Fix options (Gwyn's lane / Aria's call, I did not edit):
1. `git add -f lynx/tools/agent/lynx_codex_tool.py` so the committed test and
   the installer reference a tracked source of truth, or
2. make the committed test not depend on an untracked file (assert the
   no-queue property from the tracked runtime + queue modules only, and keep
   the source-text assertion in a working-tree-only test).

Either way the note's "9 OK" claim does not reproduce in a clean clone and
should be re-stated with the fix.

## Item 2 - status-only map (403bbc7, note #94): ACCEPTED

- `status_only_map.json` holds exactly **15** components; gap split
  `missing_wrapper 2` (touch, display), `trial_needed 7` (headset, bluetooth,
  camera, gnss, nfc, usb, fingerprint), `blocked 2` (cellular, sim),
  `status_is_function 4` (battery, thermal, storage, wifi) - exactly the
  note's `missing_tool 2 / trial_needed 7 / blocked 2 / none 4`.
- Staleness guard verified at `lynx_status_only_map.py:89-94`: if the map's
  component set differs from the coverage audit's status-only set it raises
  `MapError("status-only map is stale: ...")`.
- Driver absence is a separate `driver_loaded_this_boot` field, never a
  missing-tool claim - matches the note's stated rule.
- Map loading is strict (exact field set, duplicate and 1..N priority checks,
  cited route with source).

## Item 3 - snapshot age and boot guard (aef8efe, note #96): ACCEPTED

- `lynx_snapshot_age.py`: `MAX_AGE_S = 15*60`, `CLOCK_SKEW_S = 2*60`;
  states `fresh / stale / future / unknown_time / malformed_time`; boot states
  `same_as_previous / changed_since_previous / no_previous / unknown`; boot
  IDs must fullmatch a UUID regex. All match the note.
- Broker `lynx_status_snapshot.py:53-60` runs exactly **five** fixed
  read-only commands; the fifth is `cat /proc/sys/kernel/random/boot_id`,
  UUID-validated (`BOOT_LINE`, "boot ID is not a UUID").
- Board shows the stale/clock-skew banner and "as captured" framing
  (`lynx_tool_board.py:177-185`).

## Item 4 - catalog diff (2cdcba4, note #97): ACCEPTED

- `SHORT = 12` in `lynx_catalog_diff.py`: only names plus 12-char hash
  prefixes are emitted.
- `preview()` = JSON-escaped 40-char preview; hostile names are counted in
  `rejected_entries.count`, not embedded raw.
- `--fail-on-drift` exits **2** on drift (`lynx_catalog_diff.py:193`).
- Per-tool statuses `in_sync / hash_differs / missing_on_phone /
  added_on_phone / partial` with per-file json/sh state; `--limit` bounds the
  list while exact counts are kept (`entries_truncated`).
- Duplicate snapshot keys are reported, and the broker rejects duplicate
  catalog lines (`lynx_status_snapshot.py:91`, `parse_catalog`).

## Item 5 - board a11y checker (684152b, note #99): ACCEPTED

- `check_board_a11y.py` uses Playwright (shared web-venv), light and dark at
  1200/390 px, and checks per-element WCAG contrast (4.5:1 normal / 3:1
  large), heading outline, landmarks, Tab reach with visible focus,
  horizontal overflow, and forbidden/remote elements - as documented in the
  note.
- Exits 1 on any failure: `sys.exit(0 if result["ok"] else 1)` (:129).
- It is a page check only; no hardware claim is made.

## Item 6 - board health section (5091b93, note #102): ACCEPTED

- `lynx_health_view.py` accepts **only** schema `portable-health/1` and host
  `lynx`; anything else raises (`HealthError`), so a schema change shows
  "not shown", never a misread.
- `_status()` maps only `ok/warn/fail/unknown` through; everything else is
  displayed as `unrecognized`, never as ok.
- Bounded input (256 KiB, 50 checks, 160-char evidence) and no
  `subprocess`/`socket`/ssh imports: it never runs the collector or
  evaluator and never contacts Lynx. Verified.
- Board wiring: `--health FILE` (default `state/health.json` if present),
  rendered read-only from the saved report (`lynx_tool_board.py:26-33,
  232-233, 278-301`).

## Verdict summary

| Item | Commit | Verdict |
| --- | --- | --- |
| 1 AGENT_CANCEL no-go | `8aff46d` | **Accepted in substance; one concrete defect** - the committed test depends on the untracked, git-ignored `lynx/tools/agent/lynx_codex_tool.py`, so the suite fails (8 OK + 1 ERROR) in a fresh clone, not the claimed 9 OK |
| 2 status-only map | `403bbc7` | Accepted |
| 3 snapshot age/boot guard | `aef8efe` | Accepted |
| 4 catalog diff | `2cdcba4` | Accepted |
| 5 board a11y checker | `684152b` | Accepted |
| 6 board health section | `5091b93` | Accepted |

No phone contact during this review; no files outside this document changed.
