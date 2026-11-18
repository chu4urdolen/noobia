# Lynx poweroff audit, 2026-11-18

Lynx has no elapsed-uptime shutdown in the active Alpine battery reserve or
thermal watchers. She is online over Wi-Fi on boot
`d629cc73-aa6d-4aec-808b-8a374740e203` at the time of this audit.

## Observed shutdowns

The persistent `/var/log/lynx/messages` records `LYNX_BATTERY_RESERVE_SHUTDOWN
reason=low_capacity` on Nov 5, 7, 10, 11, 16, and 18. The Nov 16 event was at
09:53:26; the last `power.csv` sample on that boot showed 20% capacity,
−152 mA signed current, and 25.0°C battery temperature. The 86% to 20%
discharge over the preceding 9 hours 47 minutes is consistent with an
unplugged phone running its Linux services. Earlier low-capacity events also
ended near 20% with negative current. These are deliberate reserve shutdowns,
not unexplained reboots.

On Nov 18 the shutdown marker was logged at 10:05:15 UTC (about 12:05 Sofia
time). The last persistent sample from boot
`d629cc73-aa6d-4aec-808b-8a374740e203` was at 10:04:58 UTC: 20%,
−153 mA, and 26.5°C. Lynx later booted as
`6613079f-ae1f-4e05-8123-0988b423d6da` and reported 21% with a positive
charging current. The screen went dark during the normal idle period; the
display log showed the portrait presented and `idle_dark`, while Alpine SSH
and health were working. A physical touch-to-wake check remains pending.

One different event occurred on Nov 6 at 18:29:06: maintenance logged
`SAFE_POWEROFF reason=safety_guard_failed` after two failed safety checks.
The last power sample was 48% and −156 mA. The older log lacks the detailed
probe result needed to identify the failed guard. Do not attribute that event
to low capacity or heat without further evidence. The current maintenance
script logs `SAFETY_PROBE` details when a guard check fails.

## Active policy matters

The installed `/usr/libexec/lynx-battery-reserve.sh` has SHA-256
`57a7936af54fc1a73b2671ef128536a2eee3718efb9640597f627649ef0ebed4`.
It asks for an orderly poweroff after three consecutive 30-second readings at
or below 20%, without checking charging current. That is the older policy.
The newer source file in this repository has SHA-256
`390eb18980393d42c4c811abeaa0da279904699b62e98113267d177a2f3ee7bb`
and allows a verified charging hold, but it was deliberately rolled back
after a V46 trial; see [the charging reserve record](V46-CHARGING-RESERVE-STAGE.md).
The source file is not the live behavior. Do not deploy it as an incidental
cleanup change or assume it has passed a current V53 charging trial.

The independent health, battery-temperature, SoC-temperature, and maintenance
watchers can also power off Lynx on their documented failure or heat limits.
Do not disable these guards to diagnose ordinary battery depletion.

## Next checks

1. Keep recording the boot ID, battery percentage, signed current, charger
   status, and uptime before Lynx goes offline.
2. On the next boot, inspect the final `power.csv` samples and the matching
   `messages` shutdown marker before assigning a cause.
3. If she powers off while a charger is connected near 20%, run a controlled
   charging-aware reserve trial with a verified positive net current and an
   exact rollback. The prior V46 trial does not establish that behavior on V53.
