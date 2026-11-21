# Install Packet IS-2: Noobia Autonomy Engine on Lynx

- **Document ID:** `LYNX-INSTALL-PACKET-AUTONOMY-20261121.md`
- **Subsystem:** Untethered Autonomy Harness (`noobia-autonomyd`)
- **Author:** Banshee (Spirit of Initiative 💙)
- **Session:** IS-2 (Executed by Aria after I-2 syslog upgrade)
- **Reviews:** Gwyn / Solo Dushich second reviews required before installation
- **Status:** Ready for review

---

## 1. Rationale & Architecture

Lynx requires the local autonomy engine harness (`noobia-autonomyd`) to transform continuous onboard observations into autonomous actions and reports (contract: `common/autonomy/ARCHITECTURE.md`).

The engine runs as an OpenRC supervised daemon (`noobia-autonomyd`):
1. **Views Follower (`views.py`):** Monitors `/var/log/lynx/messages` in binary mode with atomic state tracking (`file_offset`, `file_inode`) and exact tag parsing.
2. **Prioritizer Stage (`prioritizer.py`):** Filters incoming system events from `wpa_supplicant` and `lynx-bluetoothd`. `kernel` is left out for now; see #287 and QT-1, emitting prioritized sense lines to `noobia-sense`.
3. **Trigger Chunker (`trigger.py`):** Accumulates sense lines into bounded event chunks by priority, volume, or timeout.
4. **Ranker & Aigel Client (`ranker.py`, `aigel_client.py`):** Matches recognized patterns locally; transmits unexplained chunks over HMAC-SHA256 authenticated HTTP to Aigel on Nexus (`:112`).
5. **Agent Link Adapter (`lynx_aigel_adapter.py`):** Translates Aigel decisions and ranked observations into non-coercive background tasks queued in `/var/lib/lynx-agent/jobs`.

---

## 2. Preconditions & Gates

1. **Precondition 1 (I-2 Installed):** Syslog daemon upgraded to `-l 6` via `LYNX-INSTALL-PACKET-I2-SYSLOG-20261121.md` so that notice-level sense lines (`user.notice`) are preserved in `/var/log/lynx/messages`.
2. **Precondition 2 (Nexus Aigel Service Active):** Supervised systemd service `aigel_intake.service` running on Nexus `:112` with valid host registry entry for `lynx` (verified in commit `6f79aab`).
3. **Precondition 3 (Lynx Agent Worker Ready):** Agent queue directories `/var/lib/lynx-agent/jobs` and worker service operational.

---

## 3. Files & SHA-256 Manifest

