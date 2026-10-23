# Lynx power-history transition gap

The first full read of `/var/log/lynx/power.csv` after the V46→V47
Fastboot trial found a **72-byte zero run** immediately before the first
V47 row. The raw read was preserved unchanged at
`logs/v47-power-history-summary-1792786329536007520/power.csv`.
The previous V46 row and all later V47 rows remain readable. The first
V47 row also has an epoch near January 1970 because the wall clock was
still unset before the local time-sync service ran; the CSV carries a
boot ID and monotonic uptime to identify it without relying on that epoch.

A read-only check found Lynx's ext4 root mounted read/write with
`errors_count=0`, zero first/last ext4 error times, and no matching ext4,
JBD2, or I/O error in the current kernel log. This does not prove why the
zero run appeared. The Fastboot transition followed an unclean departure
from the prior running Alpine session, so interrupted buffered logging is
a plausible cause, not an established one. No filesystem repair was run
on the mounted root.

`tools/summarize_v47_power_history.py` keeps the original bytes, records
the anomaly explicitly, removes only leading zero bytes from a line in
memory for its summary, and rejects embedded zero bytes or malformed data.
Its successful read-only receipt is
`logs/v47-power-history-summary-1792786374425383729/result.json`.
The old and new boot segments each show rising capacity and positive
current. These observations do not prove charge termination.

Future samples now call BusyBox `sync` on the CSV after each append and mode
check. The exact old sampler was copied to
`/root/lynx-rescue/lynx-power-history-before-fsync-v47.sh` before the
isolated OpenRC service restart. Script hashes, service status, a fresh
sample, the health guard, and file permissions passed:
`logs/v47-power-history-sync-1792786430629598468/result.json`.
The original CSV line was deliberately left untouched. A later read still
reported the same one gap and parsed subsequent rows:
`logs/v47-power-history-summary-1792786436480889630/result.json`.
