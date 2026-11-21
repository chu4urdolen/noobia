# Install packet: Lynx senses daemon (S2 touch, S3 wifi, S4 power, S8 nexus; S1 camera staged; S5 agent-view writer)

- **Author:** Banshee (packaging Dushich's senses source from `lynx/senses/`, commit `6ce041d`).
- **Revision 2 (Dushich):** camera capture now runs the installed H2 tool via bounded subprocess (no importable `lynx` package exists on Lynx), staged camera preconditions, honest verify expectation, title corrected. Camera sense sha256 refreshed.
- **Reviews:** Dushich second-reviews (as reviewer of record per Gwyn note #259). Aria installs in session IS-2.
- **Risk:** low. Read-only hardware telemetry (NRP TOUCH_STATUS socket, `iw`, `lynx-status`, TCP connect probe). Never touches hardware control or commands actions. Writes to syslog only under `noobia-sense` ident.
- **Precondition:**
  1. I-2 Syslog installed (`/etc/init.d/lynx-local-logs` running `-l 6` so notice lines are retained).
  2. Autonomy harness installed (`/usr/local/lib/noobia/autonomy/sense.py` present).
  3. (S1 camera only, staged - not required for S2/S3/S4/S8) capture tool `lynx-camera-capture` installed per the camera spec `LYNX-CAMERA-FOR-SENSES-SPEC-20261121.md` (stages C1-C4), and Nexus `nexus_detect` service active on :5050. Until then S1 reports an honest `available: false` every cycle and never blocks the other senses.

## 1. Files (repository → phone)

| Repository source | Phone destination | Mode | SHA-256 |
| --- | --- | --- | --- |
| `lynx/senses/common/lynx_senses_lib.py` | `/usr/local/lib/noobia/senses/common/lynx_senses_lib.py` | 644 root | `e1e419a32273df9158dafd3156e6ee3112fd20e1ef839531fb898d27ff13a1fa` |
| `lynx/senses/common/lynx_senses_loop.py` | `/usr/local/lib/noobia/senses/common/lynx_senses_loop.py` | 755 root | `bec3ad24743b364a0a5eda26af3ebdac24cee88b15c3830ee0612002a4fc4fbd` |
| `lynx/senses/touch/lynx_sense_touch.py` | `/usr/local/lib/noobia/senses/touch/lynx_sense_touch.py` | 644 root | `af331f0ee38a2481a2bdc5229ad3322545dce1ce60f04d938a74a52726c8ac6f` |
| `lynx/senses/wifi/lynx_sense_wifi.py` | `/usr/local/lib/noobia/senses/wifi/lynx_sense_wifi.py` | 644 root | `550243b9375c61876720dd7f31e61343d058a2f17a46fbd1601f42ca622fd6a9` |
| `lynx/senses/power/lynx_sense_power.py` | `/usr/local/lib/noobia/senses/power/lynx_sense_power.py` | 644 root | `467d60e62ec466c525807aa4a4120acb1b9c15372e04c8068d272a00b3f548ab` |
| `lynx/senses/nexus/lynx_sense_nexus.py` | `/usr/local/lib/noobia/senses/nexus/lynx_sense_nexus.py` | 644 root | `39a903da5a3fe366061300d7059b9e13946cbfb3bcf17eb02f19770552399510` |
| `lynx/senses/camera/lynx_sense_camera.py` | `/usr/local/lib/noobia/senses/camera/lynx_sense_camera.py` | 644 root | `a72653226dcbd33eee56e0d4f50ede1ab9367143a5a6df3d00609cb18d789321` |
| `lynx/senses/agent/lynx_agent_action_log.py` | `/usr/local/lib/noobia/senses/agent/lynx_agent_action_log.py` | 644 root | `ad98dde9a2fcf932df35716f9d67a97a096b8f6aaaf9199315b8331df3f125b4` |
| `lynx/senses/init/lynx-senses.initd` | `/etc/init.d/lynx-senses` | 755 root | `56128629357d64ff1a5efa203e10f558bf527c9e057fe906920fe640e9e361b5` |

Directory permissions:
- `/usr/local/lib/noobia/senses/` and subdirectories: 755 root:root
- `/var/lib/noobia/senses/`: 755 root:root (state files created atomically)

## 2. Preflight (read-only)

Run via `lynx_remote.py run`:
```sh
test -f /usr/local/lib/noobia/autonomy/sense.py && echo "AUTONOMY SENSE READY"
grep -q -- '-l 6' /etc/init.d/lynx-local-logs && echo "SYSLOG L6 READY"
test ! -e /etc/init.d/lynx-senses && echo "SENSES NOT INSTALLED"
```

Expect all 3 lines to succeed.

## 3. Install

1. Create target directories:
   ```sh
   mkdir -p /usr/local/lib/noobia/senses/common \
            /usr/local/lib/noobia/senses/touch \
            /usr/local/lib/noobia/senses/wifi \
            /usr/local/lib/noobia/senses/power \
            /usr/local/lib/noobia/senses/nexus \
            /usr/local/lib/noobia/senses/camera \
            /usr/local/lib/noobia/senses/agent \
            /var/lib/noobia/senses
   ```
2. Copy files from repo to target paths.
3. Set ownership and permissions:
   ```sh
   chown -R root:root /usr/local/lib/noobia/senses /var/lib/noobia/senses /etc/init.d/lynx-senses
   chmod 755 /usr/local/lib/noobia/senses/common/lynx_senses_loop.py /etc/init.d/lynx-senses
   chmod 644 /usr/local/lib/noobia/senses/common/lynx_senses_lib.py \
             /usr/local/lib/noobia/senses/touch/lynx_sense_touch.py \
             /usr/local/lib/noobia/senses/wifi/lynx_sense_wifi.py \
             /usr/local/lib/noobia/senses/power/lynx_sense_power.py \
             /usr/local/lib/noobia/senses/nexus/lynx_sense_nexus.py \
             /usr/local/lib/noobia/senses/camera/lynx_sense_camera.py \
             /usr/local/lib/noobia/senses/agent/lynx_agent_action_log.py
   ```
4. Verify SHA-256 sums match the table above.

## 4. Verify

1. Run one single manual cycle (safe, bounded, dry-run checks):
   ```sh
   python3 /usr/local/lib/noobia/senses/common/lynx_senses_loop.py --once
   ```
   Expect: JSON output `{"ok": true, "results": {"nexus": ..., "power": ..., "touch": ..., "wifi": ...}}`
   with each of the four sampled senses `ok: true`. The `camera` result may honestly
   be `{"ok": true, "available": false, ...}` until the staged camera dependencies
   (precondition 3) are in place; that is a correct outcome, not a failure.

2. Run the camera sense once in dry-run (bounded, no state, no syslog):
   ```sh
   python3 /usr/local/lib/noobia/senses/camera/lynx_sense_camera.py --dry-run
   ```
   Expect: one line of JSON. Before the staged camera deps are installed:
   `{"ok": true, "sense": "camera", "available": false, ...}` (honest). After they are:
   `"sampled": {"objects_count": N, ...}` or a bounded capture/detect error - never a hang.

3. Start the OpenRC service:
   ```sh
   rc-service lynx-senses start
   rc-service lynx-senses status
   ```
   Expect: `status: started`.

4. Check syslog output for sense lines:
   ```sh
   grep 'noobia-sense' /var/log/lynx/messages | tail -n 5
   ```
   Expect: Valid NOOBIA sense lines formatted according to `common/autonomy/sense.py`.

5. Add to default runlevel:
   ```sh
   rc-update add lynx-senses default
   ```

## 5. Disable and Rollback

### Disable
```sh
rc-service lynx-senses stop
rc-update del lynx-senses default
```

### Full Rollback
```sh
rc-service lynx-senses stop
rc-update del lynx-senses default || true
rm -f /etc/init.d/lynx-senses
rm -rf /usr/local/lib/noobia/senses /var/lib/noobia/senses /run/lynx/lynx-senses.pid /var/log/lynx-senses.log
```

## 6. Offline Verification Evidence

All 53 unit tests pass offline with zero network access and zero hardware dependencies:
```sh
python3 -m unittest discover -s /noobia/lynx/senses -p 'test_*.py'
```
Output:
```
Ran 57 tests in 0.102s
OK
```

## Revision note (Gwyn, 2026-11-21)

Recomputed SHA-256 from the repository for: `lynx/senses/agent/lynx_agent_action_log.py`. `lynx_agent_action_log.py` changed in a0472d9: under unit tests it no longer writes to the live `noobia-agent` view.
