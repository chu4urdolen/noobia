# Lynx: first verified native Wi-Fi and SSH

**Current thermal safety hold:** Lynx was unplugged and shut down after heating
was reported. Keep her off while the missing battery/CPU temperature and power
management support is reviewed. See [thermal findings](THERMAL-SAFETY.md).

V19 is running natively on the Nord 3 CPH2493. It uses the matching stock
5.10.149 kernel and modules with our BusyBox PID 1/initramfs. No Android
userspace is involved. Display initialization remains outside this milestone.

Only boot_a was changed in this trial. Stock boot, the matching recovery
foundation receipts, slot B and all earlier candidates remain preserved.

## Current connection

On Nexus:

```sh
bash /noobia/lynx/tools/lynx-ssh
bash /noobia/lynx/tools/lynx-ssh 'uname -a; cat /proc/uptime'
```

Current lease is 192.168.100.9 on Noobia, interface wlan0. Host key is pinned
and password authentication is disabled. Credentials stay under secrets/.
Do not put private keys or Wi-Fi credentials into reports.

The collector verified the pinned key, exact kernel release, PID 1 executable,
init and BusyBox hashes, current boot token and root UID. It acknowledged the
token in RAM, cancelling the automatic fallback for this running session.

## Before any later reboot

The cancellation is RAM-only. Start the listener on Nexus before rebooting:

```sh
cd /noobia/lynx
python3 tools/lynx_wifi_v19_contact.py --listen --seconds 660
```

It discovers the DHCP address, authenticates the phone, cancels the fallback
and retrieves diagnostics. Check its receipt rather than assuming the address
is unchanged. Keep Noobia available. No further reboot is needed now.

## Preserve diagnostics

```sh
cd /noobia/lynx
python3 tools/capture_lynx_live.py
```

This checks pinned identity and saves health, bounded runtime logs/journals
and dmesg under a new logs/native-live-* directory. It validates the compressed
archive without extracting it. Records remain private on Nexus. Runtime logs
on the handset are RAM-only, so capture before shutdown.

## Exact restoration path

With the phone in Fastboot, verified stock boot SHA256:
`a67f03d7b826b834c23653b67eaa6efa971eb70ef8af19eee4d33fb5fc7fe995`.

```sh
cd /noobia/lynx
python3 tools/lynx_boot_a_wifi_v19_trial.py --restore-stock
```

The guarded tool verifies files and live identity/layout, then executes only:

```sh
/noobia/lynx/tools/platform-tools/fastboot -s 89BYAY5L4T9HFUOV flash boot_a /noobia/lynx/linux-port/artifacts/stock-cph2493-August-eu-ota/boot.img
```

No automatic reboot, erase, relock or slot switch. This restores the stock boot
partition; it does not recreate the missing Android OS.

## Evidence and cause

Working image SHA256:
`5ce2dbf8a7c132fa7e31f6be70aa76f83afe8c293e2cd5f02251a532486fd851`.
Hardware trial: logs/boot-a-wifi-v19-trial-1792091968352709663.json.
Pinned SSH proof: logs/wifi-v19-contact-1792091967236871487/result.json.
First verified beacon/SSH arrived about109s after collector startup. Phone
stage log records WPA start85s, association wait86s, DHCP87s, SSH-ready91s.

The bundled Alpine wpa_supplicant2.11 lacks the -f log option. The old command
printed help and exited0 without a daemon. Exact-binary ARM VM tests reproduced
this. V19 runs the daemon in the foreground under an owned shell child, redirects
output to a RAM file, and requires a live PONG before proceeding. No kernel,
module, firmware, calibration or credential changes were needed for this fix.

Remaining work includes durable storage/rootfs design and power management.
This proves native BusyBox Linux, Wi-Fi, DHCP and authenticated SSH; it is not
yet a complete postmarketOS installation.
