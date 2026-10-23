# V47 local status command

Lynx now has `/usr/local/bin/lynx-status` on persistent Alpine. It reads
the gauge, CPU/SoC thermal zones, CPU cooling states, OpenRC service status,
Wi-Fi carrier and IPv4 address, root free space, power-log size, boot ID,
and uptime. It emits one compact JSON object and makes no control changes.
`--assert-ready` exits nonzero when it finds an issue while still emitting
the JSON, so a caller can save the evidence before investigating.

The guarded installer pinned rescue `/init` and the current V47 boot ID,
checked battery and running services, staged the source in `/run/lynx`,
ran it before installation, then verified the installed file and live
output. It did not restart services or touch a boot partition. The first
passing receipt and complete snapshot are in
`logs/v47-lynx-status-1792787565907355836/result.json`.

That snapshot reported all eight services running, Wi-Fi carrier and
`192.168.100.8/24`, 84% battery at 24.5°C, 551 MiB free, and no issues.
The maximum observed CPU/SoC zone was 35.567°C, with all three CPU cooling
states at zero. Signed gauge current was -145 mA, which indicates net
discharge at that instant. This is a status snapshot; it does not prove
charging behavior or future boot reliability.

Use `lynx-status` on Lynx for the JSON record, or
`lynx-status --assert-ready` before a maintenance action. The source is
`linux-port/lynx-status.py`; the guarded one-time installer is
`tools/install_v47_lynx_status.py`. The V46 boot image and its Fastboot
restoration procedure remain the rollback path for boot changes.
