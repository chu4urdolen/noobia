# Nexus Lynx presence monitor

`lynx-presence.service` runs in Aria's systemd user session on Nexus, with
user lingering enabled. Source: `lynx/tools/lynx_presence.py` and
`lynx/tools/lynx-presence.service`.

Read the latest result with:

```sh
cat /noobia/lynx/state/presence/current.json
```

The service polls passively for Lynx's known USB identity and standard
Fastboot interface every 30 seconds. It opens a short TCP connection to her
SSH port on Wi-Fi every 30 seconds. Once per minute it reads the Nexus BlueZ
cache to see whether Lynx has an **active Bluetooth connection**. It does not
scan or connect over Bluetooth; therefore `bluetooth_connected=false` does not
prove that Lynx's Bluetooth radio is off or out of range. While Wi-Fi works,
one authenticated SSH read refreshes battery percentage, current, charger
status, and temperature at most once every five minutes. The battery
observation has its own timestamp because it
can become stale when Lynx is offline. An all-negative result is
`not_observed`, never an assertion that Lynx is powered off.

`current.json` is atomically replaced each poll. State changes are appended
to `transitions.jsonl`; routine polls are not added to that history. Both
files are local runtime state and ignored by Git. The service runs at nice
level 10 and does not issue Fastboot commands or change Lynx's state.

```sh
systemctl --user status lynx-presence.service
journalctl --user -u lynx-presence.service -n 20 --no-pager
systemctl --user disable --now lynx-presence.service
```

The monitor was installed and started on 2026-10-31 after V50 restored
Alpine/Wi-Fi. Its first observation was `alpine_wifi`, Bluetooth disconnected,
and 25% battery. Presence changes can lag by one poll; Bluetooth link changes
can lag up to one minute.
