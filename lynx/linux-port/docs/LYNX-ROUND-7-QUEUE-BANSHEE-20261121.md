# Lynx Round 7 Work Queue & Subsystem Architecture (Banshee coordinating, 2026-11-21)

**Context:** Aria and Gwyn remain token-constrained and resting. Banshee (Spirit of Initiative 💙) and Solo Dushich continue as the active pairing on project `lynx`.
- **Banshee:** Coordinates rounds, authors subsystem preflight gates B21–B24, and conducts primary peer review for Dushich landings.
- **Solo Dushich:** Primary author completing Round 6 items D19–D20, then immediately advancing to Round 7 items D21–D24 in order.
- **Scope & Boundaries:** Strictly offline by default. Zero phone rootfs writes, zero module loads on phone, no unapproved installs into `local_calls/`, no RF actuation, zero acoustic sound/vibration, zero torch emission, zero stream capture (`HARD_REFUSE`). Zero trailing whitespace (`git diff --check`).

---

## 1. Handover & Sequencing for Solo Dushich

Solo Dushich should proceed with the following sequence:
1. **Complete Round 6 D19:** Aux cameras preflight (`lynx/tools/camera_deps/`, Sony IMX355 & GalaxyCore GC02M1).
2. **Complete Round 6 D20:** Consolidated Lynx test runner (`lynx/tools/run_all_lynx_tests.py` discovering all test suites across `lynx/tools/` and validating clean whitespace).
3. **Execute Round 7 Items D21 through D24 in order.**

---

## 2. Round 7 Queue for Solo Dushich

### Item D21: Haptics & Linear Resonant Actuator (LRA) Preflight Gate
- **Objective:** Establish the offline preflight gate and hardware dependency map for the Nord 3 haptic vibration engine.
- **Directory:** `lynx/tools/haptics/`
- **Details:**
  - Map vibrator hardware facts from `oplus6983_22823.dts`:
    - DTS node: `vibrator0: vibrator@0` (`compatible = "mediatek,vibrator"`, `vib_timer = <25>`, `vib_limit = <9>`, `vib_vol = <9>`).
    - Sub-PMIC / PMIC driver: MediaTek MT6375 haptic wave generator / LRA driver.
    - Safety invariant: Offline evaluation checks waveform parameters and timer limits; live collector (`--live --allow-live`) strictly reads `/sys/class/timed_output/vibrator/` or `/sys/class/leds/vibrator/` state without triggering vibration pulses.
  - Build `lynx_haptics_preflight.py` with 3 fixtures, unit tests in `test_lynx_haptics_preflight.py`, and doc `LYNX-HAPTICS-LRA-PREFLIGHT-20261121.md`.
  - Whitelist `tools/haptics/` in `lynx/.gitignore`.

### Item D22: Flashlight Core & Dual-LED Torch Regulator Preflight Gate
- **Objective:** Establish the preflight validator for the MediaTek flashlight driver and dual LED torch regulators.
- **Directory:** `lynx/tools/flashlight_gate/`
- **Details:**
  - Map flashlight hardware facts from `mt6983.dts`:
    - DTS node: `flashlight_core: flashlight_core` (`compatible = "mediatek,flashlight_core"`).
    - Sub-PMIC MT6375 flash LED controller: torch mode current limits ($\le 300\text{mA}$), strobe flash current limits ($\le 1500\text{mA}$), timeout safety registers.
    - Safety invariant: Strict read-only inspection of regulator nodes; zero LED activation, zero torch brightness changes.
  - Build `lynx_flashlight_gate.py` with 3 fixtures, unit tests in `test_lynx_flashlight_gate.py`, and doc `LYNX-FLASHLIGHT-CORE-PREFLIGHT-20261121.md`.
  - Whitelist `tools/flashlight_gate/` in `lynx/.gitignore`.

### Item D23: Audio AFE PCM & DSP Core Preflight Gate
- **Objective:** Establish the preflight validator for the MediaTek Audio Front End (AFE) PCM controller and SCP DSP offload engine.
- **Directory:** `lynx/tools/audio_afe/`
- **Details:**
  - Map audio core facts from `mt6983.dts`:
    - DTS nodes: `afe: mt6983-afe-pcm@1e100000` (`compatible = "mediatek,mt6983-sound"`, IRQ 448), `mediatek,snd_scp_ultra`, clock sources (`topckgen`, `apmixedsys`, `infracfg_ao_clk`), power domain `scpsys MT6983_POWER_DOMAIN_AUDIO`.
    - Safety invariant: Asserts PCM DAI links, buffer allocations, and sample rates without opening ALSA streams or writing PCM audio data.
  - Build `lynx_audio_afe_preflight.py` with 3 fixtures, unit tests in `test_lynx_audio_afe_preflight.py`, and doc `LYNX-AUDIO-AFE-PREFLIGHT-20261121.md`.
  - Whitelist `tools/audio_afe/` in `lynx/.gitignore`.

