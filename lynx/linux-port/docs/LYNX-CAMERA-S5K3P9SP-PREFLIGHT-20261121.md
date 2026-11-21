# Lynx Camera S5K3P9SP Front Sensor Bring-Up Preflight

## 1. Platform Identity and Sensor Overview

- **Platform**: OnePlus Nord 3 5G (CPH2493)
- **SoC**: MediaTek Dimensity 9000 (MT6983), Project `22823` ("Vitamin")
- **Sensor Model**: Samsung S5K3P9SP (16 Megapixel Four-cell / Tetracell CMOS Image Sensor)
- **Primary Driver Source**: `drivers/misc/mediatek/imgsensor/src-v4l2/common/s5k3p9sp_mipi_raw_22823/s5k3p9spmipiraw_Sensor_22823.c`
- **Device Tree Source**: `arch/arm64/boot/dts/mediatek/cust_mt6983_vitamin_camera_v4l2.dtsi:490-531`
- **Safety Boundary**: Strictly offline analysis and read-only preflight. No kernel module is loaded into the phone kernel, no camera streaming is initiated, and no phone rootfs modifications are made. Streaming and capture remain `HARD_REFUSE` under [`lynx_camera_gate.py`](file:///noobia/lynx/tools/lynx_camera_gate.py).

---

## 2. Hardware Mapping from Nord 3 Source Tree

### 2.1 Device Tree Node and I2C Addressing
The S5K3P9SP front sensor is attached to the SoC I2C-9 bus (`clock-frequency = 1000000` / 1 MHz):
```dts
&i2c9 {
    clock-frequency = <1000000>;

    /* Front Camera EEPROM OTP Calibration */
    mtk_camera_eeprom1: camera_eeprom1@54 {
        compatible = "mediatek,camera_eeprom";
        reg = <0x54>;
        status = "okay";
    };

    /* Front Camera Sensor */
    sensor1: sensor1@10 {
        compatible = "mediatek,imgsensor";
        sensor-names = "s5k3p9sp_mipi_raw_22823";
        reg = <0x10>;
        ...
    };
};
```
- **I2C Client Address**: `0x10` (7-bit address), 8-bit read/write address `0x20` / `0x21`.
- **EEPROM Address**: `0x54` (`camera_eeprom1`).
- **Sysfs Physical Path**: `/sys/bus/i2c/devices/9-0010` (live verified).
- **VCM Actuator**: None. Front camera uses a fixed-focus lens assembly.

### 2.2 CSI Port and MIPI D-PHY Configuration
- **SENINF CSI Port**: `seninf_csi_port_0` (port index 0):
  ```dts
  port {
      sensor1_out: endpoint {
          remote-endpoint = <&seninf_csi_port_0_in>;
      };
  };
  ```
- **Physical Layer Bus**: MIPI D-PHY:
  - `.mipi_sensor_type = MIPI_OPHY_NCSI2` (NCSI-2 D-PHY protocol)
  - `.mipi_lane_num = SENSOR_MIPI_4_LANE` (4 data lanes + 1 clock lane)
- **Master Clock (MCLK)**:
  - Source clock: `<&topckgen_clk CLK_TOPCKGEN_CAMTG_SEL>`
  - Clock frequency: 24 MHz (`.mclk = 24`)
  - Pin routing: `PINMUX_GPIO196__FUNC_CMMCLK0`
  - Drive strengths: 2mA (`<0>`), 4mA (`<1>`), 6mA (`<2>`), 8mA (`<3>`). Driver configures 6mA.

### 2.3 GPIO Pin Controls
From `cust_mt6983_vitamin_camera_v4l2.dtsi:151-196`:
1. **MCLK**: `GPIO196` (`camera_pins_cam1_mclk_off` / `camera_pins_cam1_mclk_6ma`)
2. **Reset (RST)**: `GPIO199`
   - Active low reset: `camera_pins_cam1_rst_0` (`pinmux = <PINMUX_GPIO199__FUNC_GPIO199>; output-low;`)
   - Normal operation: `camera_pins_cam1_rst_1` (`pinmux = <PINMUX_GPIO199__FUNC_GPIO199>; drive-strength = <3>; output-high;`)

---

## 3. Power Rails and Bring-Up Power Sequence

From `s5k3p9spmipiraw_Sensor_22823.c:2170-2178` and `multi-regulator_vitamin.dtsi`:
The sub-PMIC supplies and reset lines execute a 7-step power sequence:

| Step | Hardware Component | Action / Value | Delay | Details |
|---|---|---|---|---|
| 1 | `HW_ID_MCLK` | 24 MHz | 0 ms | Enable MCLK oscillator from CAMTG0 |
| 2 | `HW_ID_RST` | 0 (Low) | 1 ms | Assert sensor hardware reset (GPIO199 low) |
| 3 | `HW_ID_DVDD` | 1.104 V | 1 ms | Enable Digital Core VDD via `multi_reg_ldo1` |
| 4 | `HW_ID_AVDD` | 2.804 V | 1 ms | Enable Analog VDD via `multi_reg_ldo4` |
| 5 | `HW_ID_DOVDD` | 1.804 V | 3 ms | Enable Digital I/O VDD via `multi_reg_ldo7` |
| 6 | `HW_ID_MCLK_DRIVING_CURRENT` | 6 mA | 0 ms | Set MCLK drive strength to 6mA (`drive-strength = <2>`) |
| 7 | `HW_ID_RST` | 1 (High) | 2 ms | Deassert sensor reset (GPIO199 high) |

**Total Sequence Duration**: 8 ms.

### 3.1 Power-Down Sequence
During shutdown (`adaptor_hw_power_off`), the driver traverses `pw_seq` in reverse:
1. Deassert RST (low)
2. Reset MCLK driving current
3. Disable DOVDD (1.8V)
4. Disable AVDD (2.8V)
5. Disable DVDD (1.1V)
6. Disable MCLK

---

## 4. Required Kernel Modules in Dependency Order

To bind and operate the S5K3P9SP front sensor, the kernel requires six modules in strict dependency order:
1. `mtk_cam_plat_util`: Base platform helpers and DMA memory primitives.
2. `mtk_cam_plat_mt6983`: MT6983 platform clock, power domain, and register abstractions.
3. `camera_eeprom`: I2C EEPROM calibration driver for `camera_eeprom1@54`.
4. `imgsensor`: MediaTek camera sensor core framework providing `/dev/v4l-subdev*`.
5. `mtk_cam_isp`: MediaTek ISP 7.1 driver (or volatile RAM-patched build for CAMSV routing).
6. `oplus_cam_event_report`: Vendor diagnostic and OLC exception notification layer.

---

## 5. Preflight Evaluation Tooling and Live State

The inspection tool [`lynx/tools/camera_deps/lynx_s5k3p9sp_preflight.py`](file:///noobia/lynx/tools/camera_deps/lynx_s5k3p9sp_preflight.py) provides:
- **Offline Evaluation**: Audits DT node mappings, 4-lane D-PHY, MCLK, fixed-focus status (no VCM), and 7-step power sequence against reference fixtures.
- **Read-Only Live Collector**: Gated behind `--live --allow-live`. Performs non-actuating read-only queries over SSH to audit `/sys/firmware/devicetree/base`, `/sys/bus/i2c/devices/9-*`, and `/proc/modules`.

### 5.1 Current Live State on Lynx (Boot `0fe847d2`)
Live inspection confirms:
- Node `/sys/firmware/devicetree/base/i2c@11d06000/sensor1@10` is present in device tree.
- Sysfs client `/sys/bus/i2c/devices/9-0010` exists (`name = imgsensor`).
- EEPROM client `/sys/bus/i2c/devices/9-0054` exists (`name = camera_eeprom`).
- Driver binding: **UNBOUND** (quiescent).
- Kernel modules: **None loaded** (`imgsensor` absent from `/proc/modules`).
- Preflight Status: **`UNBOUND_QUIESCENT`** (Safe baseline).
