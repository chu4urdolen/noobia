# Shared context for Dushich handoffs

This is Aria's durable, human-readable context for Dushich. Update it when a
decision matters beyond one task. The bridge attaches it to each handoff along
with recent visible conversation, Noobia's project instructions, and the code
map. Task-specific files still need explicit `--include` or MCP `files` entries.

## Working relationship

Noob and Aria work in the main Codex conversation. Dushich works quietly in a
separate local Codex CLI session using Ollama `qwen3.8:27b` on Nexus. He has his
own Codex home, task workspace, Git history, instructions, and session history
under the shared `aria` Unix account.
He may implement, run tests, debug, and commit a bounded task in his workspace.
The handoff runner checks tool use, changed files, tests, and a clean commit.
When a task fails verification or needs a decision, report the blocker to Aria.
Aria and Noob can inspect the exact task brief and full event log if needed.

## Boundaries

Dushich's interactive helper and solo sessions start at `/noobia`. The verified
coding runner uses `/noobia/dushich/workspace`, a small clean task repository.
The project source tree is `/noobia`; its code map is
`/noobia/docs/CODE-MAP.md`. A Dushich commit in his
workspace does not automatically change shared Noobia code or deploy to a
device. Aria reviews relevant code before adopting it. Inference stays local;
the launcher pins Ollama and refuses unavailable local inference.

The context packet contains visible user and Aria text plus bounded excerpts of
recent visible tool calls and results, not private reasoning. Older material may
be omitted to fit the local model's context.
This document records decisions that should survive such trimming.

## Current coordination decisions

- Lynx is on V53 Alpine at `192.168.100.107`; port 22 reaches the BusyBox
  rescue shell and port 2222 reaches Alpine. Check the live boot ID before
  treating RAM-loaded camera modules as present.
- The GC02M1 camera has returned guarded 1600×1200 raw frames. A request-scoped
  AE payload with exposure 3,000 lines and raw gain 2,048 produced 1.8616×
  more positive signal than gain 1,024 in a stable lit scene. This is a camera
  trial result, not a calibrated color or full camera service.
- Dushich's offline Bayer channel statistics task passed verification in commit
  `2e22a39` and was adopted as `lynx/tools/bayer_channel_stats.py`. Matching
  sensor source declares `SENSOR_OUTPUT_FORMAT_RAW_R` while our capture node
  negotiates `BA81`; the correct color phase remains unverified. Offline
  previews now support both BGGR and RGGB interpretations. A follow-up in
  commit `3374ce3` added phase selection to his stats helper, passed 16 tests,
  and was adopted without its workspace-only import shim.
- On 2026-11-05, an attended bright-scene sensor4 trial on V53 boot
  `25360b8f-e99c-404c-b295-4535f8c5e47a` captured two raw frames with
  exposure 3,000 lines/gain 2,048. Mean pixel level rose from 21.584 to
  38.356; recognizable monitor/lights appeared. The red cable and blue helper
  were not identifiable, so Bayer phase is still open. The immediate host
  health check briefly saw `lynx-health` false while the independent monitor
  had 16 healthy samples. Aria restored `/vendor/firmware`, disarmed the
  watchdog, confirmed health, and saved both frames. See
  `lynx/linux-port/docs/CAMERA-EXPOSURE-20261104.md` for receipts. The trial
  tool now retries health once and cleans up on a reachable healthy boot;
  this change awaits a live regression trial.
- A later attended capture on the same boot passed cleanly. The second raw
  frame mean was 32.711 and showed a curved likely red cable and segmented
  helper. Matching sensor source, live seninf output, and an offline ROI red
  minus blue difference of +6.20 favor RGGB. The decoder now defaults to
  RGGB, with BGGR selectable. Dushich's ROI tool passed 22 tests in verified
  commit `91367f6`; Aria adopted it as `lynx/tools/roi_bayer_channels.py`.
- Noob confirmed the curved object is the red cable. A new host-side
  `lynx/tools/prepare_camera_camsv.py` provides read-only route status and an
  attended RAM-only bring-up sequence after future reboots; current status
  reports `already_prepared`. Dushich's LUT and frame-quality utilities passed
  26 and 30 workspace tests (commits `ceeccc5`, `66649a6`). They are adopted
  in the host-side raw decoder, which now saves a brighter preview and raw
  quality metrics without modifying Lynx or the original Bayer bytes.
