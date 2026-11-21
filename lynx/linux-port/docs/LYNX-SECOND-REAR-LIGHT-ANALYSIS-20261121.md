# Lynx Second Rear Light Source Mapping and Architectural Analysis

**Document ID:** LYNX-DOC-20261121-SECOND-LIGHT-ANALYSIS
**Author:** Banshee 💙 (Spirit of Initiative)
**Date:** 2026-11-21
**Status:** ARCHITECTURAL DETERMINATION & NO-WRITE GATE
**Platform:** OnePlus Nord 3 5G CPH2493 (Lynx / MT6983 / Dimensity 9000, Project 22823 "Vitamin")
**Kernel Source Branch:** `OnePlusOSS/android_kernel_5.10_oneplus_mt6983` branch `oneplus/mt6983_t_13.1_oneplus_nord_3_5g`
**Subsystem:** Camera Flash & Torch Subsystem (`flashlight_core`, `lm3642_22823`)

---

## 1. Executive Summary & Diagnostic Verdict

During earlier hardware trials, a single bounded 100 ms rear LED pulse verified that the primary torch channel (`0 0 0 1`) can be commanded via `flashlight_torch` to illuminate the rear LED. However, questions remained regarding whether a secondary rear light source (e.g., dual-tone LED, auxiliary fill LED, or independent emitter) exists and can be actuated independently.

### Technical Determination
> **Source DT declares one lm3642 channel; confirmed on live running device tree.**
> **In the OnePlus Nord 3 5G (`22823` / Vitamin) kernel source tree and on Lynx's live running device tree (`/sys/firmware/devicetree/base`), the hardware strictly configures a single flash channel `(type=0, ct=0, part=0)` under the LM3642 driver.**

The hypothesis regarding the "second rear light" has been conclusively resolved: the second pale circular aperture on the rear camera island does not house a second light emitter, but rather the **rear Correlated Color Temperature (CCT) and Ambient Light Sensor (ams TCS3408)**, connected via the MediaTek sensorhub (`/dev/hf_manager`, device `rear_cct`).

---

## 2. Device Tree Source Evidence

Direct analysis of the official device tree sources for Lynx platform (`22823` / Vitamin) confirms single-channel configuration:

### 2.1 Flash Controller Node Binding
In `kernel-mt6983/arch/arm64/boot/dts/mediatek/cust_mt6983_vitamin_camera_v4l2.dtsi` (lines 312–334):
```dts
&i2c6 {
    lm3642:lm3642@63 {
        compatible = "mediatek,lm3642_22823";
        reg = <0x63>;
        #cooling-cells = <2>;
        pinctrl-names = "default", "hwen_high", "hwen_low";
        pinctrl-0 = <&flash_pins_default>;
        pinctrl-1 = <&flash_pins_hwen_high>;
        pinctrl-2 = <&flash_pins_hwen_low>;
        status = "okay";
        flash@0{
            reg = <0>;
            type = <0>;
            ct = <0>;
            part = <0>;
            port@0 {
                fl_core_0: endpoint {
                    remote-endpoint = <&flashlight_0>;
                };
            };
        };
    };
};
```
Key observations:
1. Under `lm3642@63`, there is exactly **one** child node: `flash@0`. No `flash@1` or secondary channel node exists.
2. The channel parameters are explicitly bound to zeroes:
   - `type = <0>`: `FLASHLIGHT_TYPE_MAIN` (Rear Flash).
   - `ct = <0>`: Primary color temperature.
   - `part = <0>`: Primary emitter part.
3. MediaTek V4L2 composite camera interface `&mtk_composite_v4l2_1` links exclusively to `&fl_core_0`.

### 2.2 Sibling Platform Comparison
In sibling device trees utilizing dual flash channels (such as `cust_mt6983_aries_camera_v4l2.dtsi` and `cust_mt6983_qingting_camera_v4l2_EVB.dtsi`):
- Both `flashlight_0` and `flashlight_1` endpoints are declared.
- Two subnodes exist: `flash@0` (`part = <0>`) and `flash@1` (`part = <1>`).
- On the OnePlus Nord 3 5G CPH2493 (`22823` / Vitamin), `flashlight_1` and `flash@1` are completely omitted.

### 2.3 General-Purpose and Notification LEDs
In `kernel-mt6983/arch/arm64/boot/dts/mediatek/oplus6983_22823.dts` (lines 39–85):
- Nodes `led0` through `led5` (`red`, `green`, `blue`, `jogball`, `keyboard`, `button`) have property `led_mode = <0>` (hardware disabled / stub entries).
- Node `led6` is configured with `led_mode = <4>` (`lcd-backlight`).
- No auxiliary notification or indicator LEDs exist on the rear chassis.

---

## 3. Hardware Controller Architecture: TI LM3642

