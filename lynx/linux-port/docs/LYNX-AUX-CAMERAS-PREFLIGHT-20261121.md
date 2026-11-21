# Lynx Auxiliary Cameras Bring-Up Preflight (Round 6, Item D19)

## 1. Platform Identity and Aux Camera Overview

- **Platform**: OnePlus Nord 3 5G (CPH2493)
- **SoC**: MediaTek Dimensity 9000 (MT6983), Project `22823` ("Vitamin")
- **WIDE (ultrawide)**: Sony IMX355, DT node `sensor2@1a` on `&i2c2` @ `0x1a`, 400 kHz, `seninf-2`
- **MACRO**: GalaxyCore GC02M1, DT node `sensor4@3d` on `&i2c9` @ `0x3d`, 1 MHz, `seninf-1`
- **Prior functional evidence** (camera_deps README): IMX355 wide proved
  `3264x2448` Bayer frame completion in RAM (`7,990,296` bytes); GC02M1 macro
  proved recognized optical frames under request-scoped `mtk_hdr_ae` controls
- **Safety Boundary**: Strictly offline by default. Live inspection is
  read-only (`cat`/`ls`/`find`/`readlink`/`tr`/`echo` only), double-gated
  behind `--live --allow-live`, bounded to 8 s, zero writes to the phone
  rootfs, zero module loads, zero streaming or capture.

> **Queue note:** the Round 6 queue named the pair "IMX355 ultrawide &
> GC02M1 macro" (correct) with sensors "sensor2 + sensor3". Verified in
> `cust_mt6983_vitamin_camera_v4l2.dtsi`: the IMX355 is indeed `sensor2@1a`,
> but the GC02M1 is **`sensor4@3d`** — the board DTS has **no `sensor3`
> node**. The gate asserts the verified node names and documents the
> discrepancy (see §2.1).

---

## 2. Hardware Mapping from the Nord 3 Source Tree

All facts verified against:

- Camera DTSI: `sources/snapshots/kernel-mt6983/arch/arm64/boot/dts/mediatek/cust_mt6983_vitamin_camera_v4l2.dtsi`

### 2.1 Sensor Node Placement (queue-guess correction)

| Camera | Queue guess | Verified DT node | I2C bus @ addr | Bus clock |
| --- | --- | --- | --- | --- |
| IMX355 ultrawide | `sensor2` | `sensor2@1a` | `&i2c2` @ `0x1a` | 400 kHz |
| GC02M1 macro | `sensor3` | **`sensor4@3d`** | `&i2c9` @ `0x3d` | 1 MHz |

Full camera inventory on the board (same DTSI): `sensor0@36` on `&i2c8`
(main: `ov64b_mipi_raw_22823` / `imx890_mipi_raw_21871`), `sensor1@10` on
`&i2c9` (front: `s5k3p9sp_mipi_raw_22823`), `sensor2@1a` (wide), `sensor4@3d`
(macro). No `sensor3` exists.

```dts
&i2c2 {
    clock-frequency = <400000>;
    /* WIDE */
    mtk_camera_eeprom2:camera_eeprom2@51 { compatible = "mediatek,camera_eeprom"; reg = <0x51>; };
    sensor2: sensor2@1a {
        compatible = "mediatek,imgsensor";
        sensor-names = "imx355_mipi_raw_22823";
        reg = <0x1a>;
        //GPIO198  pinctrl-0..4 = camera_pins_cam2_mclk_{off,2ma,4ma,6ma,8ma}
        //GPIO201  pinctrl-5..6 = camera_pins_cam2_rst_{0,1}
        avdd-supply  = <&multi_reg_ldo4>;
        dvdd-supply  = <&multi_reg_ldo2>;
        dovdd-supply = <&multi_reg_ldo7>;
        status = "okay";
        port { sensor2_out: endpoint { remote-endpoint = <&seninf_csi_port_2_in>; }; };
    };
};

&i2c9 {
    clock-frequency = <1000000>;
    mtk_camera_eeprom4:camera_eeprom4@52 { compatible = "mediatek,camera_eeprom"; reg = <0x52>; };
    sensor4: sensor4@3d {
        compatible = "mediatek,imgsensor";
        sensor-names = "gc02m1_mipi_raw_22823";
        reg = <0x3d>;
        //GPIO197  pinctrl cam4 mclk (CMMCLK1)
        //GPIO200  pinctrl cam4 rst (output-low / output-high)
        avdd-supply  = <&multi_reg_ldo4>;
        dovdd-supply = <&multi_reg_ldo7>;   /* no dvdd-supply for GC02M1 */
        status = "okay";
        port { sensor4_out: endpoint { remote-endpoint = <&seninf_csi_port_1_in>; }; };
    };
};
```

### 2.2 MCLK / RESET GPIO Map (from DTSI pinctrl nodes)

