# Syra power from Nexus

These commands belong on Nexus, so the delayed relay controller survives Syra's
shutdown. They are not installed as Rose's autonomous power-off tools.

```sh
/noobia/aria/syra-shutdown
/noobia/aria/syra-start
/noobia/aria/syra-power cancel
/noobia/aria/syra-power status
/noobia/aria/syra-power shutdown --dry-run
```

`syra-shutdown` first verifies the Tuya credentials with a read, then sends
`ssh rose 'sudo -n /usr/bin/systemctl poweroff'`. Only after SSH succeeds does
it schedule a 300-second timer in Nexus's user systemd manager. At expiry the
worker checks the generation, deadline, and whether Syra is back online before
sending the Tuya OFF command. A machine responding at 192.168.100.7 is not cut.

`syra-start` invalidates the last pending generation, saves that cancellation,
stops its timer/service, and only then sends ON. All operations use the same
file lock, so an already running OFF operation and a new ON operation are
serialized; ON leaves the relay on. A stale timer cannot act after cancellation.
Repeated shutdown requests replace the old timer. Cancellation does not undo
an OS shutdown already accepted over SSH; ON does not deliberately power-cycle
a still-on relay. It may be necessary to restart an already halted Pi locally.

On Nexus, `start-plug` and `stop-plug` now call the graceful controller, and
the generic `plug on` also revokes a pending delayed cut. Direct vendor commands
outside this controller do not participate in its file lock. Do not bypass it.

Private configuration remains `aria/private/smartplug.json`. Its Tuya local
key is still missing, so real power operations are blocked before any SSH
shutdown. Set the local key privately before use. Scheduler state and a lock
live alongside it; no credentials are included in scheduler output. Tests use
fake relays, SSH, and scheduling; no actual shutdown or power cut was tested.

The timer is transient: it does not survive a Nexus reboot. This leaves the
relay ON rather than making an unexpected cut after recovery. A later ON or
cancel clears any leftover pending state. Syra's narrowly scoped sudoers rule
is `/etc/sudoers.d/noobia-rose-poweroff`; prior state is backed up under
`/var/backups/noobia-rose-agent-20261006-232428/` on Syra.
