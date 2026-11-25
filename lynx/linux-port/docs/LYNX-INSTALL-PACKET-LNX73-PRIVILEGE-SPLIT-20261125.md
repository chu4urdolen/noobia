# LNX-73: ordinary agent privilege split

Status: **candidate, not installed**. Author: Gwyn; installer revision: Aria.
Two Noobs other than Gwyn and Aria review this revision. Noob and Aria attend
installation on stable power. No boot, modem, route, firewall, or rescue SSH
change is part of this packet.

The ordinary `lynx-agent` process becomes user `lynx-agent` with no effective
capabilities and `no_new_privs=1`. Its tool calls go to a root broker through
`/run/lynx-agent/tool-broker.sock`. The broker checks SO_PEERCRED, catalogue
membership and argument schemas, and logs tool name, uid, result and duration.
This reduces accidental direct access; it is **not a strict root boundary**.
Noob authorized the separate `lynx-coder` full sudo, and the catalogue can
expose `lynx_codex` to the ordinary agent. This packet does not restrict that.

Install and verify the revised LNX-84 signed worker and queue packet first. Its worker already
contains the inert LNX-73 privilege-drop code; `LYNX_AGENT_USER` activates it
here. Stop if either prerequisite is not present at the exact hash below.

| Nexus source | Lynx destination | SHA-256 | mode |
| --- | --- | --- | --- |
| `lynx/tools/agent/lynx_tool_broker.py` | `/usr/local/libexec/lynx/lynx-tool-broker` | `4dde055f2083c477157793ff90f0db233b52a9d223e60b4a6103f0f38f2d51c8` | 0755 root:root |
| `lynx/tools/agent/lynx-tool-broker.openrc` | `/etc/init.d/lynx-tool-broker` | `e5be08535c6e4df4746851f6d9345c0a3edc1d83e95ec1ffa5166336893e111e` | 0755 root:root |
| `lynx/tools/agent/lynx_agent.py` | `/usr/local/bin/lynx-agent` | `89ff4e5a34788817977716772355a6ebbefc53024f4a33ecce5800489abce7b0` | 0755 root:root |
| LNX-84 prerequisite worker | `/usr/local/bin/lynx-agent-worker` | `610dc131ca4e6f0cbcc33cdcea39a3b0efd9e306fc6a6463c7986d456aee1c6a` | 0755 root:root; verify only |
| LNX-84 prerequisite queue | `/usr/local/bin/lynx_agent_queue.py` | `e16717786a579e87be3e3198526504350776c108d90baa2b360c7da48b0e497c` | 0644 root:root; verify only |

Installed old agent hash: `02b72513322a749a49a6ba405203b090465d3ea6d4db7fc1e8adeea1059890a1`.
Backup: `/usr/local/bin/lynx-agent.pre-lnx73`, absent before install.
Broker binary, OpenRC unit, config file, user/group and `/run/lynx-agent` must
also be absent before install. Do not replace an existing path.

## Preflight

Record time, boot ID, battery/temperature, power mode, worker state, SSH 22
and 2222, signed NRP STATUS, installed agent and worker hashes, and the
absence checks above. Run offline tests below. Verify these exact current
metadata before changing permissions:

| Path | Current | Intended |
| --- | --- | --- |
| `/etc/lynx` | 0700 root:root | 0750 root:lynx-agent |
| `/etc/lynx/nexus-inference.key` | 0600 root:root | 0640 root:lynx-agent |
| `/usr/local/share/lynx` | 0700 root:root | 0750 root:lynx-agent |
| `/usr/local/share/lynx/agent-tools` | 0700 root:root | 0750 root:lynx-agent |
| `/var/log/lynx-agent.jsonl` | 0600 root:root | 0600 lynx-agent:lynx-agent |

These directory changes permit the agent to read existing 0644 tool manifests
and `brain.json`; other secret files retain root-only modes. `/run/lynx`
remains root-only. OpenRC creates `/run/lynx-agent` as 0750 root:lynx-agent
on each start. The old packet's chmod of the private agent queue directory
is removed; the ordinary agent does not need the worker queue module.

## Transfer and install

From `/noobia` on Nexus after approval and preflight:

