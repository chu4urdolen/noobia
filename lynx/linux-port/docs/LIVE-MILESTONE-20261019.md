# Lynx live milestone — October 19, 2026

Lynx remains on the proven V19 `boot_a` image. On the current unplugged boot,
authenticated SSH at `192.168.100.4` verified boot ID
`3990a1d8-963d-4d17-972e-b0b8a7b366e6`. The fresh collector is
`logs/wifi-v19-contact-1792413125862297291/result.json`.

The exact V28 local health handoff passed as a RAM-only experiment on this V19
boot. Its result and live child/boot trace are under
`logs/local-health-ram-trial-1792413244813495207/`. The independent probe
timer was cancelled after the local health supervisor became ready. The V28
image itself remains unproven because its earlier hardware trial lost contact
before a final health marker. Do not infer that V28 is safe to reflash.

Alpine 3.24.2 was then restored from the immutable host checkpoint into
`/run/lynx/alpine-3.24.2`. Native Python 3.14.8 and Git 2.54.0 ran in the
chroot. The restored root and health supervisor passed three read-only checks
over 30 seconds and a separate log stream stayed healthy. Evidence is at
`logs/alpine-checkpoint-live-restore-1792413288508971900/result.json` and its
`health-runtime-trace.stdout`. BusyBox is still PID 1; Alpine is a RAM chroot,
so this is not a persistent or automatic Alpine boot.

The earlier temporary SSH refusal did not mean Lynx had powered off. The
previous boot ID remained unchanged, Alpine was still in RAM, and the health
supervisor had continued reporting valid readings. Avoid diagnosing a reboot
from a single refused TCP connection.

The first and last 16 MiB of the unmounted `userdata` partition have been
saved read-only on Nexus under
`backups/userdata-edges-1792413021056852842/`, with exact offsets and hashes
in `result.json`. The trailing 16 MiB are zero; the leading 16 MiB contain
unidentified data. This is a bounded backup, not a full partition backup.
No phone storage partition has been formatted or written. The next persistence
step needs a full backup or an explicit decision to discard the unidentified
`userdata` contents and a reviewed filesystem/install procedure.
