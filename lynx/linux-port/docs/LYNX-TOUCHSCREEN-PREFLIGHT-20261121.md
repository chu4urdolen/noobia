# Lynx Touchscreen Controller Bring-Up Preflight (Round 6, Item D18)

## 1. Platform Identity and Touch Overview

- **Platform**: OnePlus Nord 3 5G (CPH2493)
- **SoC**: MediaTek Dimensity 9000 (MT6983), Project `22823` ("Vitamin")
- **Touch Controller**: Synaptics S3908 (`compatible = "synaptics-s3908"`, `chip-name = "S3908"`), node `synaptics20171@4B` on `&i2c0` @ `0x4B`, 400 kHz I2C
- **Geometry**: 17 TX / 38 RX scan channels, up to 10 concurrent points, display coords 1440 x 3216 (curved panel, `touchpanel,curved-size = <45>`)
- **Reporting**: `report_rate_default = <60>` Hz in the `S3908 { }` sub-node; game mode and gesture-mask features present
- **Safety Boundary**: Strictly offline by default. Live inspection is
  read-only (`cat`/`ls`/`find`/`readlink`/`tr`/`echo` only), double-gated
  behind `--live --allow-live`, bounded to 8 s, zero writes to the phone
  rootfs, zero module loads, zero touch samples or injections.

> **Queue note:** the Round 6 queue named the controller "Synaptics/Goodix"
> and guessed driver modules `touch_synaptics` / `goodix_core`. The board DTS
> verifies the controller is a **Synaptics S3908**; Goodix GT9886 appears
> only in other projects' dtsi files, not in `oplus6983_22823.dts`. The
> guessed module names are not asserted (see §2.5).

---

## 2. Hardware Mapping from the Nord 3 Source Tree

All facts verified against:

- Board DTS: `sources/snapshots/kernel-mt6983/arch/arm64/boot/dts/mediatek/oplus6983_22823.dts`

### 2.1 I2C-0 Host and S3908 Touch Node

```dts
&i2c0 {
    status = "okay";
    clock-frequency = <400000>;
    synaptics20171@4B {
        status = "okay";
        compatible = "synaptics-s3908";
        reg = <0x4B>;
        chip-name = "S3908";

        /* Interrupt && Irq-gpio */
        interrupt-parent = <&pio>;
        interrupts = <8 0x2008>;

        /* Power Config */
        vdd_2v8-supply  = <&mt6373_vtp>;
        vdd_2v8_volt = <3000000>;
        vcc_1v8-supply  = <&mt6373_vmc>;
        vcc_1v8_volt = <1800000>;

        /* Other HW Resource */
        irq-gpio = <&pio 8 0x2008>;
        reset-gpio = <&pio 3 0x1>;
        pinctrl-names = "default";
        pinctrl-0 = <&ts_int_active &ts_reset_active>;

        touchpanel,curved-size = <45>;
        touchpanel,max-num-support = <10>;
        touchpanel,tx-rx-num = <17 38>;
        touchpanel,panel-coords = <5760 12864>;
        touchpanel,display-coords = <1440 3216>;
        touchpanel,int-mode = <1>;

        S3908 {
            report_rate_default = <60>;
            report_rate_game_value = <2>;
            default_gesture_mask = <8191>;
        };
    };
};
```

### 2.2 Touch GPIO Map (from `&pio` pinctrl, `ts_*_active` nodes)

| Signal | GPIO | Pinctrl node | Config |
| --- | --- | --- | --- |
| IRQ (`irq-gpio` / `interrupts`) | 8 | `ts_int_active` | `PINMUX_GPIO8__FUNC_GPIO8`, bias-pull-up |
| Reset (`reset-gpio`) | 3 | `ts_reset_active` | `PINMUX_GPIO3__FUNC_GPIO3`, output-high |

### 2.3 Touch Power Rails

| Property | Supply | Configured voltage |
| --- | --- | --- |
| `vdd_2v8-supply` | `mt6373_vtp` | 3,000,000 µV (3.0 V) |
| `vcc_1v8-supply` | `mt6373_vmc` | 1,800,000 µV (1.8 V) |

### 2.4 Scan Geometry and Reporting