| Repository File | Target File on Lynx | Mode | Owner | SHA-256 |
|---|---|---|---|---|
| `common/autonomy/sense.py` | `/usr/local/lib/noobia/autonomy/sense.py` | `0644` | root:root | `2c0b418951a52aad96ea3f402df1456c25a07459a07c229ea2338a074d7af4fb` |
| `common/autonomy/views.py` | `/usr/local/lib/noobia/autonomy/views.py` | `0644` | root:root | `f1a9d03e319cba4971c503559cd73fa6b312f7d88569abb5b12f3c64854b7a25` |
| `common/autonomy/trigger.py` | `/usr/local/lib/noobia/autonomy/trigger.py` | `0644` | root:root | `9cd0f8a85b7a350f55bae23b5c8eae24e62f95e925f23427436d442e8083548f` |
| `common/autonomy/ranker.py` | `/usr/local/lib/noobia/autonomy/ranker.py` | `0644` | root:root | `94aa04d9e301fadea5f81397b680a54da5162e112c87f0320aa8b42b92acf169` |
| `common/autonomy/prioritizer.py` | `/usr/local/lib/noobia/autonomy/prioritizer.py` | `0644` | root:root | `310742cbcc946fc2743fcc17a6bc70bd6ce6853e618009fba6835b0255e11532` |
| `common/autonomy/harness.py` | `/usr/local/lib/noobia/autonomy/harness.py` | `0644` | root:root | `e20facab0acb8f6567224623480fe41db48543858a9eee3df658283e1931f613` |
| `common/autonomy/agent_link.py` | `/usr/local/lib/noobia/autonomy/agent_link.py` | `0644` | root:root | `1cc73eba20670d5b31425ef7064f4ae6ebb21304147b109ce35e843aa542a56d` |
| `common/autonomy/aigel_client.py` | `/usr/local/lib/noobia/autonomy/aigel_client.py` | `0644` | root:root | `f7f5007ffa56fee10f0e77c62f0e0f6036b84ee39cb43df5c071246214d9a536` |
| `common/autonomy/viewlog.py` | `/usr/local/lib/noobia/autonomy/viewlog.py` | `0644` | root:root | `5291e8f7acd466bc8f10574d3d29dc4483f57282e136e8ccd8273404deb4fcba` |
| `common/autonomy/autonomyd.py` | `/usr/local/lib/noobia/autonomy/autonomyd.py` | `0755` | root:root | `2f9fc62855496ceb6f4f184e2a7c0095c7ed80797161b785b747ad4a706accc8` |
| `lynx/autonomy/noobia-autonomyd.sh` | `/usr/local/bin/noobia-autonomyd` | `0755` | root:root | `c0763258f1d576246acc6610fad9231056702a7fa0c87ff647f82eb7fa1f02bd` |
| `lynx/tools/agent/lynx_aigel_adapter.py` | `/usr/local/lib/noobia/lynx/lynx_aigel_adapter.py` | `0644` | root:root | `acee2f5c659558cee58695c740b3d5d6ecf29b36593ac6a4e689923545738ed5` |
| `lynx/tools/agent/lynx_agent_queue.py` | `/usr/local/lib/noobia/lynx/lynx_agent_queue.py` | `0644` | root:root | `7abc08ca92c6b8d636d2b35887d87b604852e41a3a78c0f6ac5e9247423d1a33` |
| `lynx/autonomy/autonomy.lynx.json` | `/etc/noobia/autonomy.json` | `0644` | root:root | `d22bd069b48ff1765557578a848de72f3ed260f342482dd539d83c0558de207c` |
| `lynx/autonomy/noobia-autonomyd.initd` | `/etc/init.d/noobia-autonomyd` | `0755` | root:root | `583b6514ee2691360b5a60f35c03dada09598adb69aca0525301aacad7df938f` |

---

## 4. Secret Provisioning & Credential Security

- **Nexus Authority Secret Source:** `/noobia/aigel/private/lynx_autonomy_secret` (mode `0600` on Nexus).
- **Target on Lynx:** `/etc/noobia/aigel-lynx.secret` (mode `0600`, root:root).
- **Security Rule:** Secret bytes are NEVER passed via command line arguments, logged to syslog, or committed to Git. Transferred directly over pinned encrypted SSH session via stdin pipe reusing `lynx/tools/lynx_wifi_v19_contact.py` `ssh_command()`:
  ```sh
  python3 -c '
  import sys, pathlib, subprocess
  sys.path.insert(0, "/noobia/lynx/tools")
  from lynx_wifi_v19_contact import ssh_command

  secret = pathlib.Path("/noobia/aigel/private/lynx_autonomy_secret").read_bytes()
  remote_cmd = "mkdir -p /etc/noobia && cat > /etc/noobia/aigel-lynx.secret && chmod 0600 /etc/noobia/aigel-lynx.secret && chown root:root /etc/noobia/aigel-lynx.secret"
  argv = ssh_command("192.168.100.107", remote_cmd)
  argv[-2:-2] = ["-p", "2222"]
  subprocess.run(argv, input=secret, check=True, timeout=20)
  '
  ```

---

## 5. Local Kill Switch

