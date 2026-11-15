# Persistent diagnostic journal

`00-noobia-persistent.conf` preserves systemd and kernel logs across reboots,
with a 256 MiB size ceiling and a fourteen-day retention ceiling. Install it as:

```sh
sudo install -d -m 0755 /var/log/journal /etc/systemd/journald.conf.d
sudo install -m 0644 00-noobia-persistent.conf \
  /etc/systemd/journald.conf.d/00-noobia-persistent.conf
sudo systemctl restart systemd-journald
```

After a forced reboot, inspect the previous boot with:

```sh
journalctl -b -1 -p warning..alert
journalctl -k -b -1
```
