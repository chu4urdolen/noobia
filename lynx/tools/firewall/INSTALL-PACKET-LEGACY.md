# LNX-65/94: runtime legacy firewall on Lynx

Status: candidate for two independent Noob reviews other than Aria. Aria
installs after both ACCEPT at the exact source hash. No reboot, boot hook,
modem action, or outbound rule change. This replaces the nftables packet,
which failed preflight because this kernel has no `CONFIG_NF_TABLES` (#505).
The nftables packages are already installed but inactive.

| Nexus source | Lynx destination | SHA-256 | mode |
| --- | --- | --- | --- |
| `lynx/tools/firewall/lynx_firewall_legacy.sh` | `/usr/local/sbin/lynx-firewall-legacy` | `6986167dc7ad3d0e38a1d37843190e4eb0023e37f8ff6b335eee242ed76567ee` | 0755 |

The script creates only `LYNX_GUARD` chains in the legacy IPv4 and IPv6
filter tables and jumps to them from INPUT position 1. It never flushes
INPUT, changes a built-in policy, or touches OUTPUT/FORWARD. It accepts
loopback and established traffic, LAN SSH 22/2222 from the whole
`192.168.100.0/24`, NRP 4243 from Nexus `192.168.100.106`, DHCP replies,
IPv4 echo requests and IPv6 ICMP on wlan0. Unicast mDNS/SSDP replies from
LAN source ports 5353/1900 are also allowed for `lynx-netintel discover`;
these ports are source-port spoofable on the LAN, so this is a deliberate
LAN trust exception. Other unsolicited input drops.
This is a runtime rule set only. A 120-second Lynx-local timer removes the
two jumps and chains unless Aria confirms from a **new** SSH session.

## Attendance and preflight

Noob and Aria present, Lynx on stable power, two independent reviews in
forge notes at the source hash. Keep existing SSH 2222 session open. Record
time, boot ID, battery, temperature, `lynx-status --assert-ready`, wlan0
address/route, and open ports 22/2222/4243. Stop if health fails, address
differs from `192.168.100.107/24`, or either rescue SSH route fails.

1. Read exact kernel config from `zcat /proc/config.gz`: require
   `CONFIG_NETFILTER_XTABLES=y`, `CONFIG_IP_NF_IPTABLES=y`,
   `CONFIG_IP6_NF_IPTABLES=y`, `CONFIG_IP_NF_FILTER=y`,
   `CONFIG_IP6_NF_FILTER=y`, `CONFIG_NETFILTER_XT_MATCH_CONNTRACK=y`,
   `CONFIG_NETFILTER_XT_MATCH_MULTIPORT=y`. These were observed 2026-11-25.
2. Check `apk policy iptables-legacy`; simulate
   `apk add --no-cache --simulate 'iptables-legacy=1.8.13-r0'`. Require only
   `libip4tc`, `libip6tc`, and `iptables-legacy` at 1.8.13-r0, no upgrade or
   removal. These were the 2026-11-25 simulation result. Stop on repo error.
3. `sha256sum /lib/ld-musl-aarch64.so.1 /sbin/openrc-init` must match
   `32377e6d71725bb019e9ff6d5e9f16b4d5156d6f2c36504191c2d6a7c4d4a44d`
   and `6180c8b047e41f2f5fdf581fa3e1a9835a6e2d0a4b3ceb3a60baf3f223217078`.
4. After package install, inspect `iptables-legacy -S INPUT`,
   `ip6tables-legacy -S INPUT`, and both `-nL LYNX_GUARD` results. Stop if
   another guard chain exists, any current rule depends on rescue traffic
   being handled by a different INPUT ordering, or the tool fails to read
   the kernel tables. Verify `-m conntrack` and `-m multiport` are available
   with `iptables-legacy -m conntrack -h` and `-m multiport -h`.

## Install and activate

On Lynx, install `apk add --no-cache 'iptables-legacy=1.8.13-r0'`; record
installed versions. Recheck both pinned hashes. Do **not** enable an
iptables OpenRC service. From `/noobia` on Nexus, use the pinned host key
and identity (no scp/SFTP on Lynx):

```sh
lyssh() { ssh -p 2222 -o BatchMode=yes -o IdentitiesOnly=yes \
  -o StrictHostKeyChecking=yes -o GlobalKnownHostsFile=/dev/null \
  -o HostKeyAlias=lynx \
  -o UserKnownHostsFile=/noobia/lynx/secrets/lynx_known_hosts \
  -o ConnectTimeout=5 -i /noobia/lynx/secrets/nexus_lynx_ed25519 \
  root@192.168.100.107 "$@"; }
lyssh 'umask 077; cat > /tmp/lynx_firewall_legacy.sh' < lynx/tools/firewall/lynx_firewall_legacy.sh
lyssh 'install -m 755 /tmp/lynx_firewall_legacy.sh /usr/local/sbin/lynx-firewall-legacy; rm -f /tmp/lynx_firewall_legacy.sh'
lyssh 'sha256sum /usr/local/sbin/lynx-firewall-legacy; stat -c "%a %n" /usr/local/sbin/lynx-firewall-legacy'
```

Require table hash and mode 755. `lynx-firewall-legacy status` must say
`off`. Run `lynx-firewall-legacy enable`; expect `loaded; auto-revert in 120s
unless confirmed` and status `pending`. The timer is started before any
INPUT jump. From **new** Nexus connections check TCP 22, 2222, 4243; key
authenticate both SSH ports; run `lynx-status --assert-ready` and normal
NRP health. Record timestamps. If any fails, **do not confirm**; wait at
least 120 seconds for local rollback, then verify both SSH routes. If all
pass, confirm from a new SSH session before the deadline. Expect `active`.
Recheck port, Wi-Fi, SSH, NRP and `lynx-board` health.

## Disable and rollback

`lynx-firewall-legacy disable` removes only this packet's two jumps/chains.
If SSH is lost while pending, wait 120 seconds; the Lynx-local timer does the
same. No reboot or hard shutdown is used. If confirmed rules misbehave,
disable from SSH or local terminal. The rule set is absent after a natural
reboot. Package and script may remain for inspection. Uninstalling the
package or removing the file requires a separate change after dependency
inspection.

## Independent offline check

`python3 -m unittest discover -s lynx/tools/firewall -p 'test_lynx_firewall_legacy.py' -v`
passed 4/4 on 2026-11-25. `sh -n lynx/tools/firewall/lynx_firewall_legacy.sh`
passed. Fake legacy executables exercise timer expiry, confirm/disable, and
middle-rule and partial IPv6 insertion failures; they do not prove live
kernel acceptance. Gwyn #517 blocked the earlier hash because an intermediate
rule failure was masked by POSIX `set -e` suppression in an `if` condition.
Every activation command now has an explicit failure exit, and the new test
reproduces that case. Banshee #515 accepted the earlier hash; **both reviewers
must re-review this revision before installation**.
