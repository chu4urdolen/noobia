# Install packet: `lynx_touch_events` (non-consuming touch state)

- **Author:** Gwyn (G9).
- **Reviews:** Gwyn wrote it; Dushich second-reviews. Aria executes; nothing
  here has been installed.
- **Risk:** low. The tool only ever sends `CALL TOUCH_STATUS` (NRP 380) on
  the local socket, never `TOUCH_POLL`. No module, service, or boot change.
- **Attendance:** none needed for the install. Proving it end to end needs
  Noob to touch the screen (step 5).

## 1. Files (repository → phone)

| Repository source | Phone destination | Mode | SHA-256 |
| --- | --- | --- | --- |
| `lynx/tools/lynx_agent_touch.py` | `/usr/local/bin/lynx-agent-touch` | 755 root | `6971e397f6a097e2545a08d9f36b252503c132a4cffd7d0990e6c84604122172` |
| `lynx/tools/ui/catalog_proposal/lynx_touch_events.sh` | `/usr/local/share/lynx/agent-tools/lynx_touch_events.sh` | 755 root | `8b08dadbd097675106b82a3b3c6bb5e92010e9ee7db8db8a7ee49a3583648beb` |
| `lynx/tools/ui/catalog_proposal/lynx_touch_events.json` | `/usr/local/share/lynx/agent-tools/lynx_touch_events.json` | 644 root | `7e7b10311ced836e4987241bb7626c6b84cb070225dcdd564018bc784d415229` |

The modes match the installed `lynx-agent-haptic` and `lynx_haptic_stop.*`,
read from Lynx on 2026-11-21. The catalog directory is `700 root`.

## 2. Preflight (read-only)

```sh
lynx-board                     # expect exit 0: fresh, 38/38 in sync
python3 lynx/tools/lynx_remote.py run "test ! -e /usr/local/bin/lynx-agent-touch && test -S /run/lynx/noobd.sock && echo READY"
```

## 3. Install

Use Aria's usual deployment route, with the same pinned SSH as
`lynx_remote.py`. Copy the three files, set modes and owners as in the
table, then compare the hashes on the phone:

```sh
sha256sum /usr/local/bin/lynx-agent-touch /usr/local/share/lynx/agent-tools/lynx_touch_events.*
```

No restart is needed: `lynx-agent` reads the catalog directory on each run
(`lynx/tools/agent/lynx_agent.py:19,60`). The tool has no `nrp_id`, so
`lynx-noobd` does not register it.

## 4. Verify

```sh
python3 lynx/tools/lynx_remote.py run "printf '{}' | /bin/sh /usr/local/share/lynx/agent-tools/lynx_touch_events.sh"
# expect: {"ok":true,"panel_open":true,"finger_down":false,"queued":N,"dropped":M,"consumes_events":false}
python3 lynx/tools/lynx_remote.py run "printf '{}' | /bin/sh /usr/local/share/lynx/agent-tools/lynx_touch_events.sh; printf '{}' | /bin/sh /usr/local/share/lynx/agent-tools/lynx_touch_events.sh"
# expect: the same queued count twice, which shows it consumes nothing
```

Then, in the repository:
1. Copy the two catalog files into `lynx/tools/local_calls/`.
2. Gwyn adds `lynx_touch_events` to the `TOOLS` table in
   `lynx/tools/ui/lynx_tool_manifest.py` as
   `("read_only", "display", ("platform", "touch"), True)`.
3. Regenerate with `lynx_tool_manifest.py --write`.
4. `lynx-board` should then report 39/39 in sync.

## 5. Attended proof (optional, Noob present)

Run the verify call while Noob holds a finger on the screen. Expect
`finger_down: true`, or a rising `queued`. Record it as an attended entry in
`lynx/tools/ui/attended_evidence.json`.

## 6. Disable and rollback

The tool is only reachable through the catalog, so either step below is
complete on its own:

```sh
# disable (keeps the binary)
rm /usr/local/share/lynx/agent-tools/lynx_touch_events.json /usr/local/share/lynx/agent-tools/lynx_touch_events.sh
# full rollback
rm -f /usr/local/bin/lynx-agent-touch /usr/local/share/lynx/agent-tools/lynx_touch_events.*
```

## Evidence

```sh
python3 -m unittest discover -s lynx/tools -p 'test_lynx_agent_touch.py'
```

This runs 8 tests against a real Unix socket answering with the **actual
runtime handler's** reply format. They check:
- only `TOUCH_STATUS` is sent, and consuming commands are refused;
- malformed or impossible replies are rejected (`queued` above 8);
- a runtime that closes without answering, and one that stays silent
  (timeout), are both reported as errors;
- arguments are rejected, and every error comes back as JSON.
