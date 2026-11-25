# LNX-84: authenticate Lynx's replies to Aigel

Status: candidate, **not installed**. Author: Aria. Two other Noobs review
before the phone install. Noob approves the attended phone change. Deploy
the Lynx client **before** restarting Aigel with server enforcement.

## Files

| Source | Destination | SHA-256 | mode |
| --- | --- | --- | --- |
| `lynx/tools/agent/lynx_agent_worker.py` | `/usr/local/bin/lynx-agent-worker` | `9051217b969f7f2496e0f68b27e2e2157eed10531bce5d70191edbb9b8b8ffd8` | 0755 root:root |

Current phone file: `6a3d27cd19c4d86cce40f6acd4a1db6afe056707b5a5b56ba1b4578b7310da12`.
Backup: `/usr/local/bin/lynx-agent-worker.pre-lnx84` (must not exist before install).
The existing `/etc/noobia/aigel-lynx.secret` is used in place; no key is copied.
The Lynx key and Aigel's registry entry matched in a challenge-response check
on 2026-11-25 without printing either key.
This worker source also contains Gwyn's LNX-73 privilege-drop code. That code
is inert while `LYNX_AGENT_USER` is unset; this packet does not set it or
install the broker.

## Preflight and install

Noob and Aria present; Lynx on stable power. Record boot ID, battery, thermal
status, `rc-service lynx-agent-worker status`, and current file hash. Confirm
both SSH rescue ports 22 and 2222 work, the key is nonempty 0600 root:root,
and the backup path is absent. Run the worker tests below. Stop on mismatch.

From `/noobia` on Nexus, with the pinned SSH identity and host key:

```sh
lyssh() { ssh -p 2222 -o BatchMode=yes -o IdentitiesOnly=yes \
  -o StrictHostKeyChecking=yes -o GlobalKnownHostsFile=/dev/null \
  -o HostKeyAlias=lynx -o UserKnownHostsFile=/noobia/lynx/secrets/lynx_known_hosts \
  -o ConnectTimeout=5 -i /noobia/lynx/secrets/nexus_lynx_ed25519 \
  root@192.168.100.107 "$@"; }
lyssh 'umask 077; cat > /tmp/lynx-agent-worker.lnx84' < lynx/tools/agent/lynx_agent_worker.py
lyssh 'set -eu; test ! -e /usr/local/bin/lynx-agent-worker.pre-lnx84; test "$(sha256sum /usr/local/bin/lynx-agent-worker | cut -d" " -f1)" = 6a3d27cd19c4d86cce40f6acd4a1db6afe056707b5a5b56ba1b4578b7310da12; test "$(sha256sum /tmp/lynx-agent-worker.lnx84 | cut -d" " -f1)" = 9051217b969f7f2496e0f68b27e2e2157eed10531bce5d70191edbb9b8b8ffd8; cp -p /usr/local/bin/lynx-agent-worker /usr/local/bin/lynx-agent-worker.pre-lnx84; install -m 755 /tmp/lynx-agent-worker.lnx84 /usr/local/bin/lynx-agent-worker; rm /tmp/lynx-agent-worker.lnx84; if rc-service lynx-agent-worker status | grep -q started; then rc-service lynx-agent-worker restart; fi; rc-service lynx-agent-worker status || true'
```

Expected: service retains its preflight state (started in active mode, stopped
in debug or power-saving mode); installed and backup hashes match above; both SSH
ports still work. Verify a bounded local Python import can sign a fixed probe
body with the existing key; compare the signature to the Nexus registry entry
without logging either secret. Observe one real reply reaching Aigel after the
next normal agent job. Keep the server's old permissive route running until
this is verified. Do not create a new job just to test the service.

## Disable and rollback

Restore the backup and restart `lynx-agent-worker` only if it was already
running; this removes reply signing without waking Lynx out of debug or
power-saving mode.
The new Aigel server **must not be running** before this rollback, or it will
reject unsigned replies. If it is running, roll back Aigel first.

```sh
lyssh 'set -eu; test "$(sha256sum /usr/local/bin/lynx-agent-worker.pre-lnx84 | cut -d" " -f1)" = 6a3d27cd19c4d86cce40f6acd4a1db6afe056707b5a5b56ba1b4578b7310da12; cp -p /usr/local/bin/lynx-agent-worker.pre-lnx84 /usr/local/bin/lynx-agent-worker; if rc-service lynx-agent-worker status | grep -q started; then rc-service lynx-agent-worker restart; fi; rc-service lynx-agent-worker status || true'
```

Offline test: `python3 -m unittest discover -s lynx/tools/agent -p 'test_lynx_agent_worker.py' -q` (8 tests pass).

Reviews: Gwyn ACCEPT with the two packet corrections above (forge lynx #488);
second independent review pending. The exact corrected packet still needs
reviewer confirmation before installation.
