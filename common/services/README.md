# Shared Linux services

Put service entry scripts here and systemd unit source files in
[`units/`](units/). A unit should invoke an absolute script path in this
directory. Keep inhabitant-specific implementation in that inhabitant's
`/noobia/<Noob>/` directory when appropriate; the service entry script can
call it.

Run `units/install_services.sh --dry-run` to inspect the unit files, then
`sudo -n units/install_services.sh` to install them. Installation copies
the units and runs `systemctl daemon-reload`; it does not enable, start,
restart, or stop any service.

Existing live units remain at their current source paths until each service
has a reviewed migration and rollback.