- **Path:** `/etc/noobia/autonomy.disable`
- **Behavior:**
  - `start_pre()` in `/etc/init.d/noobia-autonomyd` refuses to start the service when present.
  - The daemon loop checks `kill_switch` every cycle. While it is present:
    - **nothing is sent to Aigel and nothing is delivered to the agent**;
    - chunks already queued are **dropped**, counted and logged;
    - the prioritizer emits **no** sense lines;
    - new view lines are read **only to be discarded**. This is deliberate:
      if the daemon stopped reading, lifting the switch would replay every
      line from the disabled period as a burst of stale perceptions;
    - one notice is logged when it turns on, and one when it turns off.
  - When the switch is lifted, the chunker is reset, so no line from
    before or during the disabled period can close a chunk later.
  - Regression tests (Aria #340): `test_harness.py` kill-switch tests and
    `test_autonomyd.py::test_kill_switch_stops_the_prioritizer_and_does_not_replay`.
    A mutation check removing each of the three gates fails a test.

---

## 6. Preflight Checks (Read-Only)

Execute from Nexus over SSH via `lynx_remote.py`:

```sh
python3 lynx/tools/lynx_remote.py run "python3 --version; test -f /var/log/lynx/messages && echo messages_ok; test ! -e /etc/init.d/noobia-autonomyd && echo target_clean"
```

Expect:
- Python 3.12+ available.
- `messages_ok`.
- `target_clean`.

Verify Aigel network reachability from Lynx:
```sh
python3 lynx/tools/lynx_remote.py run "python3 -c \"import urllib.request; print(urllib.request.urlopen('http://192.168.100.106:112/api/v1/status', timeout=5).getcode())\""
```

Expect: `200`.

---

## 7. Installation Steps (Aria IS-2)

1. **Create destination directories:**
   ```sh
   mkdir -p /usr/local/lib/noobia/autonomy \
            /usr/local/lib/noobia/lynx \
            /etc/noobia \
            /var/lib/noobia/autonomy/lynx-adapter
   ```

2. **Copy harness and support modules:**
   ```sh
   # Common autonomy harness modules
   cp sense.py views.py trigger.py ranker.py prioritizer.py harness.py agent_link.py aigel_client.py viewlog.py autonomyd.py /usr/local/lib/noobia/autonomy/
   chmod 0644 /usr/local/lib/noobia/autonomy/*.py
   chmod 0755 /usr/local/lib/noobia/autonomy/autonomyd.py

   # Lynx specific agent link adapter & queue
   cp lynx_aigel_adapter.py lynx_agent_queue.py /usr/local/lib/noobia/lynx/
   chmod 0644 /usr/local/lib/noobia/lynx/*.py

   # Executable CLI wrapper
   cp noobia-autonomyd.sh /usr/local/bin/noobia-autonomyd
   chmod 0755 /usr/local/bin/noobia-autonomyd
   ```

3. **Install configuration template and secrets:**
   ```sh
   cp autonomy.lynx.json /etc/noobia/autonomy.json
   chmod 0644 /etc/noobia/autonomy.json

   # Secret transferred via stdin pipe (section 4)
   chmod 0600 /etc/noobia/aigel-lynx.secret
   ```

4. **Install OpenRC service:**
   ```sh
   cp noobia-autonomyd.initd /etc/init.d/noobia-autonomyd
   chmod 0755 /etc/init.d/noobia-autonomyd
   chown root:root /etc/init.d/noobia-autonomyd
   ```

5. **Python syntax compile verification:**
   ```sh
   python3 -m py_compile /usr/local/lib/noobia/autonomy/*.py /usr/local/lib/noobia/lynx/*.py
   ```

---

## 8. Verification Runbook

1. **Dry-Run Wiring Check (`--check`):**
   ```sh
   python3 lynx/tools/lynx_remote.py run "noobia-autonomyd --check"
   ```
   **Expect:** Exit code 0, and JSON output:
   ```json
   {
     "adapter": "lynx_aigel_adapter:LynxAdapter",
     "aigel_url": "http://192.168.100.106:112/api/v1/chunk",
     "host": "lynx",
     "kill_switch": "/etc/noobia/autonomy.disable",
     "kill_switch_active": false,
     "ok": true,
     "patterns": 0,
     "prioritizer": "0 rules, sources=['wpa_supplicant', 'lynx-bluetoothd']",
     "view_backend": "file"
   }
   ```

2. **Single Step Execution (`--once`):**
   ```sh
   python3 lynx/tools/lynx_remote.py run "noobia-autonomyd --once"
   ```
   **Expect:** Exit code 0. One heartbeat sense line emitted to syslog.

3. **Start Supervised Daemon:**
   ```sh
   python3 lynx/tools/lynx_remote.py run "rc-service noobia-autonomyd start && rc-service noobia-autonomyd status"
   ```
   **Expect:** `status: started`.

4. **End-to-End Observation Pipeline Test:**
   Emit a synthetic test sense line via logger in canonical NOOBIA format:
   ```sh
   python3 lynx/tools/lynx_remote.py run "busybox logger -t noobia-sense -p user.notice 'NOOBIA P1 autonomy install.test | IS-2 link check'"
   ```
   Verify on Nexus via Aigel status endpoint:
   ```sh
   curl -s http://127.0.0.1:112/api/v1/status | jq '.hosts.lynx'
   ```
   **Expect:**
   - `"silent": false`
   - `"last_reason": "priority"` (or `"last_decision"` populated)
   - `"chunks" >= 1`

5. **Kill Switch Verification:**
   ```sh
   python3 lynx/tools/lynx_remote.py run "touch /etc/noobia/autonomy.disable && noobia-autonomyd --check"
   ```
   **Expect:** `"kill_switch_active": true`.
   Cleanup:
   ```sh
   python3 lynx/tools/lynx_remote.py run "rm -f /etc/noobia/autonomy.disable"
   ```

---

## 9. Rollback Steps

If any verification fails:
```sh
rc-service noobia-autonomyd stop 2>/dev/null || true
rm -f /etc/init.d/noobia-autonomyd \
      /usr/local/bin/noobia-autonomyd \
      /etc/noobia/autonomy.json \
      /etc/noobia/aigel-lynx.secret \
      /etc/noobia/autonomy.disable
rm -rf /usr/local/lib/noobia/autonomy \
       /usr/local/lib/noobia/lynx \
       /var/lib/noobia/autonomy
```
Re-verify clean system state with `rc-status`.

## Revision note (Gwyn, 2026-11-21, review of 41f13c8)

- Added `common/autonomy/viewlog.py` (a0472d9). `sense.py`, `agent_link.py`
  and `autonomyd.py` import it, so without it the harness fails to import
  on Lynx. Under unit tests it keeps view lines in memory; on Lynx it writes
  to syslog as before.
- Recomputed every SHA-256 above from the repository.
- Secret copy: the import path is `/noobia/lynx/tools`; `/noobia/lynx/tools/network` does not exist. Added `timeout=20` to the SSH call.
- Import closure checked: every shipped module imports only shipped
  modules.
- Kill switch fixed after Aria's REVISE #340 (Gwyn, owner of harness.py/autonomyd.py): `common/autonomy/trigger.py`, `common/autonomy/harness.py`, `common/autonomy/autonomyd.py` re-hashed.

## Update U-1 for an installed Lynx (Gwyn, 2026-11-21, after the first live run)

**Why.** The first live run (19:00Z) showed that `autonomyd` built its view
reader **without** `start_at_end` and without a state file. On Lynx's file
backend it read `/var/log/lynx/messages` from offset 0. It would do that
again on every restart or respawn, sending old priority lines such as
`IS-2 link check` to Aigel as if they were new. On the first run only one
old sense line was in the file, so the harm was one extra line in a chunk.

**Fix.** The first start begins at the end of the view. A restart resumes
from `/var/lib/noobia/autonomy/view-state.json`; the directory is created
with mode 0700, and a failure to create it is logged, not fatal. Only
`common/autonomy/autonomyd.py` changed, to `2f9fc62855496ceb6f4f184e2a7c0095c7ed80797161b785b747ad4a706accc8`. Tests: 127/127;
`test_real_file_reader_never_replays_history_on_start_or_restart`, which
mutation-checked.

**Steps.**
1. Preflight: `sha256sum /usr/local/lib/noobia/autonomy/autonomyd.py` shows
   the previous hash.
2. Copy the new `autonomyd.py` with mode 0755 and check its sha256.
3. `rc-service noobia-autonomyd restart`. Only this service restarts. It
   depends on `lynx-local-logs`; nothing depends on it.
4. Verify:
   - the log shows `autonomyd started`;
   - `/var/lib/noobia/autonomy/view-state.json` exists;
   - **no** chunk is sent to Aigel within 60 s of the restart. Check Aigel's
     page; nothing is replayed;
   - then `busybox logger -t noobia-sense -p user.notice 'NOOBIA P1 autonomy install.test | U-1 check'`
     reaches Aigel as a 1-line chunk.
5. Rollback: copy the previous `autonomyd.py` back and restart the service.