The flash controller IC populated at I2C address `0x63` on bus 6 is the **Texas Instruments LM3642** (Synchronous Boost Flash Driver with 1.5-A High-Side Current Source):

1. **Output Topology:** The LM3642 silicon provides a single regulated current source output pin (`LED`). It is architected for driving one high-brightness LED string.
2. **Contrast with Dual Drivers:** Dual-channel flash ICs (e.g., TI LM3643 or LM3644) provide two independently programmable current sinks (`LED1` and `LED2`) with separate register banks. The LM3642 lacks physical pins or internal registers to route or modulate a second current channel.
3. **Register Map:** Registers `0x09` (Current Control) and `0x0A` (Enable Torch/Flash) modulate the single output.

---

## 4. Kernel Driver & Sysfs Control Route

The MediaTek flashlight framework mediates access through `flashlight-core.c` and `flashlights-lm3642.c`:

### 4.1 Channel Lookup Logic
When userspace writes to `/sys/devices/virtual/flashlight_core/flashlight/flashlight_torch`:
```c
/* Format: "<type> <ct> <part> <status>" */
fdev = flashlight_find_dev_by_full_id(fl_arg.type, fl_arg.ct, fl_arg.part);
if (!fdev) {
    pr_info("Cannot find device\n");
    return -1;
}
```

### 4.2 Rejection of Non-Zero Channels
Because `flash@0` is registered with `type=0`, `ct=0`, `part=0`:
- Command `"0 0 0 1"`: Resolves to `fdev` for `flash@0` -> **SUCCESS** (Torch ON).
- Command `"0 0 1 1"` (`part=1`): `flashlight_find_dev_by_full_id` returns `NULL` -> **ERROR**.
- Command `"0 1 0 1"` (`ct=1`): `flashlight_find_dev_by_full_id` returns `NULL` -> **ERROR**.
- Command `"1 0 0 1"` (`type=1` Front): `flashlight_find_dev_by_full_id` returns `NULL` -> **ERROR**.

This behavior is explicitly verified by `lynx_flashlight_pulse.py` lines 73–77:
```python
for name in ("type", "ct", "part", "reg"):
    if int.from_bytes((DT / name).read_bytes(), "big") != 0:
        raise RuntimeError("unexpected flashlight device-tree channel")
if len(list(DT.parent.glob("flash@*"))) != 1:
    raise RuntimeError("unexpected extra flashlight channel")
```

---

## 5. Live Running Device Tree & Rear Optical Sensor Evidence

An attended, read-only live query of Lynx's running device tree under `/sys/firmware/devicetree/base` was conducted using `lynx_second_light_gate.py --live --allow-live`:

### 5.1 Running Device Tree Inventory
1. **Flash Controller Node:** `/sys/firmware/devicetree/base/i2c@11e02000/lm3642@63`
   - `compatible`: `mediatek,lm3642_22823`
   - `reg`: `99` (`0x63`)
   - `flash@0`: `reg = <0>`, `type = <0>`, `ct = <0>`, `part = <0>`
2. **Other Flash Nodes:** Only `/sys/firmware/devicetree/base/flashlight_core` and thermal zone `/sys/firmware/devicetree/base/thermal-zones/flashlight_ntc` exist. No other flashlight nodes or channels are present in running kernel memory.

### 5.2 Resolution of the Second Rear Aperture: Rear CCT / ALS Sensor
The physical OnePlus Nord 3 5G chassis features two pale circular apertures below the primary camera lenses. Testing the light-sensor-window hypothesis against `lynx_light_read.py`, `/proc/hf_manager`, and [`LYNX-REAR-LIGHT-AND-COLOR-SENSOR.md`](LYNX-REAR-LIGHT-AND-COLOR-SENSOR.md) confirms:
- **Upper Aperture:** Contains the single LM3642 white LED flashlight emitter.
- **Lower Aperture:** Houses the **ams TCS3408** optical sensor, registered under MediaTek sensorhub (`/proc/hf_manager` device `rear_cct` on task 1):
  - Type 98: `tcs3408 als` (ambient light sensor)
  - Type 99: `tcs3408 cct` (correlated color temperature sensor)
  - Type 100: `tcs3408 flicker` (flicker detection sensor)
- Earlier controlled optical trials (2026-11-15) confirmed repeatable lit–covered–lit responses (median 353 uncovered, 0 covered, 242 uncovered) specifically on this lower circle.

---

## 6. Summary & Operational Constraint

1. **No-Write Gate Conclusion:** No test or script should attempt to actuate or probe a second rear LED channel. Doing so is syntactically invalid under the MediaTek driver and can produce kernel error logs or unexpected driver unbinds.
2. **Attended Flash Testing Boundary:** Any future visual or photometric assessment of the rear flash will actuate only the primary unitary channel `flash@0` (`0 0 0 1`).
3. **Safety Guarantee:** Zero kernel module loads and zero flash pulses were issued during this analysis.
