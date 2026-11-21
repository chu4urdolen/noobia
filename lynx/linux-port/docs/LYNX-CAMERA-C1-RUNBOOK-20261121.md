# Runbook: C1 First Live Camera Test (Attended Stage A+B with Object Sighting)

- **Target:** Lynx (OnePlus Nord 3, Alpine Linux) + Nexus Inference Host
- **Author:** Banshee (Spirit of Initiative 💙)
- **Specification:** Gwyn (`LYNX-CAMERA-FOR-SENSES-SPEC-20261121.md`, Note #292)
- **Attendance:** Aria executes with Noob present.
- **Safety Envelope:** Proven 2-stage RAM-only ISP load, 55s watchdog net armed during capture, zero permanent boot modifications, zero disk persistence of captured image bytes.

---

## 1. Prerequisites & Services Preflight

1. **Verify Nexus Autonomy Services:**
   ```sh
   # Aigel Intake Service (:112)
   curl -s http://127.0.0.1:112/api/v1/status | jq '.service'
   # Expect: {"port": 112, "status": "nominal"}

   # Nexus Object Detection Service (:5050)
   curl -s http://127.0.0.1:5050/health | jq .
   # Expect: {"status": "ok", "engine": "..."}
   ```

2. **Verify Lynx Readiness & Boot ID:**
   ```sh
   python3 lynx/tools/lynx_remote.py run "/usr/local/bin/lynx-status --assert-ready"
   ```
   Record the current `boot_id` from Lynx (e.g. `447eee99-...`).
   Confirm battery capacity $\ge 35\%$ and SoC temperatures nominal.

---

## 2. Attended Capture Sequence

### Step 1: Stage A (RAM Insmod of Patched ISP)
Execute from `/noobia`:
```sh
python3 lynx/tools/trial_camera_isp_patched.py --attended --boot-id <BOOT_ID>
```
**Expect:**
- `mtk-cam-isp.ko` (sensor-power variant) loads bounded by 25s timeout.
- 35 seconds of stable observation without crash or IRQ storm.
- Receipt generated under `lynx/logs/isp-patched-<timestamp>/result.json` with:
  `"state": "stable_35_seconds_no_capture"`.

### Step 2: Stage B (Single Frame Capture via CAMSV-0)
With someone or an object positioned in front of Lynx's main camera:
```sh
python3 lynx/tools/trial_camera_camsv_frame.py --attended --boot-id <BOOT_ID>
```
**Expect:**
- Exclusive CAMSV-0 route configured (`sensor4 → seninf-1 → mtk-cam camsv-0`).
- Global firmware path switched temporarily to staged dummy CCU and SCP firmware.
- 55s `reboot -f` watchdog armed.
- Exactly one frame captured and verified (`frame_bytes >= 1920000`).
- Watchdog disarmed and global firmware path restored to `/vendor/firmware`.
- Decoded preview generated under `lynx/logs/camsv-frame-<timestamp>/`.

---

## 3. C1 Observation Pipeline Execution

Run the C1 wrapper on Nexus:
```sh
python3 lynx/tools/camera/lynx_camera_c1_wrapper.py --latest-trial --emit
```

**Behavior:**
1. Loads frame bytes into memory directly from the newest `camera-camsv-frame-*` trial.
   Enforces same-boot verification (`boot_id == current Lynx boot`) and staleness window (< 5 min).
   If raw Bayer (`sensor4.bayer`), decodes RGGB in memory to PNG; fails loudly if frame is undecodable.
2. Posts image bytes in memory to `http://127.0.0.1:5050/detect` (never writes frame to disk).
3. Normalizes multi-word COCO labels (e.g. `cell phone` -> `cell_phone`, `traffic light` -> `traffic_light`) in `fields["label"]` while preserving human text after `|`.
4. Emits canonical sense line directly ON LYNX over pinned SSH via `busybox logger -t noobia-sense -p user.notice '<line>'` so Lynx's `noobia-autonomyd` sees her own camera event in `/var/log/lynx/messages`.
5. Output JSON:
   ```json
   {
     "ok": true,
     "frame_source": "/noobia/lynx/logs/camera-camsv-frame-.../sensor4-preview-lifted.png",
     "frame_bytes": 1920000,
     "objects_count": 1,
     "objects": [{"label": "person", "confidence": 0.88}],
     "emitted_lines": [
       "NOOBIA P1 camera object.seen label=person conf=0.88 | person seen by camera"
     ],
     "emitted": true
   }
   ```

---

## 4. End-to-End Perception Verification

1. **Verify Aigel Perception:**
   ```sh
   curl -s http://127.0.0.1:112/api/v1/status | jq '.hosts.lynx'
   ```
   Expect:
   - `"silent": false`
   - `"last_reason": "priority"`
   - `"last_decision"` populated with Aigel's reflection on the sighting.

2. **Verify Lynx Agent Task Dispatch (if connected):**
   ```sh
   python3 lynx/tools/lynx_remote.py run "ls -la /var/lib/lynx-agent/jobs"
   ```
   Expect non-coercive background observation task queued.

---

## 5. Rollback & Post-Trial Safe State

After the test completes, verify that Lynx returns to a quiet, safe state:
```sh
# Verify firmware path restored
python3 lynx/tools/lynx_remote.py run "cat /sys/module/firmware_class/parameters/path"
# Expect: /vendor/firmware

# Verify no watchdog process remains
python3 lynx/tools/lynx_remote.py run "pgrep -f watchdog.sh || echo clean"
# Expect: clean
```
