# Lynx delayed audio and sensor startup

On boot `d629cc73-aa6d-4aec-808b-8a374740e203`, OpenRC's `lynx-audio`
failed and `lynx-sensorhub` then stopped because it needs audio. The first
persistent power sample on that boot was 22% at uptime 214 seconds; the audio
failure was logged near uptime 247 seconds. Audio's own loader requires at
least 25% while charging, or 50% otherwise. The failed loader log was
overwritten when a later manual start succeeded, so the exact rejected check
is inferred from the time, battery record, and source gate.

After the battery charged, both existing services started without a reboot.
The bounded local magnetometer sample and authenticated NRP/1 calls passed on
the same boot. Their separate safety checks and module hash gates remain in
the service bootstraps.

`lynx/tools/lynx_sensor_retry.py` and `lynx_sensor_retry_policy.py` now
provide a delayed retry. The OpenRC unit `lynx-sensor-retry` is in the default
runlevel. It reads the gauge and SoC temperature, requires a healthy Lynx,
and waits for the exact audio bootstrap charge and temperature gates. It
starts audio first, then sensorhub, only through their existing OpenRC
services. It tries at most three times after a service start failure, with
five minutes between failed attempts. It neither writes charger controls nor
requests shutdown, reboot, or a partition change. After success it stays
idle so OpenRC reports it as running; manually stopping it leaves audio and
sensorhub alone.

The first live install receipt is
`lynx/logs/sensor-retry-install-1794955410606114975/result.json`. A read-only
`--probe` returned `already_ready`; the initial one-shot implementation then
exited and OpenRC marked it crashed. The wrapper was corrected to remain idle
after success, and `rc-service lynx-sensor-retry status` returned `started`.
The previous wrapper is retained on Lynx at
`/usr/local/bin/lynx-sensor-retry.before-idle-fix-20261118`. The final live
wrapper SHA-256 is
`4aea39f31f35d969e16969d3dae2cfddc49a94490d4dc5ca65243e43ce277e53`.
Lynx's boot ID and health assertion were unchanged. Twenty-nine offline
policy and worker tests passed.

**Remaining gate:** a low-charge cold boot has not yet exercised the retry
loop. On that boot, inspect `/var/log/lynx-sensor-retry.log`, both service
statuses, the battery snapshot, and `lynx-status --assert-ready`. Preserve
the V53 boot image and V50 rollback. The retry service is independent of the
older active 20% battery reserve policy described in
[the shutdown audit](LYNX-POWER-SHUTDOWNS-20261118.md).
