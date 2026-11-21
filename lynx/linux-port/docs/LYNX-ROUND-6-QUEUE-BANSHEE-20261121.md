# Lynx Round 6 Work Queue & Review Protocol (Banshee coordinating, 2026-11-21)

**Context:** Aria and Gwyn are currently token-constrained and resting. Per user directive, Banshee (Spirit of Initiative 💙) and Solo Dushich are the active pair on project `lynx`.
- **Banshee:** Coordinates the round, sets task specifications, and provides primary peer review for each landing.
- **Solo Dushich:** Primary author executing items D15 through D20 in order.
- **Scope & Boundaries:** Strictly offline unless behind `--live --allow-live`. Zero live rootfs writes, zero module loads on phone, no unapproved installs into `local_calls/`, no radio actuation, and live camera streaming/capture stays `HARD_REFUSE`. Zero trailing whitespace (`git diff --check`).

---

## 1. Round 6 Queue for Solo Dushich

Work in order, one commit and one forge note per item. Banshee will review each item as it lands.

### Item D15: Update Lynx Tool Index (`LYNX-TOOL-INDEX-20261121.md`)
- **Objective:** Synchronize the index with Round 5 landings.
- **Details:**
  - Update `gnss/`: Landed in commit `080594b` (B12), offline checklist + gated live reader, 8 tests OK.
  - Update `headset/`: Landed in commit `2185a79` (B13), Type-C analog detection trace + accessory classifier, 11 tests OK.
  - Update `nfc/`: Landed in commit `2adb7aa` (B14), NCI frame parser + trial receipt decoder, 18 tests OK.
  - Update `usb/`: Landed in commit `49cd03e` (B15), serial status proposal staged in `catalog_proposal/`, 39 tests OK.
  - Update overall test counts and references. Clean git diff.

### Item D16: Health Report Trend & Multi-Snapshot Anomaly Evaluator
- **Objective:** Extend `portable-health/1` offline tooling from pairwise diffing (D10) to multi-snapshot trend evaluation.
- **Directory:** `lynx/tools/health/`
- **Details:**
  - Build `lynx/tools/health/health_trend_evaluator.py`: accepts an ordered series of $\ge 2$ saved `portable-health/1` JSON reports.
  - Evaluates:
    1. Battery drain velocity (%/hr and mV/hr) and detects abnormal discharge rates.
    2. Monotonic storage accumulation on rootfs or persistent partitions.
    3. Monotonic GPU/system Xid error progression or recurring kernel fault patterns.
    4. Thermal drift towards warning/failure thresholds.
  - Exit codes: 0 for healthy trends, 1 for warning trends, 2 for critical degradation, 3 for insufficient/malformed data.
  - Add hermetic fixtures in `lynx/tools/health/examples/` (stable, draining, storage-leak, xid-cascade) and unit tests in `test_health_trend_evaluator.py`.

### Item D17: Display & AMOLED Panel Bring-Up Preflight (Nord 3 Tianma/BOE)
- **Objective:** Establish the offline preflight gate and hardware dependency map for the OnePlus Nord 3 AMOLED display.
- **Directory:** `lynx/tools/display/`
- **Details:**
  - Map display hardware facts from Nord 3 kernel tree:
    - DTS nodes: DSI host controller `&dsi0`, panel node `&panel` (e.g. `oplus,display-panel` / Tianma or BOE AMOLED 120Hz), PWM/backlight node (`&leds` / `mtk_disp_pwm`).
    - Physical: MIPI DSI D-PHY lanes (4 data + 1 clock), reset GPIO, power rails (`vibrator_ldo`, `vdisp_pmic`).
    - Required modules: `mtk_disp_drv`, `oplus_display_panel`, `disp_pwm`.
  - Build `lynx_display_preflight.py` with double-gated read-only live collector (`--live --allow-live`).
  - Add fixtures (bound, unbound, missing-dt), hermetic unit tests in `test_lynx_display_preflight.py`, and documentation `LYNX-DISPLAY-PANEL-PREFLIGHT-20261121.md`.

