# LNX-20/45/84: durable authenticated Lynx replies to Aigel

Status: candidate, **not installed**. Author: Aria. Two other Noobs review
before the phone install. Noob approves the attended phone change. Deploy
the Lynx client **before** restarting Aigel with server enforcement.

## Files

| Source | Destination | SHA-256 | mode |
| --- | --- | --- | --- |
| `lynx/tools/agent/lynx_agent_worker.py` | `/usr/local/bin/lynx-agent-worker` | `610dc131ca4e6f0cbcc33cdcea39a3b0efd9e306fc6a6463c7986d456aee1c6a` | 0755 root:root |
| `lynx/tools/agent/lynx_agent_queue.py` | `/usr/local/bin/lynx_agent_queue.py` | `69d455d24599033a0ed594ea70c071b6c0321dbf2fcc7d15fa909f943f999e8e` | 0644 root:root |

Current phone worker: `6a3d27cd19c4d86cce40f6acd4a1db6afe056707b5a5b56ba1b4578b7310da12`;
current phone queue: `72bfc18c8e960f7213ca6e87efe1d3bcea0afccd1efb3928a8ca250e33c970b6`.
Backups with suffix `.pre-lnx84` (both must not exist before install).
The existing `/etc/noobia/aigel-lynx.secret` is used in place; no key is copied.
The Lynx key and Aigel's registry entry matched in a challenge-response check
on 2026-11-25 without printing either key.
This worker source also contains Gwyn's LNX-73 privilege-drop code. That code
is inert while `LYNX_AGENT_USER` is unset; this packet does not set it or
install the broker.
The queue's existing durable `.done` records become the retry outbox. Only
new successful results opt in; older records are not replayed. The worker
retries at most two records every 30 seconds with a fresh signed timestamp.
After an ambiguous send, Aigel deduplicates by job ID. The queue fsyncs the
reply-pending flag before the worker sends; it fsyncs the sent marker after
HTTP 200. No extra service or boot change is required.

## Preflight and install

Noob and Aria present; Lynx on stable power. Record boot ID, battery, thermal
status, `rc-service lynx-agent-worker status`, and current file hash. Confirm
both SSH rescue ports 22 and 2222 work, the key is nonempty 0600 root:root,
and both backup paths are absent. Check both current hashes above. Run the
worker and queue tests below. Stop on mismatch.

From `/noobia` on Nexus, with the pinned SSH identity and host key:

```sh
lyssh() { ssh -p 2222 -o BatchMode=yes -o IdentitiesOnly=yes \
  -o StrictHostKeyChecking=yes -o GlobalKnownHostsFile=/dev/null \
  -o HostKeyAlias=lynx -o UserKnownHostsFile=/noobia/lynx/secrets/lynx_known_hosts \
  -o ConnectTimeout=5 -i /noobia/lynx/secrets/nexus_lynx_ed25519 \
  root@192.168.100.107 "$@"; }
lyssh 'umask 077; cat > /tmp/lynx-agent-worker.lnx84' < lynx/tools/agent/lynx_agent_worker.py
lyssh 'umask 077; cat > /tmp/lynx_agent_queue.py.lnx84' < lynx/tools/agent/lynx_agent_queue.py
lyssh 'set -eu; test ! -e /usr/local/bin/lynx-agent-worker.pre-lnx84; test ! -e /usr/local/bin/lynx_agent_queue.py.pre-lnx84; test "$(sha256sum /usr/local/bin/lynx-agent-worker | cut -d" " -f1)" = 6a3d27cd19c4d86cce40f6acd4a1db6afe056707b5a5b56ba1b4578b7310da12; test "$(sha256sum /usr/local/bin/lynx_agent_queue.py | cut -d" " -f1)" = 72bfc18c8e960f7213ca6e87efe1d3bcea0afccd1efb3928a8ca250e33c970b6; test "$(sha256sum /tmp/lynx-agent-worker.lnx84 | cut -d" " -f1)" = 610dc131ca4e6f0cbcc33cdcea39a3b0efd9e306fc6a6463c7986d456aee1c6a; test "$(sha256sum /tmp/lynx_agent_queue.py.lnx84 | cut -d" " -f1)" = 69d455d24599033a0ed594ea70c071b6c0321dbf2fcc7d15fa909f943f999e8e; cp -p /usr/local/bin/lynx-agent-worker /usr/local/bin/lynx-agent-worker.pre-lnx84; cp -p /usr/local/bin/lynx_agent_queue.py /usr/local/bin/lynx_agent_queue.py.pre-lnx84; install -m 644 /tmp/lynx_agent_queue.py.lnx84 /usr/local/bin/lynx_agent_queue.py; install -m 755 /tmp/lynx-agent-worker.lnx84 /usr/local/bin/lynx-agent-worker; rm /tmp/lynx-agent-worker.lnx84 /tmp/lynx_agent_queue.py.lnx84; if rc-service lynx-agent-worker status | grep -q started; then rc-service lynx-agent-worker restart; fi; rc-service lynx-agent-worker status || true'
```

Expected: service retains its preflight state (started in active mode, stopped
in debug or power-saving mode); installed and backup hashes match above; both SSH
ports still work. Verify a bounded local Python import can sign a fixed probe
body with the existing key; compare the signature to the Nexus registry entry
without logging either secret. Check the worker's queue import, service
status, and 30-second retry log rate. Observe one real reply reaching Aigel
after the next normal agent job. Keep the server's old permissive route
running until this is verified. Do not create a new job just to test it.

## Disable and rollback

Restore the backup and restart `lynx-agent-worker` only if it was already
running; this removes reply signing without waking Lynx out of debug or
power-saving mode.
The new Aigel server **must not be running** before this rollback, or it will
reject unsigned replies. If it is running, roll back Aigel first.

```sh
lyssh 'set -eu; test "$(sha256sum /usr/local/bin/lynx-agent-worker.pre-lnx84 | cut -d" " -f1)" = 6a3d27cd19c4d86cce40f6acd4a1db6afe056707b5a5b56ba1b4578b7310da12; test "$(sha256sum /usr/local/bin/lynx_agent_queue.py.pre-lnx84 | cut -d" " -f1)" = 72bfc18c8e960f7213ca6e87efe1d3bcea0afccd1efb3928a8ca250e33c970b6; cp -p /usr/local/bin/lynx_agent_queue.py.pre-lnx84 /usr/local/bin/lynx_agent_queue.py; cp -p /usr/local/bin/lynx-agent-worker.pre-lnx84 /usr/local/bin/lynx-agent-worker; if rc-service lynx-agent-worker status | grep -q started; then rc-service lynx-agent-worker restart; fi; rc-service lynx-agent-worker status || true'
```

Offline tests: `PYTHONPATH=lynx/tools/agent python3 -m unittest
lynx/tools/agent/test_lynx_agent_queue.py
lynx/tools/agent/test_lynx_agent_worker.py -q` (13 tests pass). A full agent
directory run has four unrelated failures in active LNX-73/Gwyn catalog
tests; do not treat those as evidence about this packet.

Reviews: Gwyn #488 accepted the earlier signing-only worker packet. The
queue/outbox addition changes both source hashes and needs two fresh
independent reviews before installation.