| Camera | MCLK GPIO | MCLK function | RESET GPIO |
| --- | --- | --- | --- |
| IMX355 (`cam2`) | 198 | `PINMUX_GPIO198__FUNC_CMMCLK2` (off/2/4/6/8 mA drive levels) | 201 |
| GC02M1 (`cam4`) | 197 | `PINMUX_GPIO197__FUNC_CMMCLK1` (off/2/4/6/8 mA drive levels) | 200 |

### 2.3 Power Rails (external multi-PMIC, per DTS comment `wl2868c/wl28681/fan53870`)

| Camera | AVDD | DVDD | DOVDD |
| --- | --- | --- | --- |
| IMX355 | `multi_reg_ldo4` | `multi_reg_ldo2` | `multi_reg_ldo7` |
| GC02M1 | `multi_reg_ldo4` | *(absent in DTS)* | `multi_reg_ldo7` |

The `multi_reg` regulator is an external PMIC; its LDO voltages are not
defined in the on-disk tree, so the gate asserts the supply names (verified
references) and deliberately does not assert voltages.

### 2.4 EEPROM and CSI Routing

| Camera | EEPROM | CSI endpoint |
| --- | --- | --- |
| IMX355 | `camera_eeprom2@51` (`&i2c2`) | `seninf_csi_port_2_in` |
| GC02M1 | `camera_eeprom4@52` (`&i2c9`) | `seninf_csi_port_1_in` |

### 2.5 Sensor Driver Modules (verification status)

The generic `mediatek,imgsensor` driver is the DT binding; per-sensor driver
modules (e.g. `imx355_mipi_raw_22823`, `gc02m1_mipi_raw_22823`) are named by
`sensor-names` in the DTSI (verified strings) but their `.ko` files are not
present in the on-disk sources (vendor camera driver tree absent locally;
the only IMX355 reference on disk is the Alpine `libcamera` patch, unrelated
to the phone kernel). Per the review-blessed D17/D18 approach, **the gate
does not assert unverified module names**. Binding evidence comes from the
I2C client driver links (`/sys/bus/i2c/devices/2-001a/driver`,
`/sys/bus/i2c/devices/9-003d/driver`) and the video4linux entity list.

---

## 3. Tool Usage

```sh
# Offline fixture validation (hermetic, no network)
python3 lynx/tools/camera_deps/lynx_aux_camera_preflight.py \
  lynx/tools/camera_deps/fixtures/aux-cameras-preflight-bound.json

# Double-gated read-only live inspection (requires BOTH flags)
python3 lynx/tools/camera_deps/lynx_aux_camera_preflight.py --live --allow-live
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
| `BOUND_READY` | Both specs valid + IMX355 and GC02M1 both bound |
| `UNBOUND_QUIESCENT` | Both specs valid, neither driver bound |
| `PARTIAL_ENUMERATED` | Spec valid, exactly one sensor bound |
| `MALFORMED_SPEC` | Any board-spec violation in either audited sensor |

### Spec Audit Coverage (per sensor)

- DT node name + presence, I2C bus/address/clock, `compatible`, `sensor-names`
- MCLK and reset GPIO map
- AVDD/DVDD/DOVDD supply references (DVDD `null` for GC02M1 — asserting one
  is a spec violation)
- EEPROM address and `seninf` CSI port

### Live Collector (read-only)

Collects over the pinned key-only SSH link (8 s cap): boot_id, devicetree
`sensor2*`/`sensor4*` nodes and their `sensor-names`, I2C clients `2-001a`
and `9-003d` with driver symlinks, video4linux node names, and loaded
modules. Uses only `cat`/`ls`/`find`/`readlink`/`tr`/`echo`; no writes, no
module loads, no streaming or capture.

---

## 4. Test Evidence

```
$ cd lynx/tools/camera_deps && python3 -m unittest test_lynx_aux_camera_preflight
Ran 30 tests ... OK
```

- 7 constant tests (wide node/I2C/identity/GPIO+rail map, macro
  sensor4-not-sensor3 assertion, macro I2C, macro identity, macro GPIO+rail map)
- 8 spec-validation tests (valid + 7 corruption/negative cases, incl.
  "asserting a DVDD for GC02M1" negative)
- 6 evaluator tests (BOUND_READY / UNBOUND_QUIESCENT / PARTIAL_ENUMERATED /
  MALFORMED_SPEC / missing runtime / to_dict)
- 5 CLI tests (bound exit 0, unbound exit 0, missing-dt exit 1, `--live`
  gate exit 2, no-args help)
- 4 safety tests (read-only script tokens, command whitelist, harmless
  imports, no unapproved local_calls additions — the pre-existing approved
  `lynx_camera` pair remains untouched)

---

## 5. Known Limitations

- Sensor driver `.ko` names are not asserted (vendor camera tree absent on
  disk); verify on-phone via the gated live collector's module list.
- External multi-PMIC LDO voltages are not asserted (not defined in the
  on-disk tree).
- The live collector reports binding per I2C client; a sensor whose driver
  binds under a different alias would still appear unbound — cross-check
  against `/sys/class/video4linux` names in the same collection.
- Functional frame capture is out of scope and remains hard-refused; this
  gate is bring-up preflight only.
