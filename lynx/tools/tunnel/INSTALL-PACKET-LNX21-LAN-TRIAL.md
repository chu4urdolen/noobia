# LNX-21: attended WireGuard LAN trial

Status: **candidate for two independent reviews; not installed**. Aria installs
after Noob authorizes this named network change. This is a runtime-only LAN
trial. It does not alter SSH 22/2222, NRP 4243, DNS, default routes, cellular,
OpenRC, systemd startup, or boot partitions. No configuration is loaded at
boot. The one UFW allow rule is persistent until the rollback step, even if
the runtime tunnel interface disappears. LNX-56 (Wi-Fi-independent
reachability) needs a later packet.

## Verified starting point, 2026-11-25

* Lynx: Alpine `wlan0` = `192.168.100.107/24`, default via `.1`,
  `CONFIG_WIREGUARD=y`, `/dev/net/tun` present, no `wg` command. `apk add
  --no-cache --simulate 'wireguard-tools-wg=1.0.20260223-r0'` proposes only
  `wireguard-tools-wg` and `ifupdown-ng-wireguard` at `0.13.0-r0`.
* Nexus: Noobia Wi-Fi = `192.168.100.106/24` on `wlx40a5ef5f66f1`, WireGuard
  kernel module available but not loaded, no `wg` command. `apt-get -s install
  wireguard-tools` proposes only that package (`1.0.20250521-1ubuntu1`). UFW
  controls inbound traffic. UDP 51821 is unused in the current `ss` sample.
* Neither host has a route for `10.77.0.0/30`. This trial reserves `.1` for
  Nexus and `.2` for Lynx. `AllowedIPs` are only the *other* tunnel address
  (`/32`); there is no `0.0.0.0/0` or `::/0`.

## Files, secrets, and modes

No prebuilt phone payload is copied from the repository. Each host generates
its own private key locally with `wg genkey`; private keys never cross SSH or
enter Git, forge notes, transcripts, or receipts. The Nexus file lives in
`/noobia/aria/private/lynx-wireguard/private.key` (0600, Aria) and the Lynx
file in `/etc/lynx/wireguard/private.key` (0600, root). Both directories are
0700. Public keys may be exchanged over the pinned SSH link and recorded in a
private install receipt at
`/noobia/aria/private/lynx-wireguard/receipt-20261125.txt` (0600, Aria).
Record SHA-256 of each **public** key and the modes
of both private key files in the receipt; do not record private key hashes or
contents in shared notes. No static installed files require a source hash.

## Preflight and stop conditions

Noob and Aria present; Lynx on stable power. Record wall time, Lynx boot ID,
`lynx-status --assert-ready`, `ip -4 route` on both hosts, `ss -lun` for UDP
51821, UFW status, the Nexus `wlx40a5ef5f66f1` address, Lynx's current
`nft list ruleset` (or record that nft is absent), and `ip link show wg-lynx`
(expected absent). Verify pinned
SSH on 22 and 2222 and NRP 4243 before and after. Stop if `wg-lynx` or UDP
51821 is already in use, if the LAN addresses differ, or if a route to
`10.77.0.0/30` exists. Simulate each package transaction immediately before
install and stop if it proposes an upgrade or removal. On Lynx, check the
boot-pinned musl and OpenRC SHA-256 values from the firewall packet before
and after `apk add`; stop if either changes.

## Installation and trial

1. Install Nexus `wireguard-tools=1.0.20250521-1ubuntu1` with `sudo -n
   env DEBIAN_FRONTEND=noninteractive apt-get install --yes`; install Lynx
   `wireguard-tools-wg=1.0.20260223-r0` with
   `apk add --no-cache 'wireguard-tools-wg=1.0.20260223-r0'`. Do not enable a
   WireGuard service. Record package versions.
2. Generate each private key locally, with `umask 077`, and derive the public
   key using `wg pubkey`. Exchange **public** keys over the same pinned SSH
   route used by `lynx/tools/lynx_remote.py`; verify the receiving copy's
   SHA-256 before applying either peer configuration.
3. On Nexus, create `wg-lynx` with `ip link add dev wg-lynx type wireguard`,
   add `10.77.0.1/30`, and `wg set` its private-key file, listen-port 51821,
   Lynx public key, and `allowed-ips 10.77.0.2/32`. Bring it up. Add one UFW
   allow rule for UDP 51821 **only** from `192.168.100.107` to
   `192.168.100.106` on `wlx40a5ef5f66f1`; record the numbered rule for
   exact deletion. No forwarding or NAT rule is added.
4. On Lynx, create `wg-lynx` with `ip link add dev wg-lynx type wireguard`,
   add `10.77.0.2/30`, and `wg set` its private-key file, Nexus public key,
   `allowed-ips 10.77.0.1/32`, endpoint `192.168.100.106:51821`, and
   `persistent-keepalive 25`. Bring it up. The Lynx firewall, if active, needs
   no inbound tunnel exception for this **Lynx-initiated** ping trial:
   established/related replies are accepted.