| Property | Value | Source |
| --- | --- | --- |
| TX/RX channels | 17 / 38 | `touchpanel,tx-rx-num = <17 38>` |
| Max concurrent points | 10 | `touchpanel,max-num-support = <10>` |
| Display coords | 1440 x 3216 | `touchpanel,display-coords` |
| Panel coords | 5760 x 12864 | `touchpanel,panel-coords` |
| Default report rate | 60 Hz | `S3908 { report_rate_default = <60>; }` |

### 2.5 Touch Driver Module (verification status)

The Round 6 queue listed `touch_synaptics` and `goodix_core` as required
modules, flagged as guesses. Neither name appears anywhere in the on-disk
Nord 3 sources (`sources/snapshots/kernel-mt6983` and the vendor `.config`
artifacts), and the vendor touch driver tree is not present locally. Per the
review-blessed D17 approach, **the gate does not assert unverified module
names**. Binding evidence comes from:

1. the I2C client driver link (`/sys/bus/i2c/devices/0-004b/driver`), and
2. the input class device (`/sys/class/input/event*` name match for
   `S3908` / `synaptics`).

---

## 3. Tool Usage

```sh
# Offline fixture validation (hermetic, no network)
python3 lynx/tools/touch/lynx_touch_preflight.py \
  lynx/tools/touch/fixtures/touch-preflight-bound.json

# Double-gated read-only live inspection (requires BOTH flags)
python3 lynx/tools/touch/lynx_touch_preflight.py --live --allow-live
```

### Exit Codes

| Code | Meaning |
| --- | --- |
| 0 | Valid spec; status `BOUND_READY` or `UNBOUND_QUIESCENT` |
| 1 | `MALFORMED_SPEC` (spec audit failed) or live query error |
| 2 | Live gate: `--live` without `--allow-live` |

### Verdict Statuses

| Status | Condition |
| --- | --- |
| `BOUND_READY` | Spec valid + I2C client driver bound + input device present |
| `UNBOUND_QUIESCENT` | Spec valid, controller enumerated but not bound |
| `PARTIAL_ENUMERATED` | Spec valid, driver bound but no input device (or vice versa) |
| `MALFORMED_SPEC` | Any board-spec violation in the audited document |

### Spec Audit Coverage

- Touch node present in the device tree; I2C bus 0, address `0x4B`
- `compatible = "synaptics-s3908"`, `chip-name = "S3908"`
- GPIO map: IRQ 8, reset 3
- Rails: `mt6373_vtp` @ 3,000,000 µV, `mt6373_vmc` @ 1,800,000 µV
- Geometry: TX 17, RX 38, max points 10, display 1440 x 3216
- Reporting: default rate 60 Hz

### Live Collector (read-only)

Collects over the pinned key-only SSH link (8 s cap): boot_id, devicetree
`*synaptics*` nodes and their `compatible`/`chip-name`, I2C-0 client
`0-004b` and its driver symlink, input class device names, and loaded modules.
Uses only `cat`/`ls`/`find`/`readlink`/`tr`/`echo`; no writes, no module
loads, no touch sampling.

---

## 4. Test Evidence

```
$ cd lynx/tools/touch && python3 -m unittest test_lynx_touch_preflight -v
Ran 29 tests ... OK
```

- 6 constant tests (chip, I2C placement, GPIOs, rails, geometry, report rate)
- 8 spec-validation tests (valid + 7 corruption/negative cases)
- 6 evaluator tests (BOUND_READY / UNBOUND_QUIESCENT / PARTIAL_ENUMERATED / MALFORMED_SPEC / missing runtime / to_dict)
- 5 CLI tests (bound exit 0, unbound exit 0, missing-dt exit 1, `--live` gate exit 2, no-args help)
- 4 safety tests (read-only script tokens, command whitelist, harmless imports, no unapproved local_calls additions — the pre-existing approved `lynx_touch_status` pair from commit `88a913f` remains untouched)

---

## 5. Known Limitations

- Module names are intentionally not asserted; verify the real vendor touch
  driver name from the on-phone `lsmod` output (via the gated live collector)
  before any bring-up work that depends on it.
- The live collector matches input devices by name substring (`s3908` /
  `synaptics`); a renamed input device would read as absent.
- `report_rate_game_value`, `default_gesture_mask`, and smooth/sensitivity
  tables are present in the DTS but not part of the gate's audited spec; they
  are behavioral tuning, not bring-up preconditions.
