# Lynx GC02M1 exposure trial, 2026-11-04

The matching OnePlus GC02M1 source initializes a 1600×1200 mode with a
1,276-line frame and a default 1,005-line shutter. `set_shutter()` writes
registers `0x03` and `0x04` and may adjust frame length via `0x41`/`0x42`.
The V4L2 adaptor registers scalar `V4L2_CID_EXPOSURE` and routes it through
`SENSOR_FEATURE_SET_ESHUTTER`; that path also notifies the frame-sync manager.
The sources are pinned in `lynx/sources/oneplus-nord3-sensor-power/SOURCE.json`.
Lynx's sysfs reports the sensor's runtime power status as `unsupported`.
Therefore an ioctl success alone is insufficient evidence that the shutter
changed or that the path is compatible with this CAMSV capture route.

The bounded helper sent only `VIDIOC_S_CTRL` (`0xc008561c`) for scalar
exposure (`0x00980911`), after stream-on. It did **not** use the vendor
`G_EXT_CTRLS` path that previously crashed the kernel. The ioctl code and
8-byte structure were checked against local Linux headers. All trials used
the same V53 boot ID `fa2ee038-c248-498d-8343-2e39a2395c71`, RAM-loaded
camera modules, a 55-second reboot watchdog, IRQ and power monitoring,
firmware-path restoration, and post-trial Alpine health checks. No partition
was written.

| Capture | Exposure | CAMSV1 IRQ growth | Result |
| --- | --- | ---: | --- |
| `logs/camera-camsv-frame-1793798481425521319` | 3,000 lines | 0 | ioctl returned success; no frame in 9 seconds |
| `logs/camera-camsv-frame-1793798548465677612` | unchanged | 22 | 1,920,000-byte frame captured |
| `logs/camera-camsv-frame-1793798590048893390` | 1,200 lines | 0 | ioctl returned success; no frame in 9 seconds |

The unchanged capture between the two modified trials demonstrates that the
camera pipeline could still deliver frames on this boot. Both exposure trials
streamed and queued a request, then timed out without a CAMSV frame interrupt.
All recorded Alpine health samples had no service issues; sensor power rails
returned to disabled and the temporary firmware path returned to
`/vendor/firmware`. This establishes a repeatable association between the
standalone exposure write and a stalled frame. It does not establish whether
the culprit is the sensor shutter write, frame-sync notification, runtime PM,
or a request-order interaction.

The host trial now refuses `--exposure-lines` so this unsuccessful path is not
repeated accidentally. Keep the working no-control capture as the baseline.

The matching ISP source provides a request-scoped path: the CAMSV branch in
`mtk_cam.c` finds a sensor control object attached to the media request, and
`mtk_cam-ctrl.c` calls `v4l2_ctrl_request_setup()` for that sensor. The host
prepared a separate `VIDIOC_S_EXT_CTRLS` request-value helper using a single
scalar exposure control. Its ioctl number, structure sizes, and member
offsets matched C headers. The guarded 1,200-line request at
`logs/camera-camsv-frame-1793798862992366602/result.json` **did** return
a complete 1,920,000-byte frame, with 22 CAMSV1 interrupts and 18 healthy
monitor samples. Cleanup restored the firmware path and disarmed the
watchdog. The rear cluster was still covered during this frame, so its
near-constant `0x10` pixels cannot establish whether the requested exposure
was applied. Compare an unchanged and request-exposure capture in the same
well-lit scene before claiming brighter imaging. A single frame may precede
the exposure change because the ISP applies controls in a frame request;
that timing also requires checking.

Noob then turned Lynx so the rear cluster was uncovered. A no-control
single frame at `logs/camera-camsv-frame-1793799135748391984/result.json`
had mean 17.362 (range 15–21). The first attempt to run the matching
request-exposure trial stopped at the initial SSH boot-ID read after a
connection timeout; it did not reach the phone's camera. SSH returned on
the same boot ID with no health issues.

The retried 1,200-line request captured a frame at
`logs/camera-camsv-frame-1793799225475744544/result.json`, mean 17.305
(range 15–21). That single frame is too similar to the baseline to prove
an exposure effect. The ISP's request-time control setup may apply after
the first frame's sensor exposure has begun.

