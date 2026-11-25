# Install packet: LNX-73 agent privilege isolation (privilege split)

* **Author:** Gwyn, 2026-11-25. Rose's backlog P1 "Agent privilege isolation".
* **Installer:** Aria (users and permissions are hers). **Reviewers:** two Noobs other than Gwyn (Banshee and/or Dushich).
* **Attendance:** Tom nearby (her agent restarts; she should keep talking). Nothing here touches boot, the hand-off, the pinned files, the modem, or power.

## Why

`lynx-agent` reads words from outside: speech she hears, camera captions, network findings and chat. Today it runs as **root**, so a prompt that tricks Qwen can make root do whatever any tool can. After this packet:

* the agent runs as the unprivileged user **`lynx-agent`** (the worker drops root itself in Python: `setgroups([])`, `setgid`, `setuid`, `no_new_privs`; a non-zero uid has no capabilities);
* its tools run through **`lynx-tool-broker`** (root). The broker checks the caller's uid with SO_PEERCRED, runs **only** catalogued tools, checks the arguments against each tool's schema, and logs every call to `/var/log/lynx-tool-broker.jsonl` (no arguments or output).

## Files

| Repo source | Installed as | Mode |
| --- | --- | --- |
| `lynx/tools/agent/lynx_tool_broker.py` | `/usr/local/libexec/lynx/lynx-tool-broker` | 755 root:root |
| `lynx/tools/agent/lynx-tool-broker.openrc` | `/etc/init.d/lynx-tool-broker` | 755 root:root |
| `lynx/tools/agent/lynx_agent.py` | `/usr/local/bin/lynx-agent` | 755 root:root (as root it behaves exactly as today; it uses the broker only when it is not root) |
| `lynx/tools/agent/lynx_agent_worker.py` | `/usr/local/bin/lynx-agent-worker` | 755 root:root |

Record `sha256sum` of each file in the review, against the commit the reviewers approved.

## Preflight (read-only)

```sh
cat /var/lib/noobia/power-mode                  # any mode is fine
rc-service lynx-agent-worker status             # note whether it is running
getent passwd lynx-agent || echo absent         # expect: absent
stat -c '%a %U:%G %n' /etc/lynx/nexus-inference.key /var/log/lynx-agent.jsonl /usr/local/share/lynx/agent
python3 -c 'import sys; print(sys.version_info >= (3, 9))'   # True (Popen user=/extra_groups=)
# NOTE: BusyBox setpriv has no --reuid (found 2026-11-25), so neither the worker nor this packet uses it
```

## Install

```sh
addgroup -S lynx-agent && adduser -S -D -H -s /sbin/nologin -G lynx-agent lynx-agent
# what the agent must read or write
chgrp lynx-agent /etc/lynx/nexus-inference.key && chmod 640 /etc/lynx/nexus-inference.key
chown lynx-agent:lynx-agent /var/log/lynx-agent.jsonl && chmod 600 /var/log/lynx-agent.jsonl
chmod 755 /usr/local/share/lynx/agent
# the broker
install -m 755 lynx_tool_broker.py /usr/local/libexec/lynx/lynx-tool-broker
install -m 755 lynx-tool-broker.openrc /etc/init.d/lynx-tool-broker
rc-update add lynx-tool-broker default && rc-service lynx-tool-broker start
# the worker runs the agent as lynx-agent
install -m 755 lynx_agent.py /usr/local/bin/lynx-agent
install -m 755 lynx_agent_worker.py /usr/local/bin/lynx-agent-worker
printf 'export LYNX_AGENT_USER=lynx-agent\n' > /etc/conf.d/lynx-agent-worker
rc-service lynx-agent-worker status | grep -q started && rc-service lynx-agent-worker restart
```

(Restart a service only if it was running: power-saving mode stops it on purpose.)

## Verify (expected output)

```sh
ls -l /run/lynx/tool-broker.sock            # srw-rw----  root lynx-agent
cat > /tmp/lnx73-check.py <<'EOF'
import importlib.util as u
s = u.spec_from_file_location("a", "/usr/local/bin/lynx-agent")
m = u.module_from_spec(s); s.loader.exec_module(m)
print(m.broker_call("lynx_haptic_status", {}))
EOF
chmod 644 /tmp/lnx73-check.py
su -s /bin/sh lynx-agent -c 'python3 /tmp/lnx73-check.py'   # {"ok": true, ...}
rm /tmp/lnx73-check.py
su -s /bin/sh lynx-agent -c 'cat /etc/shadow'   # Permission denied
tail -2 /var/log/lynx-tool-broker.jsonl     # {"uid": <lynx-agent>, "tool": "lynx_haptic_status", "ok": true, ...}
```

Then the live test: touch her and tilt her. She reacts aloud, `ps -o user,args | grep [l]ynx-agent` shows `lynx-agent`, and the broker log grows with each reaction.

## Disable switch and rollback

* **Disable** (back to the agent running as root, which works as before): `rm /etc/conf.d/lynx-agent-worker` and restart `lynx-agent-worker`. The agent is root again, so it ignores the broker.
* **Full rollback:** do the disable, then `rc-service lynx-tool-broker stop; rc-update del lynx-tool-broker`; restore the old worker from its `.bak`; optionally `chmod 600 /etc/lynx/nexus-inference.key`. The user and group can stay.

## Known limits (for the reviewers)

* The broker allows the whole catalogue; the agent itself still enforces the SENSE tool list. A hijacked agent can therefore call any catalogued tool **with schema-valid arguments**, but no longer anything root can do. Network tools are also bounded by LNX-25 (`lynx_tool_policy`).
* `lynx_codex` already runs its coding work as `lynx-coder` (unchanged).
* Tests: `cd lynx/tools/agent && python3 -m unittest test_lynx_tool_broker` (7), plus the existing agent suites.
