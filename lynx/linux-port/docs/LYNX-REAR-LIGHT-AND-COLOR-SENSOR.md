# Lynx's two pale rear circles

OnePlus lists one LED flash and a separate rear color temperature sensor for
the Nord 3 5G: https://www.oneplus.in/nord-3-5g/specs . The second pale circle
is the rear optical sensor, not a second light. A controlled cover/uncover
check on Lynx confirmed the lower pale circle's response on 2026-11-15.

The CPH2493 stock device tree contains one `lm3642@63/flash@0` child. Lynx's
loaded LM3642 driver binds I2C `6-0063`. The matching stock driver source
declares LED0 and LED1 V4L2 labels, but its brightness definitions share
register `0x09`, its enable routine uses the same mode bits for either label,
and only channel 0 is registered by this device tree. Those labels do not
establish a second independent lamp. Do not address an unregistered channel
or write the chip directly merely because the case shows two pale circles.

The bounded `FLASH_PULSE` command lit the rear LED visibly for Noob and
verified OFF. On the current V53 boot, `FLASH_STATUS` returns `value=1`,
`validated=1`, `driver_bound=1`.
Noob confirmed that only one of the two pale circles flashed during that
physical observation. This is consistent with the one-flash device tree and
OnePlus's flash-plus-sensor specification.

The rear optical driver is already registered as `tcs3408 als`. The distinct
read-only NRP/1 calls `LIGHT_STATUS` (372) and `LIGHT_RAW` (373) returned
`registered=1` and `value=0 raw1=0 raw2=0 gain=1` on 2026-11-02. A zero raw
sample in an unknown lighting condition does not validate the optical
response or identify which rear circle covers the sensor. When Noob is at
Lynx, compare uncovered and covered readings under steady ambient light.

The read-only recorder `tools/record_rear_light_response.py` captured 26
samples over 30 seconds at
`logs/rear-light-response-1793637128297070135/result.json`. The reported
value ranged from 0 to 1,333 and rose sharply only near the end. Noob had
to turn on a lamp during the recording, so this run cannot identify a
cover/uncover response. Repeat with the lamp already aimed at the lower
circle, taking separate lit, covered, and uncovered readings at Noob's pace.

The later stepwise NRP/1 check used Noob's cues. With the lamp aimed at the
uncovered lower circle, `LIGHT_RAW` returned 62. When Noob reported it
covered, the value was 7. After Noob reported it uncovered, two reads both
returned 0. The lamp position/intensity was not verified at that last step,
so the sequence is **inconclusive** for physical identification. It does
show that the `tcs3408 als` numeric channel can vary; the earlier 30-second
recording reached 1,333 near the end after the lamp was turned on. Do not
mark the rear optical sensor as physically validated from this earlier trial
alone. The later controlled trial below supplied that repeatable sequence.

For the repeat, keep a lamp fixed on the lower pale circle and use
`tools/trial_rear_light_stepwise.py`. It records five authenticated, read-only
`LIGHT_RAW` samples per cued phase, with separate `lit`, `covered`, and
`relit` JSON files under one private `logs/rear-light-stepwise-*` directory.
Run `lit` only after the lamp is steady, then pass its printed session path
with `--session` for `covered` and `relit`. Compare the three medians; a
repeatable drop and recovery is needed before identifying the circle.

## 2026-11-15 controlled optical response

Noob held a steady lamp on the lower pale rear circle and cued each phase.
The five `LIGHT_RAW` values were 271, 221, 353, 370, 391 with the circle
uncovered (median 353); 0, 0, 0, 0, 0 while covered (median 0); and 122,
122, 251, 244, 242 after uncovering (median 242). This repeatable
lit–covered–lit response validates that the lower pale circle exposes the
rear optical sensor. It does not establish calibrated lux or color
temperature measurements. All calls were read-only; no flash, reboot, or
partition change occurred. Raw receipt:
`logs/rear-light-stepwise-1794774791703875833/`.

## 2026-11-15 RAM bind on the current boot

On boot `0aa70b0f-1449-43e7-acf5-1bb5680c2a0f`, the guarded
`load_flashlight_ram.py` path verified the exact V53 image and matching
module hashes, then loaded `mtk_battery_oc_throttling`, `flashlight`, and
`lm3642_22823` in RAM. The LM3642 bound at I2C `6-0063`; authenticated
`FLASH_STATUS` returned `interface_ready=1 validated=1 driver_bound=1`.
Alpine health remained clear at 70% battery. No LED pulse, module unload,
partition write, or reboot was requested. Receipt:
`logs/flashlight-ram-1794772075897832322/result.json`. This bind lasts only
for the current boot; automatic loading remains a separate gate.

Noob watched an authenticated `FLASH_PULSE 100` on the same boot and reported
seeing the small rear light. The NRP response reported `duration_ms=100` and
`off_verified=1`; a separate local `--off` command again returned
`off_verified=true`. `FLASH_STATUS` stayed ready and Alpine health stayed
clear at 71% battery. This confirms one short visible LED pulse on this boot,
not a second independently controllable lamp.
