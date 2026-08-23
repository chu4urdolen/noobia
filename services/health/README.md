# Noobia health service

A small Linux health monitor written in C. Once per interval it logs root-filesystem
usage, available memory, system load, and temperatures exposed through Linux thermal
zones. Readings and warnings appear in the systemd journal.

## Build and inspect

```sh
make
./noobia-health --once
```

## Install

```sh
sudo make install
sudo systemctl daemon-reload
sudo systemctl enable --now noobia-health.service
systemctl status noobia-health.service
journalctl -u noobia-health.service
```

The unit contains default thresholds. Override them with a systemd drop-in rather
than editing the installed unit:

```ini
[Service]
Environment=HEALTH_INTERVAL_SECONDS=30
Environment=HEALTH_DISK_WARN_PERCENT=85
Environment=HEALTH_MEMORY_WARN_PERCENT=90
Environment=HEALTH_TEMP_WARN_C=75
```

Run `sudo systemctl edit noobia-health.service`, add the desired values, then run
`sudo systemctl restart noobia-health.service`.