- The matching stock kernel identified sensor0 as IMX890 `_21871`, sensor1 as
  S5K3P9SP `_22823`, sensor2 as IMX355 `_22823`, and sensor4 as GC02M1
  `_22823`. Their pinned source is now in
  `lynx/sources/oneplus-nord3-sensor-power/`. IMX890 and S5K3P9SP use
  four-cell Bayer modes, so IMX355 wide camera is the next simpler capture
  target. Dushich's frame-geometry calculator passed 36 tests (commit
  `369aca5`) in his workspace but has not been integrated into the live
  capture path: the 24-byte header is measured only for sensor4.
- Dushich route-planning task `20261105T165126Z-8c39a783` passed its runner,
  but its output used incomplete media link descriptors and `[0]` to disable
  dynamic links. Lynx's `media-ctl` rejects `[0]`; the valid disable flag is
  `[4]`. Aria reviewed the diff, did not adopt the code, and wrote the exact
  route tool under `lynx/tools/`. Guarded RAM-only route switches to sensor2
  IMX355 and back to sensor4 succeeded on V53 boot
  `25360b8f-e99c-404c-b295-4535f8c5e47a`. IMX355 3264×2448 BA81
  reported `sizeimage=7990296`; one frame delivered 7,990,272 raw bytes,
  sequence 1, clean STREAMOFF. The frame is nearly black, so scene validation
  is pending. The host tool mistakenly flagged format restoration by reading
  empty setter stdout; read-only verification showed the original 1600×1200
  BA81 format, macro route, `/vendor/firmware`, healthy Alpine, and YUV-B IRQ
  zero. The host check is corrected for the next trial. Receipts are in
  `lynx/logs/camera-wide-format-1793897952473287594/` and
  `lynx/logs/camera-wide-frame-1793898116331141692/`.
- Noob explicitly describes Lynx as a little phone intended to house an AI
  inhabitant like Dushich, able to use her hardware. Dushich receives bounded
  snapshots of this visible Aria/Noob conversation through the bridge, not a
  continuous live chat. Treat his own conclusions as contributions to review,
  and give him meaningful, independent tasks with enough context. On
  2026-11-06, he independently recommended a bright-scene wide-camera test;
  his first analysis mixed macro AE settings into the wide trial and confused
  sensor MIPI RAW10 with the 8-bit BA81 capture payload. The follow-up fixed
  the major format and AE claims, though the analysis still overstates what
  the dark frame proves. The sole wide raw payload remains nearly all 16;
  its parity means are all approximately 16.01. No optical scene has been
  validated. Wait for Noob to uncover and point the rear lenses at a bright
  detailed scene before the next guarded wide capture.
- Noob did so on 2026-11-06. The next guarded IMX355 wide trial captured a
  recognizable 3264×2448 image of the monitor/work surface/lights. Positive
  signal rose from 0.0119 to 2.3965 above black level, about 201×, proving
  scene-dependent response on the wide optical route. RGGB is an initial
  preview interpretation, not yet a color-target validation for IMX355.
  Trial receipt `lynx/logs/camera-wide-frame-1793970498449657635/result.json`;
  macro route, 1600×1200 BA81, and firmware path were restored. No partition
  writes. Next focus: distinguish boot image/kernel changes from loadable
  modules and Alpine services before planning another flash; build a Lynx AI
  agent with one shared tool registry for local and Noobia remote calls.

- Prefer small, clearly bounded tasks with an expected file and independent
  test command.
- Keep Dushich's working steps and event stream in his private task log. Return
  a concise final report or a concrete blocker.
- Continue a Dushich Codex thread for related follow-up tasks so local context
  and debugging history remain available. The bridge does this automatically
  within each Aria conversation; a new Aria conversation starts a new thread.
- Send relevant source and design files explicitly when they are outside his
  workspace or central to the task.
- 2026-11-14: Dushich has a separate **solo** Codex terminal at
  `/noobia/dushich/solo/launch`. Solo conversation IDs are registered separately; Aria/Banshee
  handoff threads stay in their paired panels. Noob later granted the solo
  terminal Aria-level host permissions; it now runs under Aria's Unix account
  with a separate Codex home and Full Access. Delegated tasks now have full
  Codex access and passwordless sudo under the `dushich` account. Both paths use
  the local Ollama model. His candidate
  transcript parser in `projects/solo_dashboard/` passed its own tests but
  was not adopted into the dashboard because it still filtered text by a
  `Thinking` prefix; the dashboard filters by record type and role instead.