A two-frame helper was then run on the same V53 boot with a 3,000-line
exposure attached to its **first** media request. It reused one DMA buffer
for the second request without a direct sensor-control write. Receipt:
`logs/camera-camsv-frame-1793799404470911909/result.json`. Both frames
completed in one stream, sequences 1 and 2, with 24 CAMSV1 interrupts.
The first frame had mean 17.254 (range 14–21); the second had mean 19.034
(range 15–29). Every one of sixteen 400×300 regions became brighter by
0.917–3.072 raw units. This is evidence that the request control takes
effect on a subsequent frame. It is not a calibrated shutter-time or
colorimetry measurement.

The raw frame remains severely underexposed, but an automatic diagnostic
contrast stretch of the second RGB preview reveals a recognizable room
scene. It also magnifies noise and does not repair the raw exposure. Preview:
`logs/camera-camsv-frame-1793799404470911909/sensor4-preview-diagnostic-contrast.png`.
The decoder now saves that view alongside the unaltered raw payload and
ordinary preview. Post-trial Alpine SSH, V53 boot ID, 45% battery, normal
temperature, and `/vendor/firmware` search path were verified. No camera
module was installed for automatic boot and no partition was written.

To repeat on an already prepared boot, check the live boot ID and health,
ensure the corrected ISP module and sensor4 → CAMSV route are still in RAM,
then use `tools/trial_camera_camsv_frame.py --attended --boot-id <live-id>
--two-frame-request-exposure-lines 3000`. The host tool checks the earlier
stable ISP receipt for that boot, the route, battery, temperature, and IRQs
before streaming. If Lynx has rebooted, reload and reverify the camera
modules and route first; the RAM state does not survive reboot. Do not use
the blocked standalone `--exposure-lines` path or control enumeration.

## Gain request prepared with Dushich

Dushich's separate local Codex/Ollama workshop implemented an offline
`gain_mapper()` and `pack_stagger_ae()` in his own Git workspace. Verified
commits `2268cc0` and `52a2f81` passed 5 and then 9 independent unit tests;
Aria inspected both diffs and reran the tests. The gain mapper reflects the
matching source ranges: the V4L2 analogue-gain control exposes 64–768 while
GC02M1's raw `set_gain()` clamps to 1024–12288. A factor of 16 maps both
endpoints, but that mapping alone does not prove the actual camera response.
The vendor `mtk_hdr_ae` structure is 13 little-endian 32-bit words (52 bytes):
five exposure values, five gain values, actions, subsample tags, and request
ID. The vendor AE control ID `0x00981bdf` and 52-byte layout were checked
against pinned OnePlus headers and a compiled C ABI check. The helper uses
the same encoding tested by Dushich and records his commit in its source.

A guarded two-frame request with exposure 3,000 lines and raw gain 2,048
(nominal 2×) succeeded at
`logs/camera-camsv-frame-1793826256937866992/result.json`. Both frames
completed, CAMSV1 IRQ grew by 24, and all 18 health samples reported no
issues. The kernel log in
`logs/camera-health-window-1793826260500302344/sample-004.txt` explicitly
reported `sensor_idx 4`, exposure 3000, and analogue gain 2048 through the
vendor AE path. Lynx remained on the same V53 boot with 74% battery, normal
temperature, and restored `/vendor/firmware` search path. The scene was
nearly black (first mean 16.0019, second mean 16.0232), so this confirms
control delivery and continued frame capture, **not** a measured optical
gain improvement. Repeat the bounded comparison with the rear lens uncovered
and a fixed lit scene before claiming usable gain.

## Lit-scene gain comparison

With the rear cluster uncovered and Lynx stationary, two guarded two-frame
captures used the same 3,000-line exposure. The first requested raw gain
1,024 (nominal 1×) and the second requested 2,048 (nominal 2×). Both
captures completed on the same V53 boot, with no partition writes. Receipts:
`logs/camera-camsv-frame-1793826395269987446/result.json` and
`logs/camera-camsv-frame-1793826453817967816/result.json`.

| Raw gain | First frame mean | Second frame mean | Second frame range |
| ---: | ---: | ---: | ---: |
| 1,024 | 16.4964 | 17.2395 | 15–29 |
| 2,048 | 16.4942 | 18.3075 | 14–40 |

