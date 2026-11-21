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

### Step 1: Stage A (prepare the camera stack in RAM)
Run from `/noobia`. Aria used this successfully in the first live test,
2026-11-21, forge lynx #350:
```sh
python3 lynx/tools/prepare_camera_camsv.py --status                  # read-only readiness check first
python3 lynx/tools/prepare_camera_camsv.py --execute --attended
```
**Expect:**
- It loads the stock and pipeline camera module prefixes and the patched ISP
  (the sensor-power variant). The ISP stays stable for 35 s with no IRQ storm.
- The CAMSV route is linked.
- A receipt is written to `lynx/logs/camera-prepare-<ns>/result.json` with
  `"state": "prepared_no_stream"`.

Do **not** use the older `trial_camera_isp_patched.py --attended --boot-id …`
line. It needs `--execute --with-sensor-power` and stops safely without the
camera prefix, which is what happened at the start of the first test.

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


## Findings from the first live test (2026-11-21, Gwyn, forge lynx #357, #358)

- **Cat** (real frame, 0.76): the whole chain worked up to Aigel. Aigel chose
  quiet because her prompt read "the Noob" as the human. Fixed in 6e87471, and
  aigel_intake was restarted at 19:45:28Z. There has been **no P1 sighting
  since the fix**, so Aigel → adapter → agent and the ranker repeat are
  still unproven.
- **Dog (twice) and cup**: honest `objects=0`, nothing invented. The frames
  show:
  - the **whole image rotated 90°**, because Lynx's sensor is mounted
    sideways;
  - focus that is **soft** at close range;
  - a strong **green cast**;
  - pictures shown on **screens** with glare.

  Offline re-runs: the cup is detected only after rotating 270° (cup 0.51).
  The cat is found at 0° (0.76) and at 270° (0.69).
- Next session:
  - the wrapper detects on an upright frame (rotation, white balance;
    Banshee);
  - cat repeat, to see Aigel's message reach Lynx's agent, then the ranker
    path;
  - a blank-wall negative;
  - printed pictures at 30–50 cm.
