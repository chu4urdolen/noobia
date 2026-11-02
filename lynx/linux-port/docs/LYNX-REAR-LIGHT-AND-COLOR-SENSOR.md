# Lynx's two pale rear circles

OnePlus lists one LED flash and a separate rear color temperature sensor for
the Nord 3 5G: https://www.oneplus.in/nord-3-5g/specs . The second pale circle
is therefore likely the optical sensor, not a second light. Its exact physical
position on Lynx still needs a simple cover/uncover check.

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