The almost identical first frames support a stable scene and confirm the
request acts later in the stream. With black level 16 and positive values
clipped before averaging, the second-frame signal is 1.8616× higher at the
nominal 2× setting. All sixteen 400×300 regions brightened, by 0.31–1.94
raw units. The reproducible analysis is in
`logs/camera-gain-20261104-comparison.json`, with the first-frame baseline in
`logs/camera-gain-20261104-first-frame-baseline.json`. The offline comparison
tool was built by Dushich in commit `32946dc`, reviewed, and copied to
`tools/compare_camera_frames.py`. This establishes a real gain response for
GC02M1, although the image remains dark and uncalibrated. It does not prove
the requested numerical gain equals the sensor's optical gain exactly.

## Color phase and current boot

Dushich's separately verified Bayer channel analyzer (commit `2e22a39`, 14
passing workspace tests) was adopted as `tools/bayer_channel_stats.py` and
run on the saved frames. In the nominal 2× second frame, the four pixel-class
means were 18.6303, 18.7059, 18.6191, and 17.2746 in top-left, top-right,
bottom-left, and bottom-right order. The corresponding untouched first-frame
means matched the nominal 1× trial within 0.004 raw units. The statistics are
saved in `logs/camera-gain-20261104-bayer-channels.json`.

The matching GC02M1 source declares `SENSOR_OUTPUT_FORMAT_RAW_R`, mapped by
the adaptor to `SRGGB10_1X10`. The generic CAMSV graph reports `SBGGR10_1X10`
and our capture accepts `BA81`. Those observations conflict on the top-left
color, so the earlier BGGR previews are provisional. `tools/decode_camera_bayer.py`
now accepts an explicit Bayer phase. The default was BGGR for the earlier
receipts. Both interpretations were generated from the same saved 2×
frame; the RGGB diagnostic preview is under
`logs/camera-camsv-frame-1793826453817967816/rggb-interpretation/`.
Neither preview is color-calibrated. A known color target or trustworthy sensor
subdevice format is needed before choosing the phase for a camera service.

On 2026-11-05 Lynx was reachable via authenticated Alpine SSH on port 2222,
boot ID `25360b8f-e99c-404c-b295-4535f8c5e47a`. `lynx-status --assert-ready`
reported no issues, 100% battery, 27.6°C battery temperature, and normal
thermal values. This is a newer boot, so the camera modules and route from
the gain trials were no longer loaded. At that checkpoint, no camera operation
had yet run on this boot.

## 2026-11-05 bright-scene trial and cleanup

Noob placed a red cable and blue soldering helper in front of Lynx. On V53
boot `25360b8f-e99c-404c-b295-4535f8c5e47a`, the stock camera prefix and
reviewed pipeline prefix loaded in RAM, the patched ISP passed its 35-second
health/IRQ window, and the sensor4 → CAMSV route linked. Receipts:
`logs/camera-ram-1793889844740241430/result.json`,
`logs/camera-pipeline-1793889869623123493/result.json`,
`logs/camera-isp-patched-trial-1793889917646211444/result.json`, and
`logs/camera-camsv-route-1793889974051275863.json`.

The bounded two-frame request at
`logs/camera-camsv-frame-1793889986606306247/result.json` applied 3,000
exposure lines and raw gain 2,048. Its helper reported two complete 1,920,000
byte frames, sequence numbers 1 and 2, and clean stream-off. CAMSV1 IRQ grew
by 24; YUV-B stayed zero. The second frame mean was 38.356 (range 0–255),
up from 21.584 in the first frame. It contains recognizable scene geometry
without a diagnostic contrast stretch; both Bayer interpretations were saved
under that receipt's `bggr-interpretation/` and `rggb-interpretation/` dirs.
The saved kernel stream at `logs/kernel-trial-1793889990692154584/kernel.kmsg`
identifies `gc02m1_mipi_raw_22823`, records sensor4's 3,000-line exposure and
raw gain 2,048 request, and has no
Oops or RCU-stall match in the capture window.
The view shows bright lamps and a monitor; the red cable and blue helper are
not clearly identifiable, so this frame does not settle the color phase.

