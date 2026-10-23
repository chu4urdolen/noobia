# Lynx charging reserve: staged userland trial

The user observed a charger-triggered restart loop around the 20% reserve.
The loop cause is not yet proven by a log from that specific trial. Evidence
from the preceding Nexus cable trial is stronger and narrower: exact V46
BusyBox ran on boot ID `d004a4e8-34d5-4839-83e8-15756d2498b9`; the
read-only ZY0603 gauge measured +127 to +145 mA, 20% capacity and
24.6–24.7°C; the Linux charger supply still said `online=0`, `Not charging`.
Pinned SSH disappeared around the old reserve guard's three-reading cutoff.
See `logs/v46-charging-ssh-watch-1792766705031320971/result.json` and
`logs/v46-battery-trend-1792766917990572793/result.json`.

The original reserve script treated every reading at or below 20% as low,
even with verified positive *net battery current*. Three 30-second low
readings request orderly power-off. A charger that wakes V46 again can
therefore create a loop without increasing capacity enough to clear 20%.
The V46 initramfs has an independent charger-supply guard, but during the
observed Nexus trial that supply remained `online=0`; its behavior with a
wall charger still needs observation. If that supply reports `online=1` early
in a future boot, the initramfs guard can shut V46 down before this userland
revision starts. In that case, do not claim the staged reserve change fixes
the loop; diagnose the early guard separately without blind flashing.

`linux-port/lynx-battery-reserve.sh` is the staged source revision, copied
to Lynx's persistent Alpine root. Its activation on a new boot remains
unverified. It allows a low-reserve charging hold only
after two consecutive valid net-current readings of at least +50 mA. It
still powers off after three low or invalid-gauge readings, immediately at
10% capacity or 40°C battery temperature, and after two hours without the
capacity rising above 20%. The separate V46 health supervisor, 45°C battery
watcher, 60°C CPU/SoC watcher and charger-supply guard remain in place.
This design changes no charger register, kernel module or boot partition.

`tools/test_lynx_battery_reserve.py` passes synthetic healthy, low,
positive-current hold, weak-current, critical-capacity, hot-battery and
invalid-gauge cases. The new script's `--once` mode parsed an actual saved
+132 mA, 20%, 24.7°C sample. These are offline results, not a hardware
charging proof.

`tools/stage_v46_charging_reserve.py` requires 11–30% capacity, three fresh
gauge samples at least +75 mA and below 35°C. It atomically places the new
script on persistent ext4, preserves the exact old script under
`/root/lynx-rescue`, and leaves the currently running old guard active.
The next boot is the first trial of the revised policy.
`tools/restore_v46_unplugged_reserve.py` can prepare and restore the old
script through pinned BusyBox rescue SSH on port 22; a rollback also takes
effect on the following boot. Do not stage the change when the preflight
cannot see stable positive current, when the device is hot, or when rescue
SSH is unavailable.

On a later Nexus-cable boot, the gauge reached 26–27% at 26.5–26.8°C and
five consecutive current samples measured +113 to +146 mA. Exact V46 and
Alpine PID 1 passed. The staging preflight then proved three fresh positive
readings and exact pinned rescue SSH; the new script was copied atomically to
persistent ext4, with the old script backed up. The running old guard was not
restarted. The staging and read-only rollback-preparation receipts are
`logs/v46-charging-reserve-update-1792770663450173259/result.json` and
`logs/v46-reserve-rollback-1792770682967626914/result.json`.

One orderly OpenRC reboot was requested with the Nexus cable still attached.
The user observed Orange State then a dark display about every minute, and
the new-boot SSH collector saw no pinned contact for 268 seconds:
`logs/v46-health-window-1792770785801622248/result.json`. The newly staged
userland script cannot execute before Alpine starts. Its activation and the
exact cause of this early loop therefore remain unverified. The initramfs
charger guard, power-off charging boot path, or another early failure could
explain the loop; do not assert one without its saved stage record.

V46 writes checksummed `LXBD1` stage records on persistent ext4, including a
`CHARGER_ON` marker before its early charger shutdown. The new read-only
`tools/capture_v46_bootdiag.py` can retrieve and verify these records after
a future unplugged Alpine boot. That is the next diagnostic step. The boot
image has not been flashed or changed in this work.
