# OnePlus Alert Slider (Tri-State Key) Hardware Mapping & Preflight Gate

**Subsystem:** Tri-State Key / Alert Slider (OnePlus Nord 3 / `oplus6983_22823`)
**Author:** Banshee (Spirit of Initiative 💙)
**Date:** 2026-11-21
**Directory:** `lynx/tools/tri_state_key/`

---

## 1. Hardware Architecture & Device Tree Mapping

The OnePlus Nord 3 features the signature physical 3-position Alert Slider on its chassis. Rather than using mechanical micro-switches prone to wear, OnePlus implements a contact-less magnetic positioning system using two high-sensitivity digital Hall effect ICs positioned along the slider travel path.

### 1.1 Bus & Sensor Nodes

From the unified device tree (`stock-merged.dtb` / `oplus6983_22823.dts`):
- **I2C Host Controller:** `i2c0` at MMIO `0x11e00000` (`compatible = "mediatek,mt6983-i2c"`)
- **Primary Source Dual-Hall ICs:** MagnaChip MXM1120
  - **Down-Hall Sensor (`magnachip@0C`):**
    - Address: `0x0C` (7-bit I2C)
    - Compatible: `oplus,hall-mxm1120,down`
    - Hall ID: `2` (`dhall,id = <2>`)
    - IRQ GPIO: GPIO 5 (`dhall,irq-gpio = <&pio 5 0x2008>`)
    - Pinctrl State: `downhall_tri_state_key_active`
  - **Up-Hall Sensor (`magnachip@0D`):**
    - Address: `0x0D` (7-bit I2C)
    - Compatible: `oplus,hall-mxm1120,up`
    - Hall ID: `1` (`dhall,id = <1>`)
    - IRQ GPIO: GPIO 4 (`dhall,irq-gpio = <&pio 4 0x2008>`)
    - Pinctrl State: `uphall_tri_state_key_active`

- **Second Source Dual-Hall ICs:** Isentek IST8801
  - **Down-Hall Sensor (`ist8801@18`):**
    - Address: `0x18` (7-bit I2C)
    - Compatible: `oplus,hall-ist8801,down`
    - Hall ID: `2`
    - IRQ GPIO: GPIO 5
  - **Up-Hall Sensor (`ist8801@19`):**
    - Address: `0x19` (7-bit I2C)
    - Compatible: `oplus,hall-ist8801,up`
    - Hall ID: `1`
    - IRQ GPIO: GPIO 4

### 1.2 Power Supplies

- `vio-supply`: `//spmi@1c015000/pmic@4/regulators/VIO18` (1.8V digital I/O rail from MT6363 PMIC)
- `vdd-supply`: `//spmi@1c015000/second_pmic@5/regulators/VIO28` (2.8V analog VDD rail from MT6373/MT6375 sub-PMIC)

### 1.3 Physical State Machine & Magnetic Positioning

| Position | Physical Location | Up-Hall State (GPIO 4 / 0x0D) | Down-Hall State (GPIO 5 / 0x0C) | Android / Linux Audio Profile |
|---|---|---|---|---|
| **State 1** | Top | **TRIGGERED (Near Magnet)** | IDLE (Far from Magnet) | **SILENT** |
| **State 2** | Middle | IDLE (Far from Magnet) | IDLE (Far from Magnet) | **VIBRATE** |
| **State 3** | Bottom | IDLE (Far from Magnet) | **TRIGGERED (Near Magnet)** | **RING** |

---

## 2. Preflight Gate Implementation

The preflight tool `lynx_tri_state_key_preflight.py`:
1. Validates device tree hardware topology against the hardware facts above.
2. Validates Hall sensor I2C bus registration and IRQ pin assignments.
3. Decodes slider position and flags ambiguous magnetic states.
4. Provides double-gated read-only live interrogation (`--live --allow-live`) strictly reading sysfs and input event metadata.
5. Complies with all safety boundaries: zero I2C register writes, zero sysfs writes, zero module modifications.