The host trial reported `failed_watchdog_armed` because its single immediate
post-capture `lynx-status --assert-ready` saw `service_lynx-health` false.
The independent 16-sample health/IRQ monitor recorded no issues, and a live
health check seconds later passed on the same boot. Aria restored the global
firmware path to `/vendor/firmware`, disarmed watchdog PID 31922, verified the
phone healthy and reachable, and retrieved both frame files read-only. The
original failure receipt was preserved; the cleanup and frame hashes are in
`logs/camera-camsv-frame-1793889986606306247/manual-recovery.json`.
No partition was written and no additional camera stream was attempted.

The host trial now allows one delayed health retry and, on any post-stream
error while the same boot remains reachable and healthy, restores the firmware
path and disarms the watchdog before returning failure. The modified path is
compiled and diff-checked but has not yet had a live regression trial.

## 2026-11-05 color-target retry

After Noob adjusted Lynx's view, a second bounded request capture completed
cleanly on the same V53 boot. Receipt:
`logs/camera-camsv-frame-1793895847755492267/result.json`. The helper
captured both 1,920,000-byte frames and stopped streaming; the host restored
`/vendor/firmware`, disarmed its watchdog, saved both frames, and reported
`frame_captured`. `lynx-status --assert-ready` passed after capture with 90%
battery and no issues. This also exercised the corrected cleanup path on a
normal success, though not its new error branch.

The first frame mean was 20.383 and the second 32.711 (range 15–255). The
ordinary RGB preview now shows a large curved object at the left and a
segmented object at the right. In the RGGB interpretation the left object
appears red-orange, while the BGGR interpretation makes it blue. That agrees
with Noob's red cable description and with the matching GC02M1 source's
`RAW_R` declaration. The live media graph also reported `SRGGB10_1X10` on
the enabled seninf-1 source pad, although its sink and CAMSV pad still showed
generic `SBGGR10_1X10` and the sensor pad format printed `unknown`. The two
previews are saved in the capture receipt and its `rggb-interpretation/` dir.
This is strong evidence for RGGB; color calibration and the identity of the
physical lens still require validation.

Dushich independently added a bounded Bayer ROI analyzer in his workspace
(verified commit `91367f6`, 22 passing tests). Aria reviewed it, adopted it as
`tools/roi_bayer_channels.py`, and saved an offline measurement in
`logs/camera-camsv-frame-1793895847755492267/color-roi-analysis.json`.
The approximate left curved-object region (x 30–300, y 100–550) has RGGB
red mean 25.23 and blue mean 19.03, a red-minus-blue difference of +6.20
raw units. The equivalent BGGR interpretation swaps those two channels.
This supports the visual red-cable inference but does not substitute for a
confirmed object location or a calibrated color target.
The offline decoder now defaults to RGGB for future captures and retains
`--bayer-phase bggr` to reproduce the older interpretation. Existing frame
bytes and previews were not rewritten.
Noob subsequently confirmed that the large curved object at the left of the
new preview is the red cable. This confirms RGGB as the useful color phase
for the current GC02M1 route; a color calibration matrix is still needed for
accurate colors.

The host-side decoder now also writes a reversible display preview using a
black-level-16, gain-3, gamma-1.8 LUT. Dushich implemented and independently
tested the pure LUT in commit `ceeccc5` (26 workspace tests); Aria reviewed it
and added it to the decoder. The new preview is
`logs/camera-camsv-frame-1793895847755492267/rggb-lifted-g3-g1p8/sensor4-preview-lifted.png`.
It improves visibility without changing the 8-bit raw payload or claiming
sensor color calibration. Future host capture decodes will save a
`sensor4-preview-lifted.png` automatically with parameters in the frame's
statistics JSON.
Dushich also supplied a pure raw-frame quality analyzer (verified commit
`66649a6`, 30 workspace tests). It is adopted as
`tools/camera_frame_quality.py` and now contributes percentile and clipping
metrics to future decoder receipts. For the confirmed red-cable second frame,
the raw median was 24, p95 was 69, and 1.01% of pixels were at least 250.
Those values explain why the scene appears dark before preview lifting while
the lamps already clip; they do not imply calibrated exposure.
