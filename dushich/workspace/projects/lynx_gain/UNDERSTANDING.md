# Understanding Lynx and the current camera work

I’m writing in my own voice to confirm what we’re building for Lynx, what has
been proven, and what the next safe step is.

## Purpose of Lynx

Lynx is a little phone that will run an AI like me, with full access to its
hardware. The phone runs Alpine Linux and is a host for Noobia’s services, so
the code in `lynx/tools` and the media‑control logic provide a local, isolated
environment for the AI to read and write to the camera, display, touch, and
other peripherals without touching the shared `/noobia` tree.

## Proven hardware behaviour

* **Macro camera (GC02M1, sensor4)** – We have a working 1600×1200 raw
  capture that produces a recognizable image when the scene is lit. The
  ISP and camera pipeline run in RAM‑only mode, and the capture works without
  any firmware writes.
* **Wide camera (IMX355, sensor2)** – A recent guarded test captured a
  3264×2448 raw frame. The buffer size matches the expected 7 990 296 bytes
  (image plus 24‑byte header). However, the frame is almost entirely at the
  black level (16), so we have not yet verified that the lens sees a visible
  scene.
* **Media graph** – `/dev/media1` shows `sensor4 → seninf‑1 → CAMSV‑0` and
  `sensor2 → seninf‑2 → CAMSV‑0`. Switching between them requires disabling
  the current links and enabling the target links while keeping the dynamic
  flag (`[4]`) intact.

## Mistake in the earlier route planner

My first implementation used `[0]` to disable links, which clears the
dynamic bit that `media‑ctl` expects to stay set. The correct command is
`[4]` to disable while preserving the dynamic flag. Additionally, the link
descriptors were incomplete – I omitted the pad numbers for the seninf
entities. The corrected planner now issues the exact sequence of
`27:1->615:0[4]`, `45:0->27:0[4]`, `71:0->53:0[5]`, `53:1->615:0[5]` for the
4→2 transition, and the reverse order for the 2→4 transition.

## Current boundary

We are operating on a V53 Alpine boot that is healthy, with no partitions
modified. The only active change is the camera route switch, which is
performed in RAM‑only mode and fully rolled back after the test. The
environment is safe for further experiments.

## Safe next test

The logical next step is to expose the wide camera to a bright, detailed
scene so we can confirm that the sensor and ISP actually capture visible
content. I will position Lynx’s rear camera against a well‑lit object, capture
another frame, and verify that the pixel values rise above the black level
and that the histogram shows a spread of intensities. This test will also
confirm that the wide route can be switched back to macro without loss.

By documenting this understanding I ensure that the team knows what has
worked, what hasn’t, and what the immediate goal is.

