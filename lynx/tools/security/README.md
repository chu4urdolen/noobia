# Lynx security tools

Read-only audits for Rose's backlog, group G (`lynx/BACKLOG.md`). They change
nothing on Lynx. Findings are observations, not proof of an attack (Rose's rule 8).

## `lynx_exposure_audit.py` (LNX-78, LNX-63)

What Lynx exposes to the network. Run on Lynx: `python3 lynx_exposure_audit.py --text`
(or without `--text` for JSON). Exit 0 = nothing above "warn", 1 = a "high"
finding, 2 = the audit failed. Tests: `python3 -m unittest test_lynx_exposure_audit`
(a fake `/proc`, no device needed).

It reads `/proc/net/{tcp,tcp6,udp,udp6}`, maps each socket to its program
through `/proc/<pid>/fd` (no recursive search), and checks:

* every listener against the expected list (SSH 2222, rescue SSH 22, NRP 4243);
* their protections: SSH without passwords or forwarding (`-s -j -k`), NRP only
  from Nexus with a key (`--peer`, `--nexus-key-file`);
* listeners bound to all interfaces or a public address;
* IPv4 forwarding, IPv6, the loopback state, whether a firewall tool exists;
* the versions to check against vulnerability lists (dropbear, Python, kernel).

### First run on the live phone, 2026-11-25

```
Lynx exposure audit: OK - 3 listener(s), firewall: none
  tcp 192.168.100.107:2222 (LAN) Alpine SSH (dropbear)  password logins disabled; local and remote port forwarding disabled
  tcp 192.168.100.107:4243 (LAN) NRP daemon to Nexus (lynx-noobd)  only Nexus may connect; key-authenticated frames
  tcp 192.168.100.107:22   (LAN) early-boot rescue SSH (dropbear)  password logins disabled; port forwarding disabled
  INFO: the early-boot rescue SSH (port 22) listens next to Alpine SSH (2222) - kept on purpose
  WARN: no firewall tool installed (nft/iptables): every listener is reachable from the whole LAN
  INFO: loopback interface is down
  versions: dropbear v2026.91, Python 3.14.8, kernel 5.10.149-android12-9
```

No UDP or IPv6 listeners. IPv4 forwarding is off. IPv6 has only a link-local
address. `lynx-noobd` checks both the peer address and a key authenticator.

### Input for the firewall (LNX-65, Aria)

A starting policy that follows Rose's rules (4: keep Noobia connected, 5: recoverable):

* **Inbound, default drop** on `wlan0` (and on the cellular `ccmni*` interfaces once
  they are up). Allow established/related traffic, ICMP echo and IPv6 neighbour discovery.
* **2222/tcp (SSH):** from the Noobia LAN only (192.168.100.0/24). From Nexus only,
  if Tom agrees.
* **4243/tcp (NRP):** from Nexus 192.168.100.106 only (noobd already refuses others;
  the firewall makes it two locks).
* **22/tcp (rescue SSH): always open, like 2222.** Tom, 2026-11-25: "Don't close rescue
  ports!" It is the way back in when Alpine misbehaves; never filter it more tightly than 2222.
* **Cellular interfaces:** nothing inbound until LNX-92 (inbound reachability) is assessed.
* **Outbound:** allow (her senses and her brain live on Nexus).
* **Rescue ports are never closed:** 22 and 2222 stay reachable from the Noobia LAN in every
  rule set, including the defaults loaded at boot.
* **Recoverable** (LNX-94): load rules with a timed automatic revert, e.g. revert
  after 120 s unless a confirmation over SSH arrives. A bad rule must never lock
  Nexus out of Lynx.
* Lynx has no `nft` or `iptables` yet: the firewall packet must install `nftables`
  (Alpine package) first.
