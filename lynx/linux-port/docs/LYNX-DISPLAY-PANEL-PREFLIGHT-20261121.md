# Lynx AMOLED Display & Panel Bring-Up Preflight (Round 6, Item D17)

## 1. Platform Identity and Display Overview

- **Platform**: OnePlus Nord 3 5G (CPH2493)
- **SoC**: MediaTek Dimensity 9000 (MT6983), Project `22823` ("Vitamin")
- **Display**: Curved AMOLED, 1440 x 3216 (device tree `touchpanel,display-coords = <1440 3216>`), 120 Hz per Round 6 queue / device datasheet
- **Active Panel**: Tianma NT37705 AMOLED (FHD, MIPI DSI command mode), `panel5@0`, `reg = <0>`
- **Second-Source Panel**: BOE NT37701A AMOLED (FHD, MIPI DSI command mode), `panel2@0`, `reg = <1>`
- **Backlight**: `mediatek,disp-leds` PWM controller, label `lcd-backlight`, 13-bit, max brightness `10239`
- **Safety Boundary**: Strictly offline by default. Live inspection is read-only
  (`cat`/`ls`/`find`/`readlink`/`tr`/`echo` only), double-gated behind
  `--live --allow-live`, bounded to 8 s, zero writes to the phone rootfs,
  zero module loads, zero screen-state changes.

---

## 2. Hardware Mapping from the Nord 3 Source Tree

All facts verified against:

- Board DTS: `sources/snapshots/kernel-mt6983/arch/arm64/boot/dts/mediatek/oplus6983_22823.dts`
- Vendor kernel build config: `sources/artifacts/*/basis/.config` (panel panelizer symbols)

### 2.1 DSI-0 Host and Panel Nodes

```dts
&dsi0 {
    status = "okay";
    #address-cells = <1>;
    #size-cells = <0>;

    panel2@0 {                                   /* second-source panel, reg <1> */
        compatible = "oplus22021_boe_nt37701a_fhd_dsi_cmd";
        reg = <1>;
        vddr1p5-enable-gpios = <&pio 148 0>;
        reset-gpios = <&pio 86 0>;
        te_out-gpios = <&pio 36 0>;
        aod_en-gpios = <&mt6373_pio 3 0>;
        1p8-supply = <&mt6363_vufs18>;
        3p0-supply = <&mt6373_vmch>;
    };

    panel5@0 {                                   /* active 22823 panel, reg <0> */
        compatible = "oplus22823,tm,nt37705,cmd";
        reg = <0>;
        io-channels = <&mt6373_adc (ADC_PURES_100K_MASK | AUXADC_VIN1)>;
        io-channel-names = "panel-channel";
        vddr-enable-gpios = <&pio 148 0>;
        reset-gpios = <&pio 86 0>;
        oplus-adfr-config = <33>;
        te_switch-gpios = <&pio 36 0>;
        te_out-gpios = <&pio 24 0>;
        vddr-aod-en-gpios = <&mt6373_pio 3 0>;
        1p8-supply = <&mt6373_vrf18_aif>;
        3p0-supply = <&mt6373_vmc>;
    };
};
```

- **DSI host**: `&dsi0`, `status = "okay"`, two child panel nodes. The active
  panel is `panel5@0` (`reg = <0>`); the BOE second-source panel is `panel2@0`
  (`reg = <1>`).
- **Panel interconnect**: `panel5_in5` / `panel_in2` endpoints both reference
  the shared `dsi_out` endpoint on the DSI host port.

### 2.2 Panel GPIO Map (active panel `panel5@0`)

| Function | GPIO / Controller | DTS property |
|---|---|---|
| Panel reset | GPIO 86 | `reset-gpios = <&pio 86 0>` |
| VDDR enable | GPIO 148 | `vddr-enable-gpios = <&pio 148 0>` |
| TE switch | GPIO 36 | `te_switch-gpios = <&pio 36 0>` |
| TE out | GPIO 24 | `te_out-gpios = <&pio 24 0>` |
| AOD (always-on) enable | `mt6373_pio3` | `vddr-aod-en-gpios = <&mt6373_pio 3 0>` |

Pinctrl (board DTS, `mtkfb` pin groups): `lcm_rst_out0/1` on GPIO 86,
`DSI_TE` on GPIO 85 (`PINMUX_GPIO85__FUNC_DSI_TE`), LCD bias enable
ENP/ENN on GPIO 84.

### 2.3 Panel Power Rails (active panel)

| Rail | Regulator | DTS property |
|---|---|---|
| 1.8 V core | `mt6373_vrf18_aif` | `1p8-supply` |
| 3.0 V | `mt6373_vmc` | `3p0-supply` |
| Panel channel sensing | `mt6373_adc` AUXADC `VIN1`, 100 K pure mode | `io-channels` / `io-channel-names = "panel-channel"` |

The board also declares the ADC channel explicitly:

```dts
&mt6373_adc {
    vin1_100k {
        channel = <AUXADC_VIN1>;
        pures = <ADC_PURES_100K>;
    };
};
```

### 2.4 Backlight (PWM)

```dts
&mtk_leds {
    compatible = "mediatek,disp-leds";
    backlight {
        label = "lcd-backlight";
        led_mode = <4>;
        max-brightness = <10239>;
        max-hw-brightness = <10239>;
        led-bits = <13>;
    };
};

/* &odm child */
led6:led@6 {
    compatible = "mediatek,lcd-backlight";
    led_mode = <4>;
    pwm_config = <0 1 0 0 0>;   /* PWM channel 1 */
};
```

