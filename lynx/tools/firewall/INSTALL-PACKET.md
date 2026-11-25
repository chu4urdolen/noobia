# LNX-65/94: Lynx runtime firewall, stage 1

Status: candidate. **Do not install until two Noobs other than Aria have reviewed
this packet and Noob has authorized the phone change.** Aria owns installation.
No reboot, modem start, SIM trial, network reconfiguration, or boot persistence
is part of this packet. The table disappears at reboot. A later packet may add
boot persistence after both rescue routes have been proven under a live rule.

## Files

| Nexus source | Lynx destination | SHA-256 | mode |
| --- | --- | --- | --- |
| `lynx/tools/firewall/lynx_guard.nft` | `/usr/local/lib/noobia/firewall/lynx_guard.nft` | `84275fe44ba4ec3a5732ae3d27015a9c6f5e5ca5aa31533343364eeeee2af078` | 0644 |
| `lynx/tools/firewall/lynx_firewall.sh` | `/usr/local/sbin/lynx-firewall` | `e3843a6451b09e52af6c78d47cfd21591485bb73d19bb549c1e984f717f66c14` | 0755 |

## Policy

`inet lynx_guard` drops unsolicited input across IPv4 and IPv6. It keeps SSH
22 and 2222 reachable from all of `192.168.100.0/24` on `wlan0`, and NRP
4243 from Nexus `192.168.100.106`. Loopback, established/related traffic,
Wi-Fi DHCP replies, ICMP echo, and IPv6 neighbor/router discovery stay open.
Outbound traffic is unchanged. No inbound cellular exception exists. The
script only adds or deletes `inet lynx_guard`; it never flushes other tables.

## Attendance and preflight

Noob and Aria present, Lynx on stable power, Nexus on the LAN. Keep one SSH
session open on 2222 and a second ready for verification. Record wall time,
boot ID, `lynx-status --assert-ready`, `ip -4 -o addr show dev wlan0`, and
`nft list ruleset` before changing anything. Confirm `wlan0` has
`192.168.100.107/24`, both SSH ports answer from Nexus, NRP 4243 answers,
and no `inet lynx_guard` table already exists. Inspect any other base input
chains in `nft list ruleset`; stop if one could drop rescue traffic. Stop if
these conditions fail.
Read `apk policy nftables`, then run `apk add --no-cache --simulate nftables`;
confirm the configured repository is reachable before installing. Check
`command -v nohup`, `command -v sleep`, `command -v date`, and
`command -v flock`.

## Install and activation

1. On Lynx, `apk add --no-cache nftables`. This is the only package change. Record exact
   package version and `nft --version`. Do not enable the Alpine nftables
   OpenRC service.
2. From `/noobia` on Nexus, use the pinned SSH identity and host key to stream
   each file (Lynx has no `scp` or SFTP server):

   ```sh
   lyssh() { ssh -p 2222 -o BatchMode=yes -o IdentitiesOnly=yes \
     -o StrictHostKeyChecking=yes -o GlobalKnownHostsFile=/dev/null \
     -o HostKeyAlias=lynx \
     -o UserKnownHostsFile=/noobia/lynx/secrets/lynx_known_hosts \
     -o ConnectTimeout=5 -i /noobia/lynx/secrets/nexus_lynx_ed25519 \
     root@192.168.100.107 "$@"; }
   lyssh 'umask 077; cat > /tmp/lynx_guard.nft' < lynx/tools/firewall/lynx_guard.nft
   lyssh 'umask 077; cat > /tmp/lynx_firewall.sh' < lynx/tools/firewall/lynx_firewall.sh
   lyssh 'install -d -m 755 /usr/local/lib/noobia/firewall /usr/local/sbin; install -m 644 /tmp/lynx_guard.nft /usr/local/lib/noobia/firewall/lynx_guard.nft; install -m 755 /tmp/lynx_firewall.sh /usr/local/sbin/lynx-firewall; rm -f /tmp/lynx_guard.nft /tmp/lynx_firewall.sh'
   lyssh 'sha256sum /usr/local/lib/noobia/firewall/lynx_guard.nft /usr/local/sbin/lynx-firewall; stat -c "%a %n" /usr/local/lib/noobia/firewall/lynx_guard.nft /usr/local/sbin/lynx-firewall'
   ```

   Compare hashes with the table and modes with 644/755. Stop on any mismatch.
3. On Lynx, run `nft -c -f /usr/local/lib/noobia/firewall/lynx_guard.nft`.
   Expected: exit 0, no parse errors. Run `lynx-firewall enable`. Expected:
   `loaded; auto-revert in 120s unless confirmed` and `status` = `pending`.
   The Lynx-local timer removes only `inet lynx_guard` after 120 seconds if
   confirmation does not arrive. **Do not confirm from the original SSH
   session.**
4. From Nexus, make new TCP connections to Lynx's ports 22, 2222, and 4243
   with `nc -z -w 2 192.168.100.107 PORT` for each port;
   authenticate to both SSH ports with the pinned key; run `lynx-status
   --assert-ready` over 2222; check the NRP health through its normal tool.
   Record each result and its timestamp. If any check fails, wait for local
   rollback and verify access again. Do not confirm.
5. If every check passes, run `lynx-firewall confirm` from a **new** SSH
   session before 120 seconds elapse. Expected: `confirmed; runtime rules
   retained until disable or reboot`; `status` = `active`. Recheck all three
   ports, Wi-Fi address, SSH, NRP, DHCP renewal behavior, and `lynx-board`.

## Disable and rollback

`lynx-firewall disable` removes only `inet lynx_guard`, immediately. On a
lost link, wait at least 120 seconds and reconnect: the Lynx-local timer
deletes that table unless confirmed. The timer never reboots or powers down
Lynx. If the installed rules have been confirmed but behave badly later,
disable from SSH or Lynx's local terminal. Reboot also clears this runtime
table; do not induce a reboot as the normal rollback route. The package and
files may remain for inspection. To remove them in a separate reviewed
change: `apk del nftables` after confirming no other nftables user depends on
it, then remove only the two installed files.

## Offline verification

`python3 -m unittest discover -s lynx/tools/firewall -p 'test_*.py' -v`
exercises pending rollback, confirm, disable, and refusal to replace an
existing table with a fake `nft`. It does not validate nft syntax or the
live kernel's netfilter support; those are installation preflight checks.

Reviews: pending (reviewer 1), pending (reviewer 2).
