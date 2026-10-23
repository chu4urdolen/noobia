# Lynx V47 persistent maintenance events

Lynx V47 uses BusyBox syslogd with an error-level cutoff to keep repeated
UFS warning messages from displacing important records. The maintenance
watcher still sent Wi-Fi degradation, SSH recovery, local-log recovery,
and safety-failure events at logger's default notice severity. Those
events appeared in its RAM output but were filtered from persistent syslog.

The installed maintenance script was byte-for-byte identical to
`linux-port/lynx-maintenance-watch.sh`, SHA-256
`8a4268612d95afead8ac5e81532774fecd83230044b2202ade6e5bd8167fb04d`.
The revised script changes only its event logger to `daemon.err` and adds
an explicit `--event-proof` command for a harmless test marker. The watcher
still only observes Wi-Fi loss; it does not reset the radio or alter the
rescue SSH path. Health and reserve guards remain independent.

On V47 boot `9054078d-aafa-4abf-9600-5c70f8234360`, the guarded update
verified exact rescue `/init` and Wi-Fi script hashes, Alpine/OpenRC PID 1,
ext4 root, all eight services, and healthy battery gauge readings. It
copied the previous script to
`/root/lynx-rescue/lynx-maintenance-notice-v47.sh`, installed the new
script atomically, restarted only `lynx-maintenance`, and checked that the
proof event reached `/var/log/lynx/messages` at error priority. The health,
reserve, and maintenance services were still running afterward:
`logs/v47-maintenance-event-update-1792786211258827167/result.json`.

This verifies persistent logging for the proof event. A real Wi-Fi outage
has not been induced; automatic Wi-Fi repair has not been enabled. If a
future outage occurs, inspect the private maintenance log and power history
before changing the radio. The saved script under `lynx-rescue` is the
exact rollback copy for this userland change; the V47 boot image was not
modified.