- **Backlight label**: `lcd-backlight` (sysfs `/sys/class/backlight/lcd-backlight`)
- **Bit depth**: 13 (`led-bits`), max brightness `10239` (`max-brightness` / `max-hw-brightness`)
- **PWM channel**: 1 (`pwm_config`), `led_mode = 4` (dual-PWM / boost mode)

### 2.5 Required Panel Driver Modules

Verified as loadable modules (`=m`) in the vendor kernel build configuration:

| CONFIG symbol | Module |
|---|---|
| `CONFIG_DRM_PANEL_OPLUS22823_TM_NT37705_FHD_DSI_CMD=m` | `oplus22823_tm_nt37705_fhd_dsi_cmd` (active panel) |
| `CONFIG_DRM_PANEL_OPLUS22021_BOE_NT37701A_FHD_DSI_CMD=m` | `oplus22021_boe_nt37701a_fhd_dsi_cmd` (second-source) |

> **Note on spec guesses**: the Round 6 queue named `mtk_disp_drv`,
> `oplus_display_panel`, and `disp_pwm` as "required modules" (flagged as
> guesses). These names do not appear in the on-disk vendor sources or
> build config. The verified module names above (derived from the
> `CONFIG_DRM_PANEL_*` symbols) are used by the preflight gate instead. The
> MTK dispsys/DSI core stack and the `mediatek,disp-leds` backlight driver
> are assumed present at runtime; the live collector reports the actually
> bound DRM driver and loaded modules as evidence without asserting
> unverified names.

---

## 3. Tool Usage

```sh
cd /noobia/lynx/tools/display

# Offline fixture validation (hermetic, no network)
python3 lynx_display_preflight.py fixtures/display-preflight-bound.json
python3 lynx_display_preflight.py fixtures/display-preflight-unbound.json
python3 lynx_display_preflight.py fixtures/display-preflight-missing-dt.json

# Double-gated read-only live inspection (requires BOTH flags)
python3 lynx_display_preflight.py --live --allow-live --host 192.168.100.107 --port 2222
```

### Exit Codes

| Code | Meaning |
|---|---|
| `0` | Valid preflight: `BOUND_READY` or `UNBOUND_QUIESCENT` |
| `1` | Invalid: `MALFORMED_SPEC` (spec audit violation) or live collection error |
| `2` | Live gate refused (`--live` without `--allow-live`) |

### Verdict Statuses

| Status | Meaning |
|---|---|
| `BOUND_READY` | Spec audit clean; active panel module loaded and DRM driver bound |
| `UNBOUND_QUIESCENT` | Spec audit clean; panel driver safely unbound |
| `PARTIAL_ENUMERATED` | Spec audit clean; exactly one of {module loaded, driver bound} |
| `MALFORMED_SPEC` | One or more board-spec violations (any DTS/config mismatch) |

### Spec Audit Coverage

- DSI-0 host node present in device tree
- Active panel compatible `oplus22823,tm,nt37705,cmd` present
- Second-source panel compatible `oplus22021_boe_nt37701a_fhd_dsi_cmd` present
- Backlight label `lcd-backlight`, max brightness `10239`, 13-bit, PWM channel 1
- Power rails `mt6373_vrf18_aif` (1.8 V), `mt6373_vmc` (3.0 V), AOD `mt6373_pio3`,
  panel-channel ADC `mt6373_adc AUXADC_VIN1 100K`
- GPIO map reset 86 / VDDR 148 / TE-switch 36 / TE-out 24
- Expected panel module list matches the two verified `CONFIG_DRM_PANEL_*` modules

### Live Collector (read-only)

Reads over the pinned Alpine SSH link (key-only, 8 s cap):

- `/proc/sys/kernel/random/boot_id`
- `/sys/firmware/devicetree/base/**/panel*` nodes and their `compatible` property
- `/sys/firmware/devicetree/base/**/dsi*` host nodes
- `/sys/firmware/devicetree/base/**/backlight` labels
- `/sys/class/drm/` devices and `card*/device/driver` bindings (`readlink -f`)
- `/sys/class/backlight/` entries and `lcd-backlight/max_brightness`
- `/sys/class/graphics/` framebuffers
- `/proc/modules` loaded module list

No writes, no module loads, no screen-state changes, no camera or RF actuation.

---

## 4. Test Evidence

```sh
cd /noobia/lynx/tools/display
python3 -m unittest test_lynx_display_preflight -v
# Ran 29 tests ... OK
```

- 6 fixture/evaluator tests (bound, unbound, missing-DT, partial, missing-runtime, to_dict)
- 8 spec-validation tests (valid, corrupted GPIO/rail/backlight/DSI/compatible/module)
- 6 expected-constant tests (compatibles, GPIO map, rails, backlight, module derivation)
- 5 CLI tests (fixture exit codes 0/0/1, live gate exit 2, help)
- 4 safety tests (readonly script scan, command whitelist, harmless imports,
  no unapproved `local_calls` wiring)

---

## 5. Known Limitations

- The MTK dispsys core, DSI controller, and PWM backlight driver module names
  are not asserted by the gate (unverifiable from on-disk sources); the live
  collector reports actual runtime evidence instead.
- Lane count (4 data + 1 clock) is stated in the queue spec but is not
  directly verifiable from the on-disk DTS snapshot; the gate does not assert it.
- `oplus-adfr-config = <33>` (ADFR mux switch) is recorded for completeness;
  not asserted by the gate.
