# Lynx review and work queues: Gwyn coordinating (2026-11-21)

Aria ran out of tokens. Noob asked Gwyn to take up reviews and task
assignments until she returns. This is a **temporary, bounded** role:
- offline reviews and offline task assignment only;
- live hardware trials, phone installation and deployment stay Aria's;
- nothing here approves a phone change;
- Gwyn does not review his own work: Dushich does.

Aria may revise any of it on her return.

## Reviews

Method for each item: read the commit diff, run the item's tests from a fresh
`git clone --no-local /noobia`, spot-check claims against source, and check
that any phone-side code is read-only and gated.

All Banshee suites pass in the clean clone. The live collectors
(`usb/lynx_usb_collector.py`, `fingerprint/lynx_fingerprint_inventory.py`)
send read-only shell only (`cat`, `ls`, `readlink`, `ps`; the only
redirections are `2>/dev/null`) and refuse to run without
`--live --allow-live`.

| Banshee item | Commit | Tests | Verdict |
| --- | --- | --- | --- |
| 1 USB ACM collector and attended plan | `b472549` | usb suite, 17 OK (with item 2) | **Accepted** as an offline and gated read-only collector. The attended plan needs Aria and Noob before any run |
| 2 USB NRP transport prototype | `3d2cf6b` | in usb suite | **Accepted** as an offline prototype only. No key material in the tree. Not approved for the phone |
| 3 Fingerprint inventory and secure boundary | `42ba23b` | 7 OK | **Accepted** (offline; live mode gated and read-only) |
| 4 NFC tag-exchange validator and attended plan | `2a93622` | 5 OK | **Accepted** offline. The tag trial is Aria's, attended |
| 5 Bluetooth cold-boot acceptance gate | `f4930e6` | 8 OK | **Accepted** offline. The trial is Aria's |
| 6 Headset insertion evidence | `6f11b19` | 7 OK | **Revise:** the doc labels Lynx "OnePlus 11R 5G / MT6895" (line 7), and the jack claim rests on that label |
| 7 Second rear light gate | `48353af` | 5 OK | **Revise:** wrong device label, and "PROVEN ABSENT" is too strong. See the correction below |
| 8 Main and front camera dependency map | `36cd005` | 6 OK | **Revise the label only** (line 7, same "11R/MT6895" error). The content cites Lynx's `_22823` sources |

### Correction to the platform question (Aria #107)

Banshee's identity label is wrong. Lynx is a **OnePlus Nord 3 5G, CPH2493,
MediaTek MT6983**; she is not a OnePlus 11R or an MT6895.

However, project **`22823` / "Vitamin" is Lynx's own platform**, not the
11R's:
- The cited file
  `lynx/linux-port/sources/snapshots/kernel-mt6983/arch/arm64/boot/dts/mediatek/cust_mt6983_vitamin_camera_v4l2.dtsi`
  comes from OnePlus's official repository
  `OnePlusOSS/android_kernel_5.10_oneplus_mt6983`, on branch
  `oneplus/mt6983_t_13.1_oneplus_nord_3_5g` (checked with
  `git -C lynx/linux-port/sources/kernel-mt6983 remote -v` and
  `branch --show-current`).
- Lynx's attended flashlight receipt names chip `lm3642_22823` on device
  CPH2493 (`lynx/tools/flashlight-visual-confirmation.json`).
- Lynx's vendored sensor sources are `gc02m1/imx355/s5k3p9sp_mipi_raw_22823`.

So the cited lines 312–334 (one `lm3642_22823` with a single `flash@0`) are
real source evidence **for Lynx's source tree**. Aria's alert was right that
the label is wrong. It was probably wrong to treat the Vitamin device tree as
another phone's.

The verdict still cannot be "PROVEN ABSENT". A source device tree is not
Lynx's running device tree, and a second light could sit on another
controller. The correct wording is: "the source DT declares one lm3642
channel; live confirmation pending".

A hypothesis for Banshee to test: the "second rear light" may be the
ambient-light sensor window. `lynx_light_read` describes a "lower pale rear
circle" with a verified optical response.

## Gwyn's own items (not self-reviewed)

Gwyn backlog items 1–6 have no independent review:

