# Alpine root expansion checkpoint, 2026-11-08

Lynx booted V53 into BusyBox rescue and then handed off to Alpine. Pinned
rescue SSH on port 22 and Alpine SSH on port 2222 both answered on
`192.168.100.107`. Current boot ID is
`0e445a44-0bcc-4c88-a78c-ce0d80efc6d1`.

`/dev/sdc85` remains mounted as the ext4 root. Its partition begins at sector
33,783,808 and contains 466,026,432 sectors, while the filesystem still has
262,144 blocks of 4096 bytes. Label `LYNXROOT`, UUID
`13dc3665-b062-405e-b674-ceae8972fc0f`, and the clean state were checked
read-only. `resize2fs` is installed on Alpine. No resize or partition write
has occurred.

The saved Alpine file backup passed receipt validation, and the exact V53 and
V50 boot images matched their recorded SHA-256 hashes. The guarded command is
`python3 /noobia/lynx/tools/grow_alpine_root.py --preflight`, followed by
`--grow` only when preflight passes. On this boot, preflight stopped at its
45% battery gate: Alpine reported 22%, a positive charging current, no health
issues, and normal temperatures. The charger class reported `USB_DCP` and
`Charging`. Leave the phone charging and re-run preflight on the live boot
before any filesystem change.

Later on this boot, battery rose to 25% and then 27% with positive charging
current and no reported health issues. Nexus rebooted during Dushich's first
offline audit task; Lynx retained the same boot ID and Alpine SSH afterward.
The interrupted task was marked `needs_aria`, its partial file preserved under
`lynx/logs/root-grow-20261107/dushich-interrupted-audit-20261108/`, and a
clean retry completed in Dushich's isolated workspace (commit `bc659db4858c`,
four tests passing). That audit has not been adopted into Lynx tools pending
review of malformed-input handling. Nexus GPU power limit was set to 400 W
for the retry; this is a runtime setting, not a persistent service change.

Aria adopted the audit concept as `lynx/tools/audit_alpine_root_growth.py`,
with strict schema and fixed Lynx identity checks. Four local tests pass,
including a check that the current stopped receipt is rejected. It is an
additional post-growth check; it does not initiate a resize. The latest live
reading is still 27% battery with positive charging current, so the guarded
resize has not run.

## Completed growth on the same boot

Noob explicitly directed Aria to proceed while Lynx was charging below the
original 45% gate. `grow_alpine_root.py` now has an explicit
`--allow-charging-low-battery` switch. It requires at least 25% battery,
positive current of at least 100 mA, and charger status `Charging`; all other
identity, backup, health, and thermal checks remain in force. A read-only call
of this preflight passed at 28% and about +322 mA.

`python3 /noobia/lynx/tools/grow_alpine_root.py --grow --allow-charging-low-battery`
completed successfully on boot `0e445a44-0bcc-4c88-a78c-ce0d80efc6d1`.
Only `/dev/sdc85` ext4 metadata was changed; the script performed no GPT or
boot partition write. Its receipt is
`/noobia/lynx/logs/root-grow-20261107/result.json`, state
`grown-and-verified`. The independent
`lynx/tools/audit_alpine_root_growth.py` returned `pass`. Block count grew
from 262,144 to 58,253,304 at 4096 bytes per block. `df -h /` reports
218.7 GiB total and 209.3 GiB available. The filesystem is mounted from the
same device with the same UUID and boot ID; ext4 reports clean, zero errors,
and Lynx status reports no issues with all eight monitored services running.
No reboot was used for this online resize.
