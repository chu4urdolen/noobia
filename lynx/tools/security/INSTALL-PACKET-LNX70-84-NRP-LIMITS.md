# LNX-70/84: NRP authentication resource limits

Status: **candidate, not installed**. Author and installer: Aria. Two other
Noobs must review before an attended phone change. This updates only the
already-keyed `lynx-noobd` Python program; it does not change its protocol,
key, network binding, service definition, SSH, boot partition, modem, or
firewall. It bounds remote TCP clients at 16, closes connections that do not
answer the HMAC challenge within 10 seconds, and limits **authenticated**
remote NRP requests with one shared 10/s token bucket (burst 30). The
root-local Unix socket is exempt. No autonomous reboot or poweroff.

## Files and hashes

| Nexus source | Lynx destination | SHA-256 | mode |
| --- | --- | --- | --- |
| `lynx/tools/lynx_noob_runtime.py` | `/usr/local/bin/lynx-noobd` | `23d8463b63214c005f136849a17ca6e5a6e33f63a6de146dd9f4780793aa20b4` | 0755 root:root |

Current installed file hash, to verify before replacing it:
`3d3de506e6ee4c3c322c086865cd5a1b324a53940cec735feb399574fb163490`.
Backup destination: `/usr/local/bin/lynx-noobd.pre-lnx84` (0755 root:root,
same hash as the current installed file). Stop if it already exists.

## Preflight and attendance

Noob and Aria present, Lynx on stable power. Record wall time, boot ID,
`lynx-status --assert-ready`, battery and temperature, `rc-service
lynx-noobd status` (expected started), both SSH rescue ports from Nexus,
and `python3 lynx/tools/lynx_noobctl.py STATUS` (expected `NRP/1 1 OK`).
Run `python3 lynx/tools/security/run_security_regression.py` from Nexus;
expected 15/15 pass. Confirm the installed hash above, no backup file, and
that `/etc/lynx/nrp-nexus.key` is 0600 root:root without reading it. Stop on
any mismatch or failed health check.

## Install and verify

From `/noobia` on Nexus, after preflight and approval:

```sh
lyssh() { ssh -p 2222 -o BatchMode=yes -o IdentitiesOnly=yes \
  -o StrictHostKeyChecking=yes -o GlobalKnownHostsFile=/dev/null \
  -o HostKeyAlias=lynx \
  -o UserKnownHostsFile=/noobia/lynx/secrets/lynx_known_hosts \
  -o ConnectTimeout=5 -i /noobia/lynx/secrets/nexus_lynx_ed25519 \
  root@192.168.100.107 "$@"; }
lyssh 'umask 077; cat > /tmp/lynx-noobd.lnx84' < lynx/tools/lynx_noob_runtime.py
lyssh 'set -eu; test ! -e /usr/local/bin/lynx-noobd.pre-lnx84; test "$(sha256sum /usr/local/bin/lynx-noobd | cut -d" " -f1)" = 3d3de506e6ee4c3c322c086865cd5a1b324a53940cec735feb399574fb163490; cp -p /usr/local/bin/lynx-noobd /usr/local/bin/lynx-noobd.pre-lnx84; install -m 755 /tmp/lynx-noobd.lnx84 /usr/local/bin/lynx-noobd; rm /tmp/lynx-noobd.lnx84; sha256sum /usr/local/bin/lynx-noobd /usr/local/bin/lynx-noobd.pre-lnx84; rc-service lynx-noobd restart; rc-service lynx-noobd status'
python3 lynx/tools/lynx_noobctl.py STATUS
python3 lynx/tools/security/run_security_regression.py
```

Expected new and backup hashes match the table and paragraph above;
`rc-service` reports started; signed NRP STATUS returns `NRP/1 1 OK`; security
regression remains 15/15; SSH 22/2222 remain reachable. Verify the local
socket via the normal Lynx agent status tool and inspect bounded noobd log
for startup errors. Record all checks with timestamps.
In the attended trial, open one unauthenticated TCP connection to 4243 from
Nexus, read the challenge, send nothing, and verify the server closes it
within 11 seconds. Keep the ordinary signed STATUS probe passing afterward.

## Disable switch and rollback

If any verify step fails, restore the exact backup and restart the service:

```sh
lyssh 'set -eu; test "$(sha256sum /usr/local/bin/lynx-noobd.pre-lnx84 | cut -d" " -f1)" = 3d3de506e6ee4c3c322c086865cd5a1b324a53940cec735feb399574fb163490; cp -p /usr/local/bin/lynx-noobd.pre-lnx84 /usr/local/bin/lynx-noobd; rc-service lynx-noobd restart; rc-service lynx-noobd status'
python3 lynx/tools/lynx_noobctl.py STATUS
```

This is also the disable switch: restoring the prior program removes all new
limits while retaining the previous authenticated NRP behavior. Do not
delete the backup until a later reviewed cleanup. If NRP is unavailable,
SSH 22/2222 remain separate recovery routes. No reboot is needed.

## Offline verification

From `lynx/tools`: `python3 -m unittest test_lynx_nrp_auth_transport
test_lynx_noob_local_socket test_lynx_noob_runtime test_lynx_ble_auth -q`
must pass (22 tests). The new tests cover the global token bucket and the
16-client bound; the existing transport test still proves HMAC authentication
and local socket operation. The 10-second unauthenticated timeout has not
been exercised on the phone and must be checked during attended verification.

Reviews: pending, pending.