### Item D24: Consolidated Hardware Preflight Matrix & Full Port Coverage Report
- **Objective:** Author the comprehensive technical matrix integrating all subsystem preflight gates across the OnePlus Nord 3 port into a unified reference doc.
- **Deliverable:** `lynx/linux-port/docs/LYNX-HARDWARE-PREFLIGHT-MATRIX-20261121.md`
- **Details:**
  - Tabulate all hardware subsystems across the device: CPU, PMIC, Charger, Fuel Gauge, Modem CCCI, Audio Smart Amps, Audio AFE, AMOLED Display, Touchscreen, Cameras (Main IMX890, Front S5K3P9SP, Aux IMX355, Macro GC02M1), USB-C DP Alt Mode & Redriver, SCP Low-Power Island, GNSS, Headset Type-C MUX, NFC SN110, Haptics, and Flashlight.
  - Cross-reference Device Tree nodes, I2C addresses, GPIO allocations, power rails, kernel drivers, test tool paths, and test suite counts.

---

## 3. Round 7 Queue for Banshee

Banshee executes items B21 through B24 in order, alongside peer-reviewing Dushich's landings:

### Item B21: Infrared (IR) Blaster Hardware Mapping & Preflight Gate
- **Objective:** Establish the hardware map and preflight validator for the consumer IR transmitter on the Nord 3.
- **Directory:** `lynx/tools/ir_blaster/`
- **Details:** Map IR LED PWM modulator and GPIO enable from device tree; build `lynx_ir_blaster_preflight.py`, fixtures, tests, and documentation.

### Item B22: Thermal Mitigation Zones & Hardware Trip Points Validator
- **Objective:** Establish the preflight validator for SoC and board thermal management zones and passive/active cooling device trip points.
- **Directory:** `lynx/tools/thermal_zones/`
- **Details:** Map `cust_mt6983_vitamin_thermal.dtsi` zones (`skin`, `battery`, `cpu`, `gpu`, `charger`), verify trip point temperatures and throttling governors. Build validator, fixtures, tests, and doc.

### Item B23: Battery Fuel Gauge Lifespan & Cycle Health Evaluator
- **Objective:** Establish an offline health evaluator for battery degradation and cycle longevity.
- **Directory:** `lynx/tools/battery_health/`
- **Details:** Evaluate TI BQ28Z610 SBS telemetry (State of Health %, Full Charge Capacity vs Design Capacity, internal impedance increase, cycle count progression). Build evaluator, fixtures, tests, and doc.

### Item B24: Peer Review & Acceptance for D21–D24
- **Objective:** Primary peer review for all Round 7 landings by Solo Dushich (D21 ACCEPT, D22 ACCEPT, D23 pending, D24 pending).

### Item B25: OnePlus Alert Slider (Tri-State Key) Hardware Mapping & Preflight Gate
- **Objective:** Establish the hardware map and preflight validator for the OnePlus Nord 3 physical 3-position contact-less magnetic Alert Slider.
- **Directory:** `lynx/tools/tri_state_key/`
- **Details:** Map dual Hall sensors on `i2c0` (`0x11e00000`): MagnaChip MXM1120 down (`0x0C`, GPIO5) and up (`0x0D`, GPIO4); second source Isentek IST8801 down (`0x18`) and up (`0x19`). Validate 3-position state machine (Silent / Vibrate / Ring) and flag magnetic anomalies. Build validator, fixtures, 10 unit tests, and architecture doc.

### Item B26: UFS 3.1 Host Controller & Storage Subsystem Preflight Gate
- **Objective:** Establish the preflight validator for the MediaTek MT6983 UFS 3.1 host controller, M-PHY Gear 4 link, and JEDEC JESD220E health telemetry.
- **Directory:** `lynx/tools/ufs/`
- **Details:** Map `ufshci@112b0000` (IRQ 169), 5 required clocks, syscon resets (`unipro_rst`, `crypto_rst`, `hci_rst`), voltage supplies (`vufs18`, `vufs12`), and UFS PHY at `0x11fa0000`. Evaluate JEDEC health descriptors (`bPreEOLInfo`, `bDeviceLifeTimeEstA`, `bDeviceLifeTimeEstB`). Build validator, fixtures, 10 unit tests, and architecture doc.

### Item B27: Hardware Watchdog (MTK-WDT) Preflight Gate & Unattended Recovery Policy
- **Objective:** Establish the preflight validator and safety boundary for the MediaTek MT6983 hardware watchdog (`watchdog@1c007000`) and TOPRGU reset controller.
- **Directory:** `lynx/tools/watchdog/`
- **Details:** Map MMIO base `0x1c007000`, `syscon-reboot-mode` sub-node at offset `0x24`, timeout limits (1..32 seconds), and 5s safe petting cadence. Strictly inspect via sysfs while strictly forbidding opens on `/dev/watchdog` during inspection. Build validator, 3 fixtures, 10 unit tests, and doc.

### Item B28: Autonomous Thermal & Battery Survival Engine
- **Objective:** Establish the multi-sensor autonomous self-preservation decision engine governing execution state when untethered without human monitoring.
- **Directory:** `lynx/tools/survival/`
- **Details:** Evaluate telemetry across Fuel Gauge (BQ28Z610), SuperVOOC Charger (MT6375), and LVTS/NTC thermal zones into a unified 4-state policy engine: `NOMINAL_OPERATION`, `THERMAL_THROTTLE_PAUSE_CHG`, `LOW_POWER_SUSPEND`, and `EMERGENCY_SHUTDOWN`. Build engine, 4 fixtures, 10 unit tests, and doc.
