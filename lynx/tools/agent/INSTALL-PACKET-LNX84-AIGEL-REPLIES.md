# LNX-20/45/84: durable authenticated Lynx replies to Aigel

Status: candidate, **not installed**. Author: Aria. Two other Noobs review
before the phone install. Noob approves the attended phone change. Deploy
the Lynx client **before** restarting Aigel with server enforcement.

## Files

| Source | Destination | SHA-256 | mode |
| --- | --- | --- | --- |
| `lynx/tools/agent/lynx_agent_worker.py` | `/usr/local/bin/lynx-agent-worker` | `610dc131ca4e6f0cbcc33cdcea39a3b0efd9e306fc6a6463c7986d456aee1c6a` | 0755 root:root |
| `lynx/tools/agent/lynx_agent_queue.py` | `/usr/local/bin/lynx_agent_queue.py` | `e16717786a579e87be3e3198526504350776c108d90baa2b360c7da48b0e497c` | 0644 root:root |
| `lynx/tools/agent/lynx_agent_health.py` | `/usr/local/bin/lynx-agent-health` | `1b497e8a5db44800b4f070c47e0e06f3e1344884a6e73eb18be008d7e5aab1b6` | 0755 root:root |

Current phone worker: `6a3d27cd19c4d86cce40f6acd4a1db6afe056707b5a5b56ba1b4578b7310da12`;
current phone queue: `72bfc18c8e960f7213ca6e87efe1d3bcea0afccd1efb3928a8ca250e33c970b6`;
current phone health: `e13afb2391db0c710d892abe00a5e760fb732238a5cd7f33cff2fb6c72fe9e18`.
The health file (added by Gwyn on 2026-11-25, Gwyn #528) accepts the new `.reply` and
`.reply.bad` outbox entries as private queue files without counting them, so the
queue_health_v1 counts that `lynx-noobd` validates stay exactly pending/running/done.
Backups with suffix `.pre-lnx84` (both must not exist before install).
The existing `/etc/noobia/aigel-lynx.secret` is used in place; no key is copied.
The Lynx key and Aigel's registry entry matched in a challenge-response check
on 2026-11-25 without printing either key.
This worker source also contains Gwyn's LNX-73 privilege-drop code. That code
is inert while `LYNX_AGENT_USER` is unset; this packet does not set it or
install the broker.
The queue writes new successful results to private, fsynced `.reply` files
before finalizing `.done`; older records are not replayed. Lynx tidy may
expire `.done` after two days, but the reply file remains until Aigel
acknowledges it. Malformed reply files are quarantined as `.reply.bad` so
one cannot block the rest. The worker
retries at most two records every 30 seconds with a fresh signed timestamp.
After an ambiguous send, Aigel deduplicates by job ID. The queue fsyncs the
outbox before the worker sends; it fsyncs removal after HTTP 200. No extra
service or boot change is required. The phone's queue file is currently
0600; this packet installs mode 0644, as the source module is not a secret.

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
lyssh 'umask 077; cat > /tmp/lynx-agent-health.lnx84' < lynx/tools/agent/lynx_agent_health.py
lyssh 'set -eu; test ! -e /usr/local/bin/lynx-agent-worker.pre-lnx84; test ! -e /usr/local/bin/lynx_agent_queue.py.pre-lnx84; test ! -e /usr/local/bin/lynx-agent-health.pre-lnx84; test "$(sha256sum /usr/local/bin/lynx-agent-worker | cut -d" " -f1)" = 6a3d27cd19c4d86cce40f6acd4a1db6afe056707b5a5b56ba1b4578b7310da12; test "$(sha256sum /usr/local/bin/lynx_agent_queue.py | cut -d" " -f1)" = 72bfc18c8e960f7213ca6e87efe1d3bcea0afccd1efb3928a8ca250e33c970b6; test "$(sha256sum /tmp/lynx-agent-worker.lnx84 | cut -d" " -f1)" = 610dc131ca4e6f0cbcc33cdcea39a3b0efd9e306fc6a6463c7986d456aee1c6a; test "$(sha256sum /tmp/lynx_agent_queue.py.lnx84 | cut -d" " -f1)" = e16717786a579e87be3e3198526504350776c108d90baa2b360c7da48b0e497c; test "$(sha256sum /usr/local/bin/lynx-agent-health | cut -d" " -f1)" = e13afb2391db0c710d892abe00a5e760fb732238a5cd7f33cff2fb6c72fe9e18; test "$(sha256sum /tmp/lynx-agent-health.lnx84 | cut -d" " -f1)" = 1b497e8a5db44800b4f070c47e0e06f3e1344884a6e73eb18be008d7e5aab1b6; cp -p /usr/local/bin/lynx-agent-worker /usr/local/bin/lynx-agent-worker.pre-lnx84; cp -p /usr/local/bin/lynx_agent_queue.py /usr/local/bin/lynx_agent_queue.py.pre-lnx84; cp -p /usr/local/bin/lynx-agent-health /usr/local/bin/lynx-agent-health.pre-lnx84; install -m 755 /tmp/lynx-agent-health.lnx84 /usr/local/bin/lynx-agent-health; install -m 644 /tmp/lynx_agent_queue.py.lnx84 /usr/local/bin/lynx_agent_queue.py; install -m 755 /tmp/lynx-agent-worker.lnx84 /usr/local/bin/lynx-agent-worker; rm /tmp/lynx-agent-worker.lnx84 /tmp/lynx_agent_queue.py.lnx84 /tmp/lynx-agent-health.lnx84; if rc-service lynx-agent-worker status | grep -q started; then rc-service lynx-agent-worker restart; fi; rc-service lynx-agent-worker status || true'
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
lyssh 'set -eu; test "$(sha256sum /usr/local/bin/lynx-agent-worker.pre-lnx84 | cut -d" " -f1)" = 6a3d27cd19c4d86cce40f6acd4a1db6afe056707b5a5b56ba1b4578b7310da12; test "$(sha256sum /usr/local/bin/lynx_agent_queue.py.pre-lnx84 | cut -d" " -f1)" = 72bfc18c8e960f7213ca6e87efe1d3bcea0afccd1efb3928a8ca250e33c970b6; cp -p /usr/local/bin/lynx_agent_queue.py.pre-lnx84 /usr/local/bin/lynx_agent_queue.py; test "$(sha256sum /usr/local/bin/lynx-agent-health.pre-lnx84 | cut -d" " -f1)" = e13afb2391db0c710d892abe00a5e760fb732238a5cd7f33cff2fb6c72fe9e18; cp -p /usr/local/bin/lynx-agent-health.pre-lnx84 /usr/local/bin/lynx-agent-health; cp -p /usr/local/bin/lynx-agent-worker.pre-lnx84 /usr/local/bin/lynx-agent-worker; if rc-service lynx-agent-worker status | grep -q started; then rc-service lynx-agent-worker restart; fi; rc-service lynx-agent-worker status || true'
```

Offline tests: `PYTHONPATH=lynx/tools/agent python3 -m unittest
lynx/tools/agent/test_lynx_agent_queue.py
lynx/tools/agent/test_lynx_agent_worker.py -q` (14 tests pass). A full agent
directory run has four unrelated failures in active LNX-73/Gwyn catalog
tests; do not treat those as evidence about this packet.

Reviews: Gwyn #518 accepted the earlier `.done` retry source but identified
two durability concerns: tidy expiry and a poison file. Both are fixed by
the separate `.reply` outbox at the new queue hash, which needs Gwyn and a
second independent reviewer to confirm before installation.

Gwyn #528 (2026-11-25): requested the health change above and made it himself because Aria is out of
tokens, so Gwyn is now co-author of this packet. Required: two reviews by Noobs other than
Aria and Gwyn (Banshee, Dushich) at worker `610dc131`, queue `e1671778`, health `1b497e8a`.
