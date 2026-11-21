# Independent review of Gwyn's round-2 items (D5, Dushich, 2026-11-21)

Solo Dushich, per Gwyn's round-2 queue (forge #124): independent review of
`7fe3cd8` (display mapping), `79e4526` (touch design), `4f7f7e3` (the
codex-tool source-tracking fix), and `ba2ef26`'s full-health-capture test.

**Method.** Everything checked in a fresh `git clone --no-local` of `main`
(at `6e390b9`, so all four commits are included and no local-only files can
be present), with line-level verification against the source and the test
suites run inside the clone. Offline only: no phone contact, nothing
installed, no hardware action.

## Verdicts

| Item | Commit | Clean-clone evidence | Verdict |
| --- | --- | --- | --- |
| Media image actions → display | `7fe3cd8` | ui suite 113 OK; mapping, guard, map and README verified line-by-line | **ACCEPTED** |
| Touch events analysis + design | `79e4526` | ui suite 113 OK (incl. 4 contract tests); every fact checked against runtime source | **ACCEPTED** |
| Track `lynx_codex_tool.py` + `lynx_agent_health.py` | `4f7f7e3` | files tracked at HEAD; full-content audit clean; cancel contract **9 OK** in clone | **ACCEPTED** |
| Full health-capture UI test | `ba2ef26` | new test pins the 7/7 capture; ui suite 113 OK in clone | **ACCEPTED** |

### `7fe3cd8` — media image actions mapped to the display

- The premise holds: `lynx_agent_media.py:16-30` accepts `kind=sound|image`
  for play/stop and requires a catalog item for play — so the image path
  genuinely belongs to the screen.
- `lynx_tool_manifest.py`: new `ALSO_COMPONENTS` maps all four media tools
  to `platform/display`, with a guard that raises `ManifestError` when a
  secondary component is not a declared source component; the manifest
  entries keep `component: audio`, `status_source: platform`,
  `also_components: ["platform/display"]` — live state stays with the
  primary component.
- `status_only_map.json` (checked as JSON, not by eye): **14 components**,
  `platform/display` absent, priorities exactly `1..14`. README updated to
  match (14, display out, audio primary, attended beep audio-only).
- New tests assert the claim precisely:
  `test_media_image_actions_cover_the_display` (action `[lynx_media_play]`,
  stop `[lynx_media_stop]`, status `[lynx_display_status]`,
  `lynx_media_status` in reads, `attended == []`, display not in the
  status-only gaps) and
  `test_secondary_component_never_changes_live_state` (with a healthy
  display snapshot, media live state is still `interface_only` because the
  primary audio component is not validated).
- Staleness guard still active: `test_lynx_status_only_map.py` pins
  entry count 14, display absence, priorities `1..15` → `1..14`.

### `79e4526` — touch events consumption analysis and design

Every fact in the design doc checked against `lynx_noob_runtime.py`:

- `TOUCH_DEVICE = "/dev/input/event0"` (:41); `TouchInput` docstring:
  "Read one verified Synaptics contact **without grabbing the display's
  fd**"; no `EVIOCGRAB` anywhere in the source (the contract test asserts
  this).
- `RecordQueue` (:190): `deque(maxlen=8)` with a `dropped` counter that
  increments when the ring is full (oldest dropped), `pop()` takes the
  oldest. Matches the doc.
- `reg(380, "TOUCH_STATUS", ...)` reads only `panel`, `down`, `queued`,
  `dropped` — non-consuming, verified in the handler body.
- `reg(381, "TOUCH_POLL", ...)` is the **only** code that pops
  `touch.events` (contract test asserts `source.count("self.touch.events.pop(") == 1`),
  and the queue is shared by every NRP caller — the doc's shared-queue
  warning is therefore the right caution, not overkill.
- Scoping is honest: "one reader of the panel" is a claim about the Lynx
  runtime. The old V47-era `lynx_touch_events.c` raw probe also opens
  `event0`, but it is a standalone tool, not an NRP-queue poller — no
  conflict with the doc's claims.
- The proposal is properly gated: non-consuming peek tool first, capped
  drain only after Aria confirms no other consumer, `TOUCH_PEEK` runtime
  change explicitly Aria's decision; the missing attended receipt is named.

### `4f7f7e3` — source-tracking fix for the item-1 defect

- Both files are now tracked at HEAD (`git ls-files`); the commit adds
  exactly 147 lines of new files.
- **Secret audit (full read of both files):** no keys, tokens, passwords,
  or secret paths. `lynx_codex_tool.py` is a bounded wrapper (unprivileged
  `lynx-coder` uid check, model pinned to `gpt-oss-20b`, 120 s
  `killpg` timeout, output caps, minimal env). `lynx_agent_health.py` is a
  read-only queue scanner with privacy checks (`0o700`/`0o600`, owner
  checks) — and its JSON shape (`counts`, `oldest_pending_seconds`,
  `stopped`, `issues`) is exactly what my health collector maps, so the
  seam is consistent.
- The defect I reported in the item-1 review (forge #117) is **fixed and
  verified from a clean clone**: `test_agent_cancel_contract` is **9 OK**
  there (it was 8 OK + 1 ERROR before the fix).

### `ba2ef26` — full health-capture test

`test_full_live_capture_has_no_unknowns` pins my
`lynx-live-20261121-full.json`: verdict `ok`, all **7** checks `ok`, and no
"checks unknown" text in the rendered section. The original test still
pins the interim capture with its two `unknown`s — so both examples are
covered, which is exactly the split I recommended in forge #121. Passes in
the clean clone (ui suite **113 OK**).

The round-2 review section in `LYNX-REVIEW-AND-QUEUES-GWYN-20261121.md`
is factually consistent with everything above (including the "health
95 OK, 2 errors in a clean clone" record of my pre-fix state, which I
reproduced independently).

## New finding (pre-existing, outside the four reviewed items)

The same v19 import-time landmine from D3 also breaks `lynx/tools/agent`
in a clean clone:

- `deploy_native_mcp_catalog.py:18` imports `lynx_wifi_v19_contact` at
  **module level**; that module reads the gitignored, machine-local
  `linux-port/artifacts/.../build-validation.json` at import time
  (`lynx_wifi_v19_contact.py:7`).
- Result in a clean clone: `test_deploy_native_mcp_catalog.py` fails to
  even load (`ImportError`), so `discover -s lynx/tools/agent` is
  **15 tests, 1 error**.
- This is **not** a regression of any reviewed item: the file is Aria's
  (`61522d0`, 2026-11-18) and predates all of round 2.
- Fix options for Aria (via Gwyn): make the v19 import lazy (inside the
  deploy function, the way `lynx_health_collect.make_ssh_runner` does it),
  or stub `sys.modules['lynx_wifi_v19_contact']` in the test as D3 did.

## Evidence summary (all in the clean clone at `6e390b9`)

| Suite | Result |
| --- | --- |
| `lynx/tools/ui` (113 tests) | OK |
| `lynx/tools/health` (97 tests) | OK |
| `test_agent_cancel_contract` (9 tests) | OK |
| `discover -s lynx/tools/agent` (15 tests) | 14 OK, 1 error (pre-existing, see finding) |

No phone contact, nothing installed, offline only.
