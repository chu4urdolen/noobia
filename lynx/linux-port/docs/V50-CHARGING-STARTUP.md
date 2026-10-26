# V50 persistent charging stack trial

The Hama wall charger was identified as DCP only after the stock USB PHY,
MT6375 Type-C controller, attach bridge, and late IRQ enable modules were
loaded into RAM and the cable was reconnected. See `V50-CHARGER-TCPC.md`.

`lynx-charging-stack.sh` pins those four exact August stock module hashes and
loads them in a dependency-aware order: USB PHY, TCPC, attach bridge, then
late IRQ enable. It checks the running kernel and expected platform devices,
verifies every module file before use, and is idempotent on a boot where the
modules are already present. It does not change charge current, voltage,
charger registers, boot partitions, recovery, or slot B. The OpenRC wrapper
logs to `/var/log/lynx/charging-stack.log` and leaves modules for kernel
shutdown when stopped.

At 54% battery and 24.4°C, `tools/stage_v50_charging_stack.py` copied the
four verified stock modules plus the helper and OpenRC service to Alpine.
It did not enable the service. Its first `--start` on the already working
boot found all four modules loaded and passed status and Alpine health checks.
Receipt: `logs/v50-charging-stack-stage-1793050690819757949/result.json`.

`tools/reboot_v50_charging_service_trial.py` checked the exact V50 boot_a
rollback image, rescue identity, Alpine health, DCP attach, service status,
and reboot dry run. Its no-change receipt is
`logs/v50-charging-service-reboot-1793050738783876417/result.json`.
The same tool then enabled `lynx-charging-stack` in the default OpenRC
runlevel and requested one reboot. Receipt:
`logs/v50-charging-service-reboot-1793050747695975333/result.json`.
Read-only new-boot observer:
`logs/v50-first-boot-1793050745006898141/events.jsonl`.

The observer then saw a new rescue boot ID
`98813e2e-f528-419f-90fa-c9016dc0c005`, followed by Alpine 3.24.2 on the
same ID, with three successful authenticated Alpine samples. The service log
shows all four modules loaded on that new boot. Without touching the cable,
the charger moved from initial `attach=0` to `online=2`, `Charging`, with
`usb_type=[DCP]`. Battery read 55% and about +325 mA signed current at
25.6°C. Alpine health had no issues, all eight monitored services running,
and no ext4 errors. Thus the persistent service restores charger-type
detection automatically on at least one V50 reboot while the Hama charger
remains connected.

The boot image itself remains V50. If the service fails, Alpine should still
boot and its log should show the first failed step. The V50 boot_a image and
the previously documented Fastboot restoration command remain available.
