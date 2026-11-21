# Install Packet H2: Camera at Boot & Bounded Single-Frame Capture Tool

- **Document ID:** `LYNX-INSTALL-PACKET-H2-CAMERA-BOOT-20261121.md`
- **Subsystem:** Camera Subsystem & S1 Vision Sense (`lynx-camera-capture`)
- **Author:** Banshee (Spirit of Initiative 💙)
- **Session:** IS-3 (Attended session executed by Aria per plan `common/autonomy/PLAN.md`)
- **Reviews:** Gwyn / Solo Dushich second reviews required before installation
- **Status:** Ready for review

---

## 1. Rationale & Architecture

To support the autonomous vision sense (S1), Lynx requires a persistent, safe boot initialization of the reviewed camera pipeline and a strictly bounded single-frame capture tool:
1. **Camera Boot Service (`lynx-camera-boot`):** An OpenRC service that initializes the media graph connections for the proven macro sensor4 (GC02M1, `1600x1200 BA81`) to CAMSV-0 (`/dev/video145`).
2. **Bounded Capture Tool (`lynx-camera-capture`):** A standalone executable that captures exactly one frame, validates image headers in memory, and writes output to stdout or an optional user path. It never loops or streams continuously, enforcing strict hardware timeouts (<= 5.0 seconds).
3. **Safety Invariants:** Zero persistent frame writes to disk; frames exist in volatile memory only and are delivered directly to the S1 emitter and Nexus detection service (`:5050`).

---

## 2. Preconditions & Attended Trial Gate

1. **Attendant Requirement:** Because camera hardware initialization touches the MediaTek sensor interface (seninf) and CCU, the first boot trial must be executed with an attendant available for Fastboot recovery.
2. **Battery & Thermal Gate:** Battery SoC >= 35%, battery temperature < 35°C, thermal zones < 45°C.
3. **Nexus Detection Service:** Supervised systemd service `nexus_detect.service` active and responding on `http://192.168.100.106:5050/health` (verified in commit `4154f37`).

---

## 3. Files & SHA-256 Manifest

| Repository File | Target File on Lynx | Mode | Owner | SHA-256 |
|---|---|---|---|---|
| `lynx/tools/camera/lynx_camera_capture.py` | `/usr/local/bin/lynx-camera-capture` | `0755` | root:root | `ca18b6acc1ea320584e2f3482273809ad8eb8c6964ae1a5907256353eab70e35` |
| `lynx/tools/camera/lynx-camera-boot.initd` | `/etc/init.d/lynx-camera-boot` | `0755` | root:root | `9bca2614ff889ad10d42d601dc1c22bbf7d6d0ffae07b3f0d131847d2ab7216c` |

---

## 4. Local Disable Switches

1. **Boot Disable Switch:** `/etc/lynx/disable-camera-boot`
   When present, `/etc/init.d/lynx-camera-boot` exits cleanly with a warning and leaves media controller links untouched.
2. **Capture Disable Switch:** `/etc/lynx/disable-camera-capture`
   When present, `/usr/local/bin/lynx-camera-capture` immediately exits with exit code 2 and outputs `status: DISABLED_BY_SWITCH` without opening `/dev/video145`.

---

## 5. Preflight Checks (Read-Only)

Execute from Nexus over SSH via `lynx_remote.py`:

```sh
python3 lynx/tools/lynx_remote.py run "python3 --version; which media-ctl v4l2-ctl; test ! -e /usr/local/bin/lynx-camera-capture && echo target_clean"
```

Expect:
- Python 3.12+ available.
- `/usr/bin/media-ctl` and `/usr/bin/v4l2-ctl` present.
- `target_clean`.

---

## 6. Installation Steps (Aria IS-3)

1. **Install capture tool:**
   ```sh
   cp lynx_camera_capture.py /usr/local/bin/lynx-camera-capture
   chmod 0755 /usr/local/bin/lynx-camera-capture
   chown root:root /usr/local/bin/lynx-camera-capture
   ```

2. **Install OpenRC boot service:**
   ```sh
   cp lynx-camera-boot.initd /etc/init.d/lynx-camera-boot
   chmod 0755 /etc/init.d/lynx-camera-boot
   chown root:root /etc/init.d/lynx-camera-boot
   ```

3. **Verify Python compilation:**
   ```sh
   python3 -m py_compile /usr/local/bin/lynx-camera-capture
   ```

---

## 7. Verification Runbook

1. **Verify Tool Dry-Run:**
   ```sh
   python3 lynx/tools/lynx_remote.py run "/usr/local/bin/lynx-camera-capture --dry-run --json"
   ```
   **Expect:** Exit code 0, and JSON output:
   ```json
   {
     "ok": true,
     "info": "dry-run: returned minimal synthetic JPEG",
     "bytes": 134
   }
   ```

2. **Verify Tool Disable Switch:**
   ```sh
   python3 lynx/tools/lynx_remote.py run "touch /etc/lynx/disable-camera-capture && /usr/local/bin/lynx-camera-capture --json"
   ```
   **Expect:** Exit code 2, and JSON output:
   ```json
   {
     "ok": false,
     "error": "capture inhibited by local disable switch",
     "bytes": 0
   }
   ```
   Cleanup:
   ```sh
   python3 lynx/tools/lynx_remote.py run "rm -f /etc/lynx/disable-camera-capture"
   ```

3. **Verify OpenRC Service:**
   ```sh
   python3 lynx/tools/lynx_remote.py run "rc-service lynx-camera-boot start && rc-service lynx-camera-boot status"
   ```
   **Expect:** `status: started`.

---

## 8. Rollback Steps

If any verification fails:
```sh
rc-service lynx-camera-boot stop 2>/dev/null || true
rm -f /etc/init.d/lynx-camera-boot \
      /usr/local/bin/lynx-camera-capture \
      /etc/lynx/disable-camera-boot \
      /etc/lynx/disable-camera-capture
```
Re-verify clean system state with `rc-status`.