| Item | Commit |
| --- | --- |
| 1 | `8aff46d` |
| 2 | `403bbc7` |
| 3 | `aef8efe` |
| 4 | `2cdcba4` |
| 5 | `684152b` |
| 6 | `5091b93` |

Aria reviewed item 7 (`5f45d3b`, #109). Items 1–6 are assigned to Dushich
below.

## Queues (offline only; work in order; one commit and forge note per item)

Shared rules from the team handoff still apply:
- `forge-db project touch lynx --for <you> --by <you> --together` before each
  item;
- run your own tests, and record the command, result, commit and remote hash;
- stage only your own files;
- no phone writes, module loads, service installs, modem or RF actions, or
  unattended physical trials.

### Banshee

1. **Fix the platform identity** in items 6, 7 and 8, including the flashlight
   tool's docstring, fixture name and metadata, and the test name.
   - Use OnePlus Nord 3 5G CPH2493, MT6983, project 22823 "Vitamin".
   - Cite the Nord 3 kernel branch.
   - Downgrade item 7's verdict to "source DT declares one lm3642 channel;
     live confirmation pending".
   - Re-check whether the headset doc's jack claim holds for the Nord 3,
     citing sources.
   - Tests must still pass.
2. **Live-DT gate for the rear light, read-only and gated.**
   - Add an optional `--live --allow-live` read of Lynx's running device tree
     under `/sys/firmware/devicetree/base`: every `lm3642*` node, its
     `flash@*` children, and any other flashlight-compatible node. Use the
     same read-only pattern as your fingerprint collector.
   - Add fixtures for one channel, two channels and a missing node.
   - Test the light-sensor-window hypothesis against `lynx_light_read` and the
     sensor DT, and record what explains the second rear circle.
   - Do not actuate any light. Gwyn reviews.
3. **Bluetooth link-state read design** (status-only map priority 4).
   - Design an agent-facing, read-only link-state report on top of
     `BT_STATUS` (NRP 393) and `lynx_bluetoothd.py`, as an offline collector
     with fixtures and tests.
   - No radio start or stop.
   - Aria owns any live trial.

### Solo Dushich

1. **Independent review of Gwyn's backlog items 1–6** (commits above;
   claims in forge notes #91, #94, #96, #97, #99 and #102).
   - Run `python3 -m unittest discover -s lynx/tools/ui -p 'test_*.py'` and
     `python3 -m unittest discover -s lynx/tools/agent -p 'test_agent_cancel_contract.py'`
     in a fresh clone.
   - Check each note's claims against the code. In particular, check the
     `AGENT_CANCEL` no-go in `LYNX-AGENT-CANCEL-20261121.md` against
     `lynx_noob_runtime.py` and `lynx_agent_queue.py`.
   - Report accept, or the concrete defects, in forge. Do not edit
     `lynx/tools/ui`.
2. **Fill the two `unknown` machine checks** in `lynx/tools/health` only.
   - Map `lynx_modem` from the read-only `lynx-platform-status cellular`
     `md1_state_code`, and `lynx_agent_queue` from `lynx-agent-health` queue
     counts.
   - Missing facts stay `unknown`.
   - Use fixtures and tests. Keep the bounded SSH pattern Aria accepted in
     #103. No install.

### Gwyn

1. **Display actions.**
   - Map image play, stop and status (`lynx_media_*` with `kind=image`) to the
     display in the coverage audit and the status-only map, so the display is
     no longer shown as status-only. This is the map's priority 2.
   - Manifest and UI only; no wrapper changes.
2. **Touch-events read design** (priority 1).
   - Write an offline analysis of who consumes `TOUCH_POLL` events on Lynx
     (`lynx_noob_runtime.py:997-999`).
   - Propose either a non-consuming peek or a capped drain, with a proposed
     manifest and offline tests.
   - Do not deploy. Aria decides on the runtime change.
3. **Review Banshee's queue items 1–3 above** as they land.

## Round 2: reviews and queues (Gwyn coordinating, 2026-11-21 ~01:00 UTC)

### Reviews

Every suite was run from a fresh `git clone --no-local`.

| Item | Commit | Clean-clone tests | Verdict |
| --- | --- | --- | --- |
| Banshee 1: identity correction | `fcdd39b` | headset, flashlight and camera_deps OK | **Accepted** (#116). Wording nit: the jack is "absent per published spec", not physically verified |
| Banshee 2: live running-DT light check | `564f79a` | flashlight 9 OK | **Accepted** |
| Banshee 3: Bluetooth link-state design | `d5681f5` | bluetooth 18 OK | **Accepted** as an offline design and gated read-only collector |
| Dushich 1: review of Gwyn items 1–6 | `289565f` | — | **Accepted.** He found a real defect in Gwyn's item 1, now fixed (see below) |
| Dushich 2: health machine facts | `3fa41fe` | health 95 OK, **2 errors** | **Accepted with one fix** (D3 below) |

**Banshee 2.**
- The live script is read-only: `find`, `cat`, and a Python reader; the
  only redirections are `2>/dev/null`. It is gated by `--live --allow-live`.
- It searches `*lm3642*`, `*flashlight*` and `flash@*`, not only the known
  node.
- Her result: one `lm3642@63` with a single `flash@0`, and no other flash
  node.
- The second rear circle is the ams TCS3408 colour/ALS sensor (`rear_cct`).
  This is consistent with the tracked `LYNX-REAR-LIGHT-AND-COLOR-SENSOR.md`.
- The question of a second rear *light* is answered: there is none in the
  running DT. Banshee should keep the raw output of that live run as a
  receipt (B4).

**Banshee 3.** The live script uses only `rc-update show`,
`rc-service … status`, `lsmod`, and existence tests. No radio or service
action.

**Dushich 1.** In a clean clone, `test_agent_cancel_contract.py` errored
because `lynx/tools/agent/lynx_codex_tool.py` had never been committed.
Gwyn's #74 claim that it was tracked was wrong: that list came from `ls`,
not `git ls-files`. Fixed by tracking `lynx_codex_tool.py` and
`lynx_agent_health.py`, after auditing them: no keys, tokens or addresses.
The clean clone now gives 9 OK.

**Dushich 2.**
- The three commands are fixed status readers sharing one 45 s budget.
- Missing facts stay `unknown`. Live run: 7/7 ok.
- In a clean clone, `DefaultRunnerTests` (2 tests) error. They import
  `lynx_wifi_v19_contact`, which needs the machine-local
  `lynx/linux-port/artifacts/busybox-wifi-ssh-twostage-v19/build-validation.json`.
  They pass on Nexus but not from a clone.

### Queues (offline, same rules as round 1)

**Banshee**

- B4: Store item 2's live DT output as a receipt under `lynx/logs/` and cite
  it in the analysis doc and forge.
- B5: USB cold-boot persistence design (offline). What would bring the mtu3
  ACM gadget up at boot? Cover an OpenRC service design, ordering against
  Wi-Fi and SSH, a local disable switch, teardown, and rollback. Add fixture
  tests for any parser or validator. No install and no live gadget change.
  Aria decides.
- B6: A catalog-ready proposal for `lynx_bluetooth_link_state`: manifest,
  wrapper, and an effect classification for Gwyn's coverage table. Do not
  add it to `local_calls` until Aria approves.

**Solo Dushich**

- D3: Make the two `DefaultRunnerTests` independent of the machine-local
  artifact: patch `ssh_command`, or skip with an explicit reason when the
  artifact is absent. Record clean-clone results (95 + 2 → 97 OK).
- D4 (continuity): Record today's new tool directories in the forge atlas,
  with owners and tags, and check them with `forge-db path check`:
  `lynx/tools/ui`, `usb`, `fingerprint`, `nfc`, `bluetooth`, `headset`,
  `flashlight`, `camera_deps`, `health`, plus the new docs.
- D5: Independent review of Gwyn's later commits: `7fe3cd8` (display
  mapping), `79e4526` (touch design), and the source-tracking fix and
  full-health test in this round.

**Gwyn**

- G4 (done this round): test for Dushich's `lynx-live-20261121-full.json`
  (7/7 ok, no unknowns).
- G5: Review B4–B6 and D3–D5 as they land.
- G6: Keep the coverage tables current as new tools are approved.

## Round 3: reviews and queues (Gwyn coordinating, 2026-11-21 ~01:05 UTC)

### Reviews

The clean clone was taken at `f33722a`, where the machine-local v19
`build-validation.json` is absent. Results:

| Suite | Result |
| --- | --- |
| health | 97 OK |
| ui | 113 OK |
| usb | 30 OK |
| bluetooth | 23 OK |
| flashlight | 9 OK |
| nfc | 5 OK |
| cancel contract | 9 OK |

`lynx_tool_manifest.py --check` passes, and `local_calls` is still 38 pairs.

| Item | Commit | Verdict |
| --- | --- | --- |
| Banshee B4: rear-flash live-DT receipt | `be4c82b` | **Accepted.** The receipt `lynx/logs/v53-live-dt-flashlight-1795222443064305946/` (`result.json`, `raw_dt.json`) exists on Nexus on the current boot `0fe847d2…`. Like other `lynx/logs` receipts it is machine-local and untracked |
| Banshee B5: USB cold-boot persistence design | `20252f6` | **Accepted as a design, with one required change (B8).** The template `usb/lynx-usb-gadget.initd` has `before sshd` (line 11). SSH is Lynx's recovery route, so a gadget start that hangs (module load, configfs, or the UDC bind at line 69) must never be able to delay it. It is not installed; Aria decides on any install |
| Banshee B6: Bluetooth link-state catalog proposal | `f33722a` | **Accepted as a proposal.** It is staged outside `local_calls` (still 38) and classified `read_only`/`radio`/`hardware/bluetooth`. Its wrapper needs an uninstalled `/usr/local/bin/lynx-bluetooth-link-state`, so installation is Aria's. The NFC SN110T citation is verified in Lynx's tree: `nfc/mt6983_vitamin_22823_sn110.dtsi`, `nq@28`, `nxp,sn-nci` |
| Dushich D3: clone-independent health tests | `6e390b9` | **Accepted.** Verified 97 OK in a clone without the artifact |
| Dushich D4: atlas continuity (21 rows) | (atlas only) | **Accepted.** His NFC-label finding was fixed in `f33722a` |
| Dushich D5: review of Gwyn's round 2 | `677ec9c` | Noted: all four items accepted |

A label that both Banshee and Gwyn missed:
`lynx/linux-port/docs/LYNX-BLUETOOTH-ATTENDED-ACCEPTANCE-TRIAL.md` still says
"11R/MT6895" (B7).

For Aria, from D5 (pre-existing, Aria's lane):
`lynx/tools/agent/deploy_native_mcp_catalog.py:18` imports
`lynx_wifi_v19_contact` at module level. Its test therefore errors in a
clean clone, for the same reason the health tests did. Fixing it is Aria's
call.

### Queues (smaller items; offline; same rules)

**Banshee**

- B7: Fix the device label in `LYNX-BLUETOOTH-ATTENDED-ACCEPTANCE-TRIAL.md`.
  Grep `lynx/` for any remaining "11R" or "MT6895", excluding review docs
  that quote them.
- B8: Revise the boot ordering in the USB design so the gadget can never
  hold up recovery:
  - start after `sshd`, or prove `start()` is bounded with explicit
    timeouts on the module load and the UDC bind;
  - update the doc and validator, and add a test that rejects
    `before sshd`.

**Solo Dushich**

- D6: Independent second review of Banshee's B5/B8 boot design, focused on
  recovery: whether any path can block or break SSH or Wi-Fi at boot, and
  whether the disable switch and rollback really work from an SSH-only
  session.
- D7: Atlas rows for the round-2 artifacts: `usb/lynx-usb-gadget.initd`,
  `bluetooth/catalog_proposal/`, the USB persistence and Bluetooth proposal
  docs, the B4 receipt, and `common/bin/lynx-board`. Mark proposals as
  "not installed".

**Gwyn**

- G7: A short "while you were out" handoff for Aria. It will list every
  review verdict, the decisions waiting on her, and the open findings.
- G8: Review B7, B8, D6 and D7.

## Round 4 (Gwyn coordinating, 2026-11-21 ~01:15 UTC)

| Item | Commit | Verdict |
| --- | --- | --- |
| Banshee B7: Bluetooth trial label | `90b4ec2` | **Accepted.** No "11R" or "MT6895" left outside review docs and mtkclient configs (clean-clone grep) |
| Banshee B8: USB boot ordering | `b81f72f` | **Ordering accepted** (`after bootmisc modules sshd`; usb 32 OK in a clean clone). **The timeouts are broken on Lynx:** see B9 |
| Dushich D6: recovery review | `130d181` | **Accepted** (M1–M4 noted). It missed the timeout syntax defect |
| Dushich D7: atlas rows | (atlas only) | **Accepted.** `forge-db path check --prefix /noobia/lynx` reports all recorded paths exist |

**Defect, verified with one read-only command on Lynx (boot `0fe847d2`):**
- Lynx's `/bin/busybox` is **v1.37.0**.
- `busybox timeout -t 1 true` → `timeout: unrecognized option: t`, rc 1.
- `busybox timeout 1 true` → rc 0.

The template's `timeout -t 5` and `timeout -t 3` calls (`lynx-usb-gadget.initd`
lines 31, 32, 35, 69 and 82) would therefore fail at once, and the gadget
would never come up. SSH would not be harmed. The validator's
substring check (M3) passed it.

### Queue

- **Banshee B9:**
  - Use the v1.37 syntax `timeout SECS PROG` (optionally `-k KILL_SECS`).
  - Make the validator parse and reject `-t`, which closes M3.
  - Fix the M1 wording and bound the M2 configfs writes.
  - Add tests, including a fixture with `-t`. Offline only.
- **Dushich D8:** Re-review B9. Check every `timeout` call against the
  BusyBox 1.37 usage quoted above.

## Round 5 queues (Gwyn coordinating; Noob asked for a larger batch)

These are offline unless stated. Work in order, one commit and one forge note
per item. Gwyn reviews, and Dushich gives a second review on Banshee's
hardware items. No phone writes, module loads, installs, radio or light
actions. Read-only live reads are allowed only behind
`--live --allow-live`.

**Banshee** (after B9):

- **B10: Main camera IMX890 bring-up preflight.**
  - From Lynx's Nord 3 source tree, map its DT node, power rails and
    sequence, C-PHY lanes, clock, VCM, and required modules.
  - Add a gated read-only collector for the current bound and unbound state.
  - Add fixtures, tests, and a doc. No module load, no capture.
- **B11: Front camera S5K3P9SP.** The same preflight as B10.
- **B12: GNSS fix-trial readiness.**
  - Write an offline checklist and a gated read-only collector: driver and
    node state, last NMEA receipt summary, and a sky-view and power gate.
  - Aria runs the trial, last.
- **B13: Headset path.** Trace the Type-C analog accessory detection in the
  Nord 3 source (accdet and Type-C mux) and explain what each switch bit
  means on this phone. Fixtures and tests for the decoder.
- **B14: NFC receipt decoder.**
  - Build an offline NCI frame parser: CORE_RESET/INIT,
    RF_DISCOVER, RF_INTF_ACTIVATED and DATA.
  - Add fixtures from the SN110 spec, so the attended tag trial produces a
    parseable, bounded receipt.
- **B15: USB serial status tool proposal.** A catalog-ready read-only tool,
  staged outside `local_calls` like B6.

**Solo Dushich** (after D8):

- **D9: Battery reserve policy evidence.**
  - Read the installed `lynx-battery-reserve` source in the repo and
    document its real thresholds and actions.
  - Compare them with the evaluator's proposed bands; label each as
    verified or proposed.
- **D10: Health report diff.** An offline tool comparing two saved
  `portable-health/1` reports: changed statuses, new unknowns, bounded
  output. Fixtures and tests. No periodic job.
- **D11: Nexus self-check.**
  - Run the portable common checks on Nexus itself, local and read-only
    (battery absent, so unknown).
  - Document what overlaps with Aigel's board. Do not edit `aigel/`.
- **D12: Second reviewer** for Banshee's B10–B15 as they land.
- **D13: Atlas hygiene.** Run `forge-db path list --prefix /noobia/lynx
  --sort hits` and `path check`. Flag stale or unused rows in a note; delete
  nothing without asking.
- **D14: Lynx tool index.**
  `lynx/linux-port/docs/LYNX-TOOL-INDEX-20261121.md`, one page listing
  every tool directory created today: owner, purpose, live or offline,
  installed or not, and its test command. Read-only on the code.
