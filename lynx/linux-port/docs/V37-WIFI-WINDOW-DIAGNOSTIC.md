# V37 bounded Wi-Fi-only diagnostic

V36 reached pinned Wi-Fi SSH on two boots and then lost contact at uptimes
150.72 and 165.07 seconds while local health startup was under way. The last
captured samples contain no explicit power-off request or kernel panic. The
cause remains unknown. A later V33 Alpine boot stayed reachable under the
same read-only collector for 31 consecutive samples, and direct Alpine SSH
was verified. This does not isolate whether the V36 loss is tied to health
startup or to elapsed boot time.

V37 asks one narrower question: **does pinned Wi-Fi SSH survive to uptime 190
seconds without starting V31 health?** It is derived from exact V36 and changes
only the primary `/init` tail. The stock kernel, command line, supplementary
payload, AVB footer and all other image members are byte-identical. It keeps
the same local Wi-Fi startup and rescue SSH, checks that the charger remains
offline, and deliberately requests power-off at uptime 190 seconds. An
independent timer requests power-off 230 seconds after the tail starts if the
main path stalls; the existing bootloader reboot helper is its fallback if a
power-off command returns. It does not mount the Alpine root or start health
modules. This is a **short diagnostic only**, not a safe daily boot image.

The image is private at
`linux-port/artifacts/wifi-only-window-v37-offline/nord3-wifi-only-window-v37-untested.img`,
SHA-256 `b87d9baa503dc72478cb086cea46987292d828b0d6907da3f76113e8f70ccd52`.
Build and independent validation receipts are in the same artifact directory.
Validation checked exact V36 parent, unchanged stock kernel and supplement,
init-only round trip, BusyBox syntax, unlocked/locked AVB model behavior, and
both exact V33/V19 rollback images. `tools/lynx_boot_a_v37_trial.py --prepare`
passed without phone contact. A three-second pinned collector dry run against
the current V33 Alpine boot captured one sample and correctly reported
`candidate_seen=false` at
`logs/v37-wifi-window-1792600658092963760/result.json`.

## First hardware attempt — no pinned contact; V33 restored

On 2026-10-21 Lynx's exact Fastboot serial matched and the collector was
listening before the guarded `boot_a`-only V37 flash. The flash and separate
Fastboot reboot succeeded:
`logs/v37-boot-a-trial-1792600965590634356/result.json` and
`logs/v37-boot-a-trial-1792600973762244944/result.json`. The collector ran
for about 287 seconds with **zero pinned SSH samples** and did not prove that
V37 executed userspace. Lynx then enumerated in Fastboot over USB. The
collector was stopped, and exact V33 was restored only to `boot_a` after a
fresh identity/layout preflight:
`logs/v34-boot-a-trial-1792601253452132247/result.json`. No reboot followed.
The raw collector receipt and incident summary are at
`logs/v37-wifi-window-1792600960480583281/`. Whether USB was unplugged
promptly during the trial is awaiting physical confirmation. A separate
V33 reboot then reached pinned SSH at `192.168.100.7`, passed RAM health,
and ran Alpine/OpenRC as PID 1 on boot ID
`dd9abd57-33f0-46e0-8376-e714d46eef26`:
`logs/v33-alpine-pid1-verification-1792601501041777035/result.json`.
Direct Alpine SSH on port 2222 and charger offline were confirmed. Read-only
pstore still holds only the older UFS token; the expdb prefix hash is
identical to five earlier captures. **The Wi-Fi-only question remains
unanswered. V33 is installed and Alpine is running.**

For any later trial, start `tools/capture_v37_wifi_window.py` before any write; its receipt
must be fresh. The guarded trial tool allows only `boot_a`, requires a fresh
identity/layout preflight and a separate flash receipt before reboot. The
rollback command is `sudo -n python3 tools/lynx_boot_a_v34_trial.py --restore-v33`
from `/noobia/lynx` after Lynx is in Fastboot on USB; it performs its own fresh
preflight and does not reboot. Preserve slot B, bootloader and recovery.

Interpretation: contact through uptime 190 and the deliberate power-off would
make an autonomous-health-path trigger more likely. Loss around 150–165 even
without health would point away from health startup. Neither result alone
establishes the root cause or validates unattended boot.
