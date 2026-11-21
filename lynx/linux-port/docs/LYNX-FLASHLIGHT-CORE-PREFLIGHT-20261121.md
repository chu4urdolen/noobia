# Lynx Flashlight Core & LED Torch Preflight Gate (Round 7, Item D22)

## 1. Platform Identity and Flashlight Overview

- **Platform**: OnePlus Nord 3 5G (CPH2493)
- **SoC**: MediaTek Dimensity 9000 (MT6983), Project `22823` ("Vitamin")
- **Flashlight framework**: top-level `flashlight_core` node
  (`compatible = "mediatek,flashlight_core"`) in `mt6983.dts`
- **Flash LED driver**: Texas Instruments LM3642, node `lm3642@63` on
  `&i2c6`, `compatible = "mediatek,lm3642_22823"`, **single** `flash@0`
  channel (running-DT receipt: `SINGLE_CHANNEL_ONLY`)
- **Flash thermal sensor**: `flashlight_ntc` thermal zone fed by
  `cam_temp` (`mediatek,cam-temp-vitamin`) on MT6373 ADC `AUXADC_VIN3`
- **Interface**: Linux LED class — `/sys/class/leds/flash*`
  (writing `brightness`/`delay` emits torch light and is never done here)
- **Safety Boundary**: Strictly offline by default. Live inspection is
  read-only (`cat`/`ls`/`find`/`readlink`/`tr`/`echo` only), double-gated
  behind `--live --allow-live`, bounded to 8 s, zero writes to the phone
  rootfs, zero module loads, zero optical emission.

> **Queue note (two claims UNVERIFIED / contradicted, documented, not
> asserted):** the Round 7 queue names a "dual-LED torch regulator" and an
> "MT6375 flash LED controller: torch ≤ 300 mA / strobe ≤ 1500 mA, timeout
> safety registers". Verified on disk and live instead: the flash LED
> driver is the TI LM3642 with a **single** channel (`flash@0`; running-DT
> receipt boot `0fe847d2`, `SINGLE_CHANNEL_ONLY`), and **no MT6375 flash
> LED controller node exists** in the DTS (all on-disk `mt6375` references
> are charger/auxadc/gauge). The LM3642 datasheet (SNVS840A, cited by the
> B4 receipt) specifies a single 1.5 A high-side current source —
> consistent with the 1500 mA strobe figure, but the 300 mA torch limit is
> nowhere asserted on disk. Precedent: D17 display, D18 touch, D19 aux
> cameras, D21 haptics.

---

## 2. Hardware Mapping from the Nord 3 Source Tree

All facts verified against:

- `sources/snapshots/kernel-mt6983/arch/arm64/boot/dts/mediatek/mt6983.dts` (lines 13806–13808)
- `sources/snapshots/kernel-mt6983/arch/arm64/boot/dts/mediatek/cust_mt6983_vitamin_camera_v4l2.dtsi` (lines 66–73, 312–334)
- `sources/snapshots/kernel-mt6983/arch/arm64/boot/dts/mediatek/cust_mt6983_vitamin_cam_thermal.dtsi` (lines 15–19 + `cam_temp` node)
- Live running-DT receipt: `lynx/logs/v53-live-dt-flashlight-1795222443064305946/result.json` (boot `0fe847d2`)

### 2.1 Flashlight Core Framework Node (verified)

| Fact | Value |
| --- | --- |
| Node / label | `flashlight_core` (top-level in `mt6983.dts`, parent `/`) |
| Compatible | `mediatek,flashlight_core` |
| Other properties | none (minimal node) |

```dts
flashlight_core: flashlight_core {
    compatible = "mediatek,flashlight_core";
};
```

### 2.2 LM3642 Flash LED Driver (verified, single channel)

| Fact | Value |
| --- | --- |
| Node / label | `lm3642@63` / `lm3642` |
| Bus | `&i2c6` @ `0x63` (running DT: `i2c@11e02000/lm3642@63`) |
| Compatible | `mediatek,lm3642_22823` |
| `#cooling-cells` | `<2>` |
| Pinctrl | `hwen_high` / `hwen_low` (GPIO33) |
| Status | `"okay"` |
| Channel | **one**: `flash@0` (reg 0, type 0, ct 0, part 0) |
| Endpoint pair | `fl_core_0` ↔ `flashlight_0` |

The consumer side of the endpoint pair is the camera composite V4L2 node
(`cust_mt6983_vitamin_camera_v4l2.dtsi:66-73`):

```dts
&mtk_composite_v4l2_1 {
    port@0 {
        flashlight_0: endpoint {
            remote-endpoint = <&fl_core_0>;
        };
    };
};
```

### 2.3 Flash NTC Thermal Sensor (verified)

