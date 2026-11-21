# Lynx's first live test: a real picture, seen by Lynx, understood by Aigel

Gwyn, 2026-11-21. Approved by Noob as **C1**: attended. Aria runs the camera,
Noob shows Lynx detectable pictures, and Gwyn runs the checks. Background:
`LYNX-CAMERA-FOR-SENSES-SPEC-20261121.md`; contract
`common/autonomy/ARCHITECTURE.md`.

## What must be true before the day (all installed from reviewed packets)

| # | Piece | Where | Check |
| --- | --- | --- | --- |
| 1 | I-2: Lynx keeps notice-level sense lines | Lynx | **done** (IS-1a, forge lynx #296) |
| 2 | **A real detector** on Nexus `:5050`, a CPU model with COCO labels | Nexus | `curl -s 127.0.0.1:5050/health` shows `"model": true`, and a fixture cat image comes back as `cat` |
| 3 | Aigel's service on `:112` with Lynx in its host registry | Nexus | `curl -s 127.0.0.1:112/api/v1/status` lists `lynx` |
| 4 | G3 brain config: Lynx thinks with Qwen | Lynx | the packet's end-to-end verify: an agent job answers with her battery level |
| 5 | IS-2: `noobia-autonomyd` with the Lynx adapter, running | Lynx | `noobia-autonomyd --check` is ok; the packet's sense test line appears in Aigel's status |
| 6 | C1 wrapper: one captured frame → `:5050` → `NOOBIA P1 camera object.seen label=… conf=…` | Nexus (runs the trial) | dry-run on a fixture image emits a correct sense line |
| 7 | Health | Lynx | battery ≥ 35 %, temperatures under the camera trial gates, `lynx-board` fresh |

The detector must be real (row 2). A detector that invents labels would make
the test meaningless, and before 2026-11-21 it did exactly that (forge
autonomy #297).

## Pictures Noob can show (COCO labels the detector knows)

Large, well-lit, filling most of the frame, one subject at a time:
1. **cat**;
2. **dog**;
3. **cup**;
4. **person**, Noob himself.

Show each for about 20 s. Between pictures, show a blank wall, which should
be detected as nothing.

## The test (about 20 minutes)

1. **Baseline.** Gwyn runs `lynx-board` and opens Aigel's page
   (`http://192.168.100.106:112/`). Note Lynx's queue and the last decision.
2. **Aria** runs Stage A (patched ISP, 35 s stability) and confirms the
   receipt.
3. Noob shows the **cat**.
4. **Aria** runs Stage B, one frame, with the reboot net armed. The C1
   wrapper sends the frame to `:5050`.
5. **Expected trail, each hop checked by Gwyn:**
   - the wrapper prints the detection, e.g. `cat 0.8x`, and the sense line
     it emitted;
   - Lynx's `/var/log/lynx/messages` has the `noobia-sense` line, which is a
     single named file read;
   - `noobia-autonomyd` closes a PRIORITY chunk. On first sight no pattern
     exists, so the chunk goes to Aigel. Her page shows `lynx`, `priority`,
     the evidence line, and her decision;
   - Aigel answers `message`, for example "A cat appeared in front of you",
     and possibly proposes a pattern;
   - the Lynx adapter queues a job, which shows as one new pending job, then
     a running one;
   - Lynx's agent thinks with Qwen (about 20–40 s) and **acts with her own
     tools**: an image, a sound, the flashlight or haptics, or chooses to do
     nothing. Her audit log records it, in the `noobia-agent` view.
6. Repeat with the **dog**, then the **cup**. If Aigel proposed a cat
   pattern, show the **cat** again. It should now be explained by the ranker
   **without** an LLM call: no new request on Aigel's page, and the message
   comes from `ranker`.
7. Show the **blank wall**: no object, so no sense line or only a `P0` one,
   and no message.

## Success means

- At least one real frame produced the right label, and that label reached
  Lynx as a message she acted on, or chose not to, through the full chain.
- The second sight of a learned thing went through the ranker, with no Aigel
  call.
- Nothing invented: a blank wall produced no "object.seen".
- Every hop is visible in the logs and on the pages above.

## Stop and recovery

- Stop any autonomy at once on Lynx with
  `touch /etc/noobia/autonomy.disable`. Nexus is unaffected.
- The camera trial's own 55 s reboot net and the IRQ guard stay as they are.
- Commands on Lynx are single named reads only. **Never** run anything
  recursive (`lynx/AGENTS.md`).
- Everything installed for the test has its packet's rollback.
