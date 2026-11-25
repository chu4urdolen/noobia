# LNX-85: attended authenticated DNS proof on Lynx

Status: candidate for two reviews by Noobs other than Aria. This is a
120-second **local proof**, not a system resolver cutover. It leaves
`/etc/resolv.conf`, DHCP, routes, SSH, and boot services unchanged. A later
packet may safely switch the system resolver only after boot persistence and
failure recovery are designed. Noob and Aria attend the proof on stable
power. No reboot or modem operation.

| Nexus source | Lynx destination | SHA-256 | mode |
| --- | --- | --- | --- |
| `lynx/tools/dns/lynx-unbound-dot.conf` | `/usr/local/lib/noobia/dns/lynx-unbound-dot.conf` | `8400922128605d5b02e8d345beee869a87d59fd2a027083c93139c8f7da2436d` | 0644 |
| `lynx/tools/dns/lynx_dns_trial.sh` | `/usr/local/sbin/lynx-dns-trial` | `ca48539c630826d20e1a28db80d586092636abef4609bc4e044f24f8bdabff03` | 0755 |

The config binds only `127.0.0.1:53`, allows loopback clients, and forwards
to Quad9 `9.9.9.9` and `149.112.112.112` on TCP 853 with TLS name
`dns.quad9.net` and the system CA bundle. Two options together keep it TLS-only:
`forward-tls-upstream: yes` makes "the queries to this forwarder use TLS for transport",
and `forward-first: no` (Unbound's default) means a SERVFAIL from the forwarders is
**not** retried by Unbound's own (plaintext) recursion; only `yes` would "fall back to
less specific resolution" (unbound.conf manual, checked 2026-11-25). The manual
documents no plaintext fallback for TLS forwarders. Quad9 lists these addresses and name in its [service
documentation](https://docs.quad9.net/services/); the [Unbound
manual](https://unbound.docs.nlnetlabs.nl/en/latest/manpages/unbound.conf.html)
documents the `@853#name` and CA validation syntax. This is a proposed
resolver choice; the live resolver remains Tom's `8.8.8.8`, `1.1.1.1`.

## Preflight

Record time, boot ID, battery/thermal status, `lynx-status --assert-ready`,
current `sha256sum /etc/resolv.conf`, wlan0 address, and SSH 22/2222 plus
NRP 4243 reachability. Require no listener on `127.0.0.1:53`; `ss -lun`
showed none on 2026-11-25. Verify both Quad9 TCP 853 endpoints are reachable
with bounded `nc -z -w 3`. Stop on health or route failure. Check the pinned
boot file hashes:

* `/lib/ld-musl-aarch64.so.1`:
  `32377e6d71725bb019e9ff6d5e9f16b4d5156d6f2c36504191c2d6a7c4d4a44d`
* `/sbin/openrc-init`:
  `6180c8b047e41f2f5fdf581fa3e1a9835a6e2d0a4b3ceb3a60baf3f223217078`

Simulate `apk add --no-cache --simulate 'unbound=1.25.2-r2'
'ca-certificates=20261020-r0'`; require only these six packages and no
upgrade/removal: ca-certificates 20261020-r0, dnssec-root 20250524-r0,
hiredis 1.3.0-r0, unbound-libs 1.25.2-r2, unbound 1.25.2-r2,
unbound-openrc 1.25.2-r2. This exact simulation succeeded 2026-11-25.
Stop if the repo or package set differs.

## Install and proof

Install only the pinned packages above. Recheck both boot hashes. Require
`id unbound`, `command -v unbound`, `command -v unbound-checkconf`,
`command -v timeout`, `command -v nslookup`, and `command -v flock`. Do not
enable the Unbound OpenRC unit.

From `/noobia` on Nexus, stream exact files with the pinned SSH identity:

```sh
lyssh() { ssh -p 2222 -o BatchMode=yes -o IdentitiesOnly=yes \
  -o StrictHostKeyChecking=yes -o GlobalKnownHostsFile=/dev/null \
  -o HostKeyAlias=lynx \
  -o UserKnownHostsFile=/noobia/lynx/secrets/lynx_known_hosts \
  -o ConnectTimeout=5 -i /noobia/lynx/secrets/nexus_lynx_ed25519 \
  root@192.168.100.107 "$@"; }
lyssh 'umask 077; cat > /tmp/lynx-unbound-dot.conf' < lynx/tools/dns/lynx-unbound-dot.conf
lyssh 'umask 077; cat > /tmp/lynx_dns_trial.sh' < lynx/tools/dns/lynx_dns_trial.sh
lyssh 'set -eu; install -d -m 755 /usr/local/lib/noobia/dns; install -m 644 /tmp/lynx-unbound-dot.conf /usr/local/lib/noobia/dns/lynx-unbound-dot.conf; install -m 755 /tmp/lynx_dns_trial.sh /usr/local/sbin/lynx-dns-trial; rm /tmp/lynx-unbound-dot.conf /tmp/lynx_dns_trial.sh; sha256sum /usr/local/lib/noobia/dns/lynx-unbound-dot.conf /usr/local/sbin/lynx-dns-trial; stat -c "%a %n" /usr/local/lib/noobia/dns/lynx-unbound-dot.conf /usr/local/sbin/lynx-dns-trial'
```

Compare hashes/modes to the table. Run `unbound-checkconf
/usr/local/lib/noobia/dns/lynx-unbound-dot.conf`; require exit 0. Record
`lynx-dns-trial status` = `off`, then `lynx-dns-trial enable`. The helper
starts a loopback Unbound process, proves a bounded query to it, and starts
a Lynx-local 120-second timer that terminates only this process. Expect
`local DoT proof active; auto-stop in 120s` and `status` = `pending`.
During the window, make another bounded `nslookup example.com 127.0.0.1` and
recheck SSH/NRP. **The DoT evidence is now mandatory and built into `enable`**
(Dushich #543, Gwyn 2026-11-25). After the probe answers, the script reads this
unbound's own sockets (`/proc/<pid>/fd` and `/proc/net/{tcp,udp}{,6}`). It requires at
least one connection to port 853 and **no** socket to port 53 away from loopback.
Otherwise it stops the process and exits 1. The success line prints
`dot=N plain=0`; record it. Record results
and timing. **Do not leave the proof running:** `lynx-dns-trial disable` or
wait for timer, then require `status` = `off`, no loopback listener, and the
original `/etc/resolv.conf` hash. The timer does not reboot or power down.

## Disable and rollback

`lynx-dns-trial disable` stops only the process whose command line contains
the installed config path and removes its own `/run/lynx-dns-trial` state.
If SSH fails during the proof, the local timer stops it after 120 seconds;
numeric-IP SSH remains independent of DNS. The resolver file was never
changed. Packages and installed files may remain for inspection; package
removal is a separate dependency-checked change.

Offline verification: `sh -n lynx/tools/dns/lynx_dns_trial.sh` and
`python3 -m unittest discover -s lynx/tools/dns -p 'test_*.py' -v` pass
(2/2). The fake resolver tests timer and manual disable; on-device
`unbound-checkconf`, TLS connectivity, and traffic observation remain
mandatory before concluding the proof.

## Revision 2026-11-25 (Gwyn; Aria out of tokens)

Script `ca48539c630826d20e1a28db80d586092636abef4609bc4e044f24f8bdabff03`. Changes:
* the timer starts **before** unbound;
* it waits up to 6 s for the listener;
* the mandatory socket proof above.

Config unchanged (`84009221`). Tests: 4/4 under `/bin/sh` (DoT proof passes, no-DoT and plaintext cases refused and cleaned up, timer and disable). Under BusyBox `sh` on Nexus, the shell's built-in `nslookup` replaces the test's fake one, so the attended on-device run is the real test of that path. Gwyn is now co-author: reviews needed from Dushich and Banshee.
