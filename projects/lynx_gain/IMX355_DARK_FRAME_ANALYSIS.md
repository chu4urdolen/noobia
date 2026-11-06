# IMX355 Dark Frame Analysis

## Evidence

* The raw frame captured from the IMX355 (sensor2) in the guarded wide‑camera
  test was **3264×2448** pixels, 7 990 296 bytes total, including a 24‑byte
  header.  The pixel histogram shows **98.8 % of samples at the black level
  (16)**, with a mean of 16.01 and a 95th percentile also at 16.
* The kernel trace during the capture contains the expected media‑bus path
  `imgsensor 2‑001a frame desc VC0 datatype0x2b 3264x2448` and a normal
  stream‑off sequence.  No error or warning about frame format or size is
  reported besides the usual `media bus code mismatch` warnings that appear in
  macro captures.
* The capture node negotiated the `BA81` format (RAW R), which matches the
  32‑bit per‑pixel raw stream expected for IMX355.  No runtime error or
  format mismatch is seen.
* The buffer statistics show **7,894,345 bytes at value 16**, **94,279 bytes at
  17**, and a negligible number at 15, confirming a flat‑black distribution.

## Competing Hypotheses (ranked by evidence)

1. **Lens/Optics not illuminated** – The sensor is functioning, but the
   optical path is dark because the lens is not pointed at a visible scene
   or the light level is too low.  This explains the flat histogram and
   matches the kernel trace that shows a normal stream.
2. **Incorrect exposure or gain settings** – The AE request used 3000 lines
   and a raw gain of 2048, but the ISP may be overriding or clipping the
   exposure.  The mean of 16 indicates the gain is not applied.
3. **ISP pipeline mis‑configured** – The sensor data passes through the
   ISP but the ISP may be outputting a black frame due to a missing or
   mis‑enabled output node.  The trace shows `seninf CSI port 2` and a
   successful stream‑off, but no evidence of an ISP error.
4. **Camera driver bug** – The driver could be incorrectly handling the
   raw stream, sending a zeroed buffer.  The lack of kernel errors makes this
   less likely.

## Unknowns

* Is the sensor actually receiving sufficient light?  We have no direct
   measurement of the optical scene.
* Are the exposure and gain registers correctly set in the sensor?  The
   current test does not read back the sensor registers.
* Does the ISP pipeline have the correct output node enabled for RAW
   capture?  We cannot confirm from the kernel logs.

## Safest Discriminating Next Test

Perform a **bright‑scene capture**: place Lynx on a well‑lit object (e.g., a
white card or a brightly lit table) and capture another wide‑camera frame.
Validate that the histogram shows a spread of values and that the mean is
well above 16.  This test directly addresses the top‑ranked hypothesis and
provides the simplest confirmation of optical illumination.

If the bright‑scene frame is still flat, the next step is to read back the
exposure/gain registers and verify the ISP output node.  But the bright‑scene
capture is the lowest‑effort discriminant.

