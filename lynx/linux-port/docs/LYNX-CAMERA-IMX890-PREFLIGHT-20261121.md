# Lynx Camera IMX890 Main Sensor Bring-Up Preflight

## 1. Platform Identity and Sensor Overview

- **Platform**: OnePlus Nord 3 5G (CPH2493)
- **SoC**: MediaTek Dimensity 9000 (MT6983), Project `22823` ("Vitamin")
- **Sensor Model**: Sony IMX890 (50 Megapixel Four-cell / Quad Bayer CMOS Image Sensor)
- **Primary Driver Source**: `drivers/misc/mediatek/imgsensor/src-v4l2/common/imx890_mipi_raw_21871/imx890mipiraw_Sensor_21871.c`
- **Device Tree Source**: `arch/arm64/boot/dts/mediatek/cust_mt6983_vitamin_camera_v4l2.dtsi:428-480`
- **Safety Boundary**: Strictly offline analysis and read-only preflight. No kernel module is loaded into the phone kernel, no camera streaming is initiated, and no phone rootfs modifications are made. Streaming and capture remain `HARD_REFUSE` under [`lynx_camera_gate.py`](file:///noobia/lynx/tools/lynx_camera_gate.py).

---

## 2. Hardware Mapping from Nord 3 Source Tree

### 2.1 Device Tree Node and I2C Addressing
The IMX890 main sensor is attached to the SoC I2C-8 bus (`clock-frequency = 1000000` / 1 MHz):
```dts
&i2c8 {
    clock-frequency = <1000000>;

    /* Voice Coil Motor Actuators */
    camera_af_main@0a  { compatible = "mediatek,ak7375c_22823"; reg = <0x0a>; ... };
    camera_af_main1@0b { compatible = "mediatek,ak7377_21871";  reg = <0x0b>; ... };
    camera_af_main2@0c { compatible = "mediatek,jd5516w_21871"; reg = <0x0c>; ... };

    /* EEPROM OTP Calibration */
    mtk_camera_eeprom0: camera_eeprom0@74 {
        compatible = "mediatek,camera_eeprom";
        reg = <0x74>;
        status = "okay";
    };

    /* Main Camera Sensor */
    sensor0: sensor0@36 {
        compatible = "mediatek,imgsensor";
        sensor-names = "ov64b_mipi_raw_22823", "imx890_mipi_raw_21871";
        reg = <0x36>;
        ...
    };
};
```
- **I2C Client Address**: `0x36` (7-bit address), 8-bit read/write address `0x6c` / `0x6d`.
- **EEPROM Address**: `0x74` (`camera_eeprom0`).
- **Sysfs Physical Path**: `/sys/bus/i2c/devices/8-0036` (live verified).

### 2.2 CSI Port and MIPI C-PHY Configuration
- **SENINF CSI Port**: `seninf_csi_port_3` (port index 3):
  ```dts
  port {
      sensor0_out: endpoint {
          remote-endpoint = <&seninf_csi_port_3_in>;
      };
  };
  ```
- **Physical Layer Bus**: MIPI C-PHY:
  - `.mipi_sensor_type = MIPI_CPHY`
  - `.mipi_lane_num = SENSOR_MIPI_3_LANE` (3 C-PHY trios: Trio A, Trio B, Trio C)
  - `.mipi_data_lp2hs_settle_dc = 85`
  - Symbol encoding: 3 wires per trio, 2.28 bits per symbol (higher data bandwidth than D-PHY at lower clock rate)
- **Master Clock (MCLK)**:
  - Source clock: `<&topckgen_clk CLK_TOPCKGEN_CAMTG4_SEL>`
  - Clock frequency: 24 MHz (`.mclk = 24`)
  - Pin routing: `PINMUX_GPIO208__FUNC_CMMCLK3`
  - Drive strengths: 2mA (`drive-strength = <0>`), 4mA (`<1>`), 6mA (`<2>`), 8mA (`<3>`)

### 2.3 GPIO Pin Controls
From `cust_mt6983_vitamin_camera_v4l2.dtsi:93-150`:
1. **MCLK**: `GPIO208` (`camera_pins_cam0_mclk_off` / `camera_pins_cam0_mclk_4ma`)
2. **Reset (RST)**: `GPIO202`
   - Active low reset: `camera_pins_cam0_rst_0` (`pinmux = <PINMUX_GPIO202__FUNC_GPIO202>; output-low;`)
   - Normal operation: `camera_pins_cam0_rst_1` (`output-high;`)
3. **Core Power Switch (DVDD)**: `GPIO194`
   - Power off: `camera_pins_cam0_dvdd_off` (`output-low;`)
   - Power on: `camera_pins_cam0_dvdd_on` (`output-high;`)

### 2.4 Voice Coil Motor (VCM / AF Actuators)
The Nord 3 uses multi-vendor VCM second-sourcing on I2C-8:
1. `camera_af_main@0a`: Asahi Kasei `ak7375c_22823` at `0x0a`
2. `camera_af_main1@0b`: Asahi Kasei `ak7377_21871` at `0x0b`
3. `camera_af_main2@0c`: Jingdao `jd5516w_21871` at `0x0c`
All three endpoints are muxed into `mtk_composite_v4l2_2` in the camera topology.

---

## 3. Power Rails and Bring-Up Power Sequence

From `imx890mipiraw_Sensor_21871.c:4656-4668` and `multi-regulator_vitamin.dtsi`:
The sub-PMIC supplies and GPIO lines execute the following strict 9-step power sequence:

| Step | Hardware Component | Action / Value | Delay | Details |
|---|---|---|---|---|
| 1 | `HW_ID_MCLK` | 24 MHz | 0 ms | Enable MCLK oscillator from CAMTG4 |
| 2 | `HW_ID_RST` | 0 (Low) | 1 ms | Assert sensor hardware reset |
| 3 | `HW_ID_AVDD` | 2.804 V | 3 ms | Enable Analog VDD via `multi_reg_ldo3` (Camera sub-PMIC WL2868C/FAN53870) |
| 4 | `HW_ID_AVDD1` | 1.804 V | 3 ms | Enable Secondary Analog VDD via `multi_reg_ldo6` |
| 5 | `HW_ID_AFVDD` | 2.804 V | 3 ms | Enable VCM Actuator VDD via `multi_reg_ldo5` |
| 6 | `HW_ID_DVDD` | 1 (High) | 4 ms | Assert GPIO194 high to activate Digital Core 1.1V/1.2V |
| 7 | `HW_ID_DOVDD` | 1.804 V | 3 ms | Enable Digital I/O VDD via `multi_reg_ldo7` |
| 8 | `HW_ID_MCLK_DRIVING_CURRENT` | 4 mA | 6 ms | Set MCLK drive strength to 4mA (`drive-strength = <1>`) |
| 9 | `HW_ID_RST` | 1 (High) | 5 ms | Deassert sensor reset to enter standby |

**Total Sequence Duration**: 22 ms.

### 3.1 Power-Down Sequence
During shutdown (`adaptor_hw_power_off`), the driver traverses `pw_seq` in reverse:
1. Deassert RST (low)
2. Reset MCLK driving current
3. Disable DOVDD (1.8V)
4. Deassert DVDD (GPIO194 low)
5. Disable AFVDD (2.8V)
6. Disable AVDD1 (1.8V)
7. Disable AVDD (2.8V)
8. Disable MCLK

---

## 4. Required Kernel Modules in Dependency Order

To bind and operate the IMX890 sensor, the kernel requires six modules in strict dependency order:
1. `mtk_cam_plat_util`: Base platform helpers and DMA memory primitives.
2. `mtk_cam_plat_mt6983`: MT6983 platform clock, power domain, and register abstractions.
3. `camera_eeprom`: I2C EEPROM calibration driver for `camera_eeprom0@74`.
4. `imgsensor`: MediaTek camera sensor core framework providing `/dev/v4l-subdev*`.
5. `mtk_cam_isp`: MediaTek ISP 7.1 driver (or volatile RAM-patched build for CAMSV routing).
6. `oplus_cam_event_report`: Vendor diagnostic and OLC exception notification layer.

---

## 5. Preflight Evaluation Tooling and Live State

The inspection tool [`lynx/tools/camera_deps/lynx_imx890_preflight.py`](file:///noobia/lynx/tools/camera_deps/lynx_imx890_preflight.py) provides:
- **Offline Evaluation**: Audits DT node mappings, C-PHY lanes, MCLK, VCM definitions, and power sequence against reference fixtures.
- **Read-Only Live Collector**: Gated behind `--live --allow-live`. Performs non-actuating read-only queries over SSH to audit `/sys/firmware/devicetree/base`, `/sys/bus/i2c/devices/8-*`, and `/proc/modules`.

### 5.1 Current Live State on Lynx (Boot `0fe847d2`)
Live inspection confirms:
- Node `/sys/firmware/devicetree/base/i2c@11d05000/sensor0@36` is present in device tree.
- Sysfs client `/sys/bus/i2c/devices/8-0036` exists (`name = imgsensor`).
- VCM clients `8-000a`, `8-000b`, `8-000c` and EEPROM `8-0074` exist.
- Driver binding: **UNBOUND** (quiescent).
- Kernel modules: **None loaded** (`imgsensor` absent from `/proc/modules`).
- Preflight Status: **`UNBOUND_QUIESCENT`** (Safe baseline).