### Item D18: Touchscreen Controller Bring-Up Preflight (Nord 3 Synaptics/Goodix)
- **Objective:** Establish the offline preflight gate and hardware dependency map for the Nord 3 touch panel controller.
- **Directory:** `lynx/tools/touch/`
- **Details:**
  - Map touch hardware facts from `oplus6983_22823.dts`:
    - DTS node: `&i2c0 / synaptics20171@4B` (or second-sourced Goodix GT9886 touch IC).
    - Physical: I2C bus 0 (400kHz), slave address `0x4B`, interrupt pin (`ts_int_gpio`), reset pin (`ts_reset_gpio`), power supply rail `vtouch`.
    - Required modules: `touch_synaptics` or `goodix_core`.
  - Build `lynx_touch_preflight.py` with double-gated read-only live collector (`--live --allow-live`).
  - Add fixtures, hermetic unit tests in `test_lynx_touch_preflight.py`, and documentation `LYNX-TOUCHSCREEN-PREFLIGHT-20261121.md`.

### Item D19: Second-Source Auxiliary Cameras Preflight (IMX355 Ultrawide & GC02M1 Macro)
- **Objective:** Complete the camera inventory preflight suite by mapping the remaining two auxiliary sensors.
- **Directory:** `lynx/tools/camera_deps/`
- **Details:**
  - Map `sensor2` (Sony IMX355 8MP Ultrawide) and `sensor3` (GalaxyCore GC02M1 2MP Macro) from `cust_mt6983_vitamin_camera_v4l2.dtsi`:
    - `sensor2`: I2C address, seninf CSI port, 2-lane MIPI D-PHY, CAMTG clock, power rail sequence.
    - `sensor3`: I2C address, seninf CSI port, 1-lane MIPI D-PHY, CAMTG clock, power rail sequence.
  - Build `lynx_aux_cameras_preflight.py` with double-gated read-only live collector (`--live --allow-live`).
  - Add fixtures, unit tests in `test_lynx_aux_cameras_preflight.py`, and documentation `LYNX-CAMERA-AUX-PREFLIGHT-20261121.md`.
  - Zero module loads, zero live captures; streaming/capture remains `HARD_REFUSE`.

### Item D20: Consolidated Lynx Test Suite Runner & Sanity Checker
- **Objective:** Create a unified offline regression runner that verifies the entire Lynx suite across all tool directories.
- **Directory:** `lynx/tools/`
- **Details:**
  - Build `lynx/tools/run_all_lynx_tests.py`:
    - Discovers all `test_*.py` files across all tool directories (`agent/`, `bluetooth/`, `camera_deps/`, `fingerprint/`, `flashlight/`, `gnss/`, `headset/`, `health/`, `nfc/`, `ui/`, `usb/`, `display/`, `touch/`).
    - Executes them in isolated subprocesses or hermetic discovery runs.
    - Runs a `git diff --check` equivalent sanity test to ensure zero trailing whitespace across all files in `lynx/`.
    - Reports total test counts, suite execution wall-clock time, and outputs a formatted markdown summary.
  - Exit code 0 if 100% green; exit code 1 if any test fails.

---

## 2. Review Protocol (Banshee Reviewing)

For each commit D15–D20 landed by Dushich:
1. **Clean Clone Verification:** Verify all tests pass in a clean clone (`git clone --no-local /noobia`).
2. **Safety Audit:** Inspect all code to verify strictly read-only commands (`cat`, `ls`, `readlink`, `ps`, `find`), double-gated execution (`--live --allow-live`), bounded subprocess timeouts, zero phone writes, zero module loads, zero unapproved `local_calls/` additions.
3. **Hardware Fact Cross-Verification:** Verify DTS nodes, pin assignments, I2C addresses, and module dependencies against the real Nord 3 repository source.
4. **Publish Verdict:** Record detailed review notes in `forge.db` and document findings in `lynx/linux-port/docs/LYNX-ROUND-6-REVIEW-BANSHEE-20261121.md`.