```sh
lyssh() { ssh -p 2222 -o BatchMode=yes -o IdentitiesOnly=yes \
  -o StrictHostKeyChecking=yes -o GlobalKnownHostsFile=/dev/null \
  -o HostKeyAlias=lynx -o UserKnownHostsFile=/noobia/lynx/secrets/lynx_known_hosts \
  -o ConnectTimeout=5 -i /noobia/lynx/secrets/nexus_lynx_ed25519 \
  root@192.168.100.107 "$@"; }
lyssh 'umask 077; cat > /tmp/lynx-tool-broker.lnx73' < lynx/tools/agent/lynx_tool_broker.py
lyssh 'umask 077; cat > /tmp/lynx-tool-broker.openrc.lnx73' < lynx/tools/agent/lynx-tool-broker.openrc
lyssh 'umask 077; cat > /tmp/lynx-agent.lnx73' < lynx/tools/agent/lynx_agent.py
lyssh 'set -eu; test "$(sha256sum /tmp/lynx-tool-broker.lnx73 | cut -d" " -f1)" = 4dde055f2083c477157793ff90f0db233b52a9d223e60b4a6103f0f38f2d51c8; test "$(sha256sum /tmp/lynx-tool-broker.openrc.lnx73 | cut -d" " -f1)" = e5be08535c6e4df4746851f6d9345c0a3edc1d83e95ec1ffa5166336893e111e; test "$(sha256sum /tmp/lynx-agent.lnx73 | cut -d" " -f1)" = 89ff4e5a34788817977716772355a6ebbefc53024f4a33ecce5800489abce7b0; test "$(sha256sum /usr/local/bin/lynx-agent-worker | cut -d" " -f1)" = 610dc131ca4e6f0cbcc33cdcea39a3b0efd9e306fc6a6463c7986d456aee1c6a; test "$(sha256sum /usr/local/bin/lynx_agent_queue.py | cut -d" " -f1)" = e16717786a579e87be3e3198526504350776c108d90baa2b360c7da48b0e497c; test "$(sha256sum /usr/local/bin/lynx-agent | cut -d" " -f1)" = 02b72513322a749a49a6ba405203b090465d3ea6d4db7fc1e8adeea1059890a1; test ! -e /usr/local/bin/lynx-agent.pre-lnx73; test ! -e /usr/local/libexec/lynx/lynx-tool-broker; test ! -e /etc/init.d/lynx-tool-broker; test ! -e /etc/conf.d/lynx-agent-worker; test ! -e /run/lynx-agent; cp -p /usr/local/bin/lynx-agent /usr/local/bin/lynx-agent.pre-lnx73; addgroup -S lynx-agent; adduser -S -D -H -s /sbin/nologin -G lynx-agent lynx-agent; chgrp lynx-agent /etc/lynx /etc/lynx/nexus-inference.key /usr/local/share/lynx /usr/local/share/lynx/agent-tools; chmod 750 /etc/lynx /usr/local/share/lynx /usr/local/share/lynx/agent-tools; chmod 640 /etc/lynx/nexus-inference.key; chown lynx-agent:lynx-agent /var/log/lynx-agent.jsonl; install -m 755 /tmp/lynx-tool-broker.lnx73 /usr/local/libexec/lynx/lynx-tool-broker; install -m 755 /tmp/lynx-tool-broker.openrc.lnx73 /etc/init.d/lynx-tool-broker; install -m 755 /tmp/lynx-agent.lnx73 /usr/local/bin/lynx-agent; printf "export LYNX_AGENT_USER=lynx-agent\n" > /etc/conf.d/lynx-agent-worker; chmod 644 /etc/conf.d/lynx-agent-worker; rm /tmp/lynx-tool-broker.lnx73 /tmp/lynx-tool-broker.openrc.lnx73 /tmp/lynx-agent.lnx73; rc-update add lynx-tool-broker default; rc-service lynx-tool-broker start; if rc-service lynx-agent-worker status | grep -q started; then rc-service lynx-agent-worker restart; fi'
```

On any failure, run rollback below; do not reboot. Verify all three installed
hashes, worker hash, listed ownership and modes, broker socket
`srw-rw---- root:lynx-agent`, and worker state preserved. Run a catalogued
read-only tool (`lynx_haptic_status`) as `lynx-agent` through the broker;
confirm direct `/etc/shadow` access fails. Inspect `NoNewPrivs: 1` and
`CapEff: 0000000000000000` on an actual agent child. Observe one normal
reaction (no synthetic job) and a broker log entry without arguments or
output. Recheck signed NRP and SSH 22/2222.

## Disable and rollback

Disable: remove only `/etc/conf.d/lynx-agent-worker`, restart the worker **if
it was running**, then stop the broker and remove it from the default
runlevel. Full rollback additionally restores the old agent binary and the
original modes and owners. Keep created user and broker files for a later
reviewed cleanup.

```sh
lyssh 'set -eu; test "$(sha256sum /usr/local/bin/lynx-agent.pre-lnx73 | cut -d" " -f1)" = 02b72513322a749a49a6ba405203b090465d3ea6d4db7fc1e8adeea1059890a1; rm -f /etc/conf.d/lynx-agent-worker; if rc-service lynx-agent-worker status | grep -q started; then rc-service lynx-agent-worker restart; fi; rc-service lynx-tool-broker stop || true; rc-update del lynx-tool-broker || true; cp -p /usr/local/bin/lynx-agent.pre-lnx73 /usr/local/bin/lynx-agent; chown root:root /etc/lynx /etc/lynx/nexus-inference.key /usr/local/share/lynx /usr/local/share/lynx/agent-tools /var/log/lynx-agent.jsonl; chmod 700 /etc/lynx /usr/local/share/lynx /usr/local/share/lynx/agent-tools; chmod 600 /etc/lynx/nexus-inference.key /var/log/lynx-agent.jsonl; sha256sum /usr/local/bin/lynx-agent; rc-service lynx-agent-worker status || true'
```

Expected old agent hash and metadata, broker stopped, worker state unchanged,
signed NRP and rescue SSH still usable. No automatic reboot or poweroff.

Offline tests from `/noobia`: `python3 -m unittest discover -s lynx/tools/agent
-p 'test_lynx_tool_broker.py' -q` (9 pass) and `python3 -m unittest discover
-s lynx/tools/agent -p 'test_lynx_agent_worker.py' -q` (9 pass).

Reviews of this revised packet: pending, pending.
