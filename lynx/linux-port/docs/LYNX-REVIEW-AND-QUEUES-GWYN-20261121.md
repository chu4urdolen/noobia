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