5. From Lynx, run `ping -c 3 -W 2 10.77.0.1`. Expected: 3 replies. On both
   hosts, `wg show wg-lynx latest-handshakes` must show a recent nonzero
   timestamp, and transfer counters must increase. Recheck both hosts' default
   routes (unchanged), Lynx SSH 22/2222 and NRP 4243 from Nexus, battery,
   health, and the security regression suite (15/15 baseline). Record times.

The following commands make the plan concrete. Run each group only after its
preflight succeeds; replace nothing silently. The `lyssh` function uses the
pinned Lynx host identity. The public-key copies must be checked before any
interface is created.

```sh
# On Nexus, from /noobia. These commands are NOT for pre-review execution.
lyssh() { ssh -p 2222 -o BatchMode=yes -o IdentitiesOnly=yes \
  -o StrictHostKeyChecking=yes -o GlobalKnownHostsFile=/dev/null \
  -o HostKeyAlias=lynx \
  -o UserKnownHostsFile=/noobia/lynx/secrets/lynx_known_hosts \
  -o ConnectTimeout=5 -i /noobia/lynx/secrets/nexus_lynx_ed25519 \
  root@192.168.100.107 "$@"; }

sudo -n env DEBIAN_FRONTEND=noninteractive apt-get install --yes wireguard-tools=1.0.20250521-1ubuntu1
lyssh "apk add --no-cache 'wireguard-tools-wg=1.0.20260223-r0'"
install -d -m 700 /noobia/aria/private/lynx-wireguard
(umask 077; wg genkey > /noobia/aria/private/lynx-wireguard/private.key)
wg pubkey < /noobia/aria/private/lynx-wireguard/private.key > /noobia/aria/private/lynx-wireguard/nexus.public.key
lyssh 'install -d -m 700 /etc/lynx/wireguard; umask 077; wg genkey > /etc/lynx/wireguard/private.key; wg pubkey < /etc/lynx/wireguard/private.key > /etc/lynx/wireguard/lynx.public.key'
lyssh 'cat /etc/lynx/wireguard/lynx.public.key' > /noobia/aria/private/lynx-wireguard/lynx.public.key
lyssh 'umask 077; cat > /etc/lynx/wireguard/nexus.public.key' < /noobia/aria/private/lynx-wireguard/nexus.public.key
sha256sum /noobia/aria/private/lynx-wireguard/*.public.key
lyssh 'sha256sum /etc/lynx/wireguard/*.public.key; stat -c "%a %U:%G %n" /etc/lynx/wireguard/private.key'
stat -c '%a %U:%G %n' /noobia/aria/private/lynx-wireguard/private.key

sudo -n ip link add dev wg-lynx type wireguard
sudo -n ip address add 10.77.0.1/30 dev wg-lynx
sudo -n wg set wg-lynx listen-port 51821 private-key /noobia/aria/private/lynx-wireguard/private.key peer "$(cat /noobia/aria/private/lynx-wireguard/lynx.public.key)" allowed-ips 10.77.0.2/32
sudo -n ip link set dev wg-lynx up
sudo -n ufw allow in on wlx40a5ef5f66f1 proto udp from 192.168.100.107 to 192.168.100.106 port 51821

lyssh 'set -eu; ip link add dev wg-lynx type wireguard; ip address add 10.77.0.2/30 dev wg-lynx; wg set wg-lynx private-key /etc/lynx/wireguard/private.key peer "$(cat /etc/lynx/wireguard/nexus.public.key)" allowed-ips 10.77.0.1/32 endpoint 192.168.100.106:51821 persistent-keepalive 25; ip link set dev wg-lynx up; ping -c 3 -W 2 10.77.0.1'
```

The two SHA-256 lines must agree pairwise for each public key. No private key
is printed. Use `sudo -n ufw --dry-run allow in on ...` with the exact rule
arguments in preflight; verify the new numbered UFW rule after installation.

## Disable and rollback

Run `lyssh 'ip link del dev wg-lynx'` on Lynx and
`sudo -n ip link del dev wg-lynx` on Nexus. Delete the **exact UFW rule
created in step 3** with `sudo -n ufw delete allow in on wlx40a5ef5f66f1
proto udp from 192.168.100.107 to 192.168.100.106 port 51821` after
checking its numbered entry, then verify no `wg-lynx` link, no `10.77.0.0/30` route, no UDP 51821
listener, and both rescue SSH ports still work. The runtime interfaces vanish
on reboot, but reboot is not a normal rollback. Keep packages and private
keys for inspection; removal/rotation requires a separate reviewed step.
If the link fails midway, delete any created interface and UFW rule; because
default routes and SSH were never changed, the pinned LAN route remains the
recovery path. No autonomous restart or shutdown is used.

## Required reviews

Two Noobs other than Aria must review the exact install commands, package
plan, keys/modes, UFW rule, preflight, verification, disable and rollback.
The implementation commands must be finalized and hashed in the review
receipt before execution. Reviewers: pending, pending.

References: [WireGuard quick start](https://www.wireguard.com/quickstart/),
[`wg(8)`](https://man7.org/linux/man-pages/man8/wg.8.html).
