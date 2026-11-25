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
* **2222/tcp (SSH):** from the Noobia LAN (192.168.100.0/24).
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

## `lynx_tool_policy.py` (LNX-25): network tool authorization

Every network tool asks `authorize(tool, action, target)` before acting. Rose's
rule 7 (authorized targets) and rule 10 (traceable):

| Action kind | Allowed |
| --- | --- |
| passive views: `net-ifaces`, `lan-sweep`, `wifi-recon` | always |
| probing: `port-scan`, `vuln-check` | only Lynx herself and the Noobia LAN (192.168.100.0/24); a name that hides an outside address is refused |
| path checks: `traceroute`, `dns-audit`, `ssl-audit` | Lynx, the LAN, and public addresses; private networks outside Noobia refused |
| capture: `packet-sample` (tcpdump) | **off** until a person sets `"allow_packet_capture": true` (it records other people's traffic) |
| anything else | refused |

* Policy file (optional): `/etc/lynx/tool-policy.json`, for example
  `{"authorized_networks": ["192.168.100.0/24"], "allow_packet_capture": false}`.
  If it is broken, probing and capture are refused (fail closed).
* Audit log: `/var/log/lynx-tool-policy.jsonl` (mode 600): time, tool, action,
  target, resolved addresses, decision, reason. Never the tool's output.
* Installed on Lynx at `/usr/local/lib/noobia/security/lynx_tool_policy.py`.
  `lynx-net-diag` checks it before its lock and before forking, and exits 3 with
  the reason when it refuses. Check a decision by hand:
  `python3 /usr/local/lib/noobia/security/lynx_tool_policy.py check port-scan 8.8.8.8`.
* `lynx_cellular_diag` needs no gate today: all its actions are read-only;
  `at-probe` only checks that the AT channel exists.
* Tests: `python3 -m unittest test_lynx_tool_policy` (8) here, and the gate tests
  in `lynx/tools/net_diag` (run from `/noobia`).

## `lynx_config_audit.py` (LNX-87, LNX-64, LNX-76): secrets, integrity, kernel

Read-only, on Lynx (`--text` or JSON; exit 1 on a high finding). Checks that key
files, host keys and `authorized_keys` are not readable by others (the inference
key may be group `lynx-agent` after LNX-73), that private logs are not
world-readable, that nothing in her program and service folders is
world-writable (one level, no recursive search), that the three files pinned by
the boot hand-off match their pins, and the kernel hardening sysctls.

First live run, 2026-11-25: **OK**: secrets protected; boot pins match
(openrc-init, musl, lynx-health); kernel 5.10.149-android12-9; no SELinux.

**Hardening for Aria (LNX-87, install with the firewall packet):**
`/etc/sysctl.d/90-lynx-hardening.conf`, applied at boot:

```
kernel.kptr_restrict = 1
kernel.dmesg_restrict = 1            # root (and the rescue tools) can still read dmesg
kernel.unprivileged_bpf_disabled = 1
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.all.rp_filter = 2      # loose: keeps Wi-Fi + cellular routes working
```

(`tcp_syncookies` and `yama.ptrace_scope` do not exist in this kernel.)

> **Never let `apk` upgrade `musl` or `openrc`.** The boot hand-off pins their
> hashes: an upgrade means every boot is refused. Use `apk add --no-upgrade`, and
> check `apk version musl openrc` before installing anything (e.g. `nftables`).

## `repo_secret_scan.py` (LNX-76): the public repository

Runs on Nexus over the files Git tracks, which is what GitHub publishes:
`python3 lynx/tools/security/repo_secret_scan.py [--term WORD ...]`.
It looks for private keys, provider tokens, literal password/secret/key
assignments (skipping placeholders and unit-test fixtures), and private terms
given at run time (never stored). Every hit is masked.

2026-11-25: no keys or tokens. Two old findings remain for Tom to decide: the
Lolth spider-bot firmware carries the robot's default Wi-Fi AP password
(`lolth/firmware/*/0.SpiderBot/webserver.cpp`), and five Argus scripts and
units contain the Pi's home-folder user name.

## `lynx_security_status.py` (LNX-88): her own check-up

An agent tool, `lynx_security_status` (read-only, no arguments), so Lynx can
answer "are you safe?" from facts. It covers the doors open to the network,
serious findings and things to improve, the boot pins, and the last day's
network-tool refusals, broker refusals, prompt-injection attempts and incidents
from Banshee's journal (`/var/log/lynx/security.jsonl`). Installed:
`/usr/local/lib/noobia/security/` plus the tool in her catalogue.