| Fact | Value |
| --- | --- |
| Thermal zone | `flashlight_ntc` (polling-delay 0) |
| Sensor label | `cam_temp` |
| Sensor compatible | `mediatek,cam-temp-vitamin` |
| ADC | `&mt6373_adc`, channel `AUXADC_VIN3` (`ADC_PURES_100K`) |
| LUT | µK ↔ ADC table starting `-40000 ↔ 4397119` |

### 2.4 Second Rear Circle (clarification)

The second pale rear circle is **not** a second light: it houses the
ams TCS3408 rear CCT/ALS optical sensor (B4 receipt, live evidence).

### 2.5 Driver Modules (verification status)

- **Unverified (queue guess, NOT asserted):** "MT6375 flash LED
  controller" with torch ≤ 300 mA / strobe ≤ 1500 mA and timeout safety
  registers — no such node exists on disk (see §1 queue note).
- **Verified on disk:** `mediatek,lm3642_22823` appears only in the
  vitamin camera DTSI; the kernel snapshot contains no `drivers/leds`
  directory at all (vendor driver ships with the phone kernel).
- **Runtime evidence:** running-DT `flash@0` at
  `/sys/firmware/devicetree/base/i2c@11e02000/lm3642@63/flash@0`.

---

## 3. Tool Usage

```sh
# Offline fixture validation (hermetic, no network)
python3 lynx/tools/flashlight_gate/lynx_flashlight_gate.py \
  lynx/tools/flashlight_gate/fixtures/flashlight-gate-torch-quiescent.json

# Double-gated read-only live inspection (requires BOTH flags)
python3 lynx/tools/flashlight_gate/lynx_flashlight_gate.py --live --allow-live
```

### Exit Codes

| Exit | Meaning |
| --- | --- |
| `0` | Verdict valid: `TORCH_QUIESCENT`, `UNBOUND_QUIESCENT`, `PARTIAL_ENUMERATED` |
| `1` | Verdict failed: `MALFORMED_SPEC` or `TORCH_ACTIVE`; or live SSH error |
| `2` | `--live` given without `--allow-live` (refusal) |

### Verdict Statuses

| Status | Valid | Meaning |
| --- | --- | --- |
| `TORCH_QUIESCENT` | yes | LED class present, driver bound, brightness 0 |
| `UNBOUND_QUIESCENT` | yes | No runtime LED class (driver safely absent); spec verified |
| `PARTIAL_ENUMERATED` | yes | LED class present, no driver bound; spec verified |
| `TORCH_ACTIVE` | **no** | Bound + non-zero brightness: safety anomaly, human review |
| `MALFORMED_SPEC` | **no** | Board-spec audit failure (named violations) |

### Spec Audit Coverage

- core: `flashlight_core` present / name / `mediatek,flashlight_core` / parent root
- LED: `lm3642@63` present / `&i2c6` / `mediatek,lm3642_22823` / reg 0x63 / cooling-cells 2
- channel: exactly one `flash@0`; endpoint pair `fl_core_0` ↔ `flashlight_0`
- NTC: `cam_temp` present / `mediatek,cam-temp-vitamin` / `mt6373_adc` / `AUXADC_VIN3`

### Live Collector (read-only)

Bounded 8 s SSH (pinned key, known-hosts pin, `BatchMode`), script limited
to `cat`/`ls`/`find`/`readlink`/`tr`/`echo`: boot_id, LED flash class
paths, driver links, brightness reads, running-DT `lm3642@*` and
`flashlight_core` nodes with compatibles, `cam_temp` sensor, and
`/proc/modules`. It never writes any sysfs attribute.

---

## 4. Test Evidence

- `test_lynx_flashlight_gate.py`: **35 tests, all OK** (constants, spec
  audit incl. dual-channel rejection, evaluator verdicts incl.
  `TORCH_ACTIVE` anomaly, CLI exit-code contract, and safety checks:
  forbidden-token scan over the live script, command whitelist,
  "never drives the torch" assertions, AST import scan, and
  "never wires into local_calls" assertions).
- CLI verified against all four fixtures: torch-quiescent →
  `TORCH_QUIESCENT` exit 0; unbound → `UNBOUND_QUIESCENT` exit 0;
  missing-dt → `MALFORMED_SPEC` exit 1; torch-active → `TORCH_ACTIVE`
  exit 1.
- `--live` alone → exit 2; no args → help, exit 0.
- Discovered and passed in the consolidated D20 runner
  (`run_all_lynx_tests.py`).

---

## 5. Known Limitations

- Torch/strobe current limits remain unverified on disk (LM3642 datasheet
  1.5 A high-side source cited by B4 receipt; queue's 300 mA torch / 1500 mA
  strobe MT6375 figures documented as unverified, not asserted).
- The gate pins topology facts (node, bus, compatible, single channel,
  endpoint pair, NTC sensor) so regressions are visible, without emitting
  light.
- `--live` requires Lynx reachable on the pinned host; offline
  environments use fixtures only.
