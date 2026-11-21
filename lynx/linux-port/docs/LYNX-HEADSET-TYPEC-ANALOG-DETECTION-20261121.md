# Lynx Headset & Type-C Analog Accessory Detection Trace

**Device:** OnePlus Nord 3 5G (`CPH2493` / platform `MT6983` / board `oplus6983_22823`)  
**Subsystem:** Audio Accessory Detection (`accdet`), Type-C Crossbar MUX (`fsa4480`), and PMIC ADC Sense  
**Author:** Banshee 💙 (Spirit of Initiative)  
**Date:** 2026-11-21  
**Status:** Validated Architecture & Offline Decoder Specification  

---

## 1. Hardware Architecture Overview

The OnePlus Nord 3 does **not** feature a dedicated 3.5mm TRS/TRRS audio jack. All analog audio input and output for wired headphones and headsets are routed through the phone's single USB Type-C receptacle.

Detecting and routing analog audio accessories requires a synchronized three-tier hardware chain:
1. **USB Type-C CC Port Controller (TCPC MT6375):** Detects physical connection and accessory termination impedance on Configuration Channel pins (CC1 / CC2).
2. **Analog Audio Crossbar MUX (FSA4480 / DIO4480):** High-speed 0.4Ω DPDT bilateral analog switch with negative rail capability on I2C6 (slave `0x42`), routing Type-C high-speed data pins (`DP`/`DM`) and sideband pins (`SBU1`/`SBU2`) between digital USB PHY and analog audio paths.
3. **PMIC Accessory Detection Subsystem (MT6338 ACCDET):** High-precision AUXADC impedance comparator measuring voltage drops on the MIC and GND lines to classify 3-pole headphones, 4-pole headsets, line-out cables, and inline button presses.

```
 [USB Type-C Receptacle]
      │
      ├── CC1 / CC2 ───────> MT6375 TCPC (Detects Ra/Ra Audio Accessory Mode)
      │                            │
      │                            ▼ (TYPEC_ATTACHED_AUDIO event)
      ├── DP / DM ─────────> FSA4480 I2C MUX (reg 0x42 on &i2c6)
      │   (D+ / D-)                ├── Routes DP/DM -> PMIC HPR / HPL
      │                            ├── Routes SBU1/SBU2 -> PMIC MIC / AGND
      ├── SBU1 / SBU2              ├── Automatic OMTP <-> CTIA ground swapping
      │                            └── Asserts hs-det-gpio (GPIO98)
      │                                    │
      ▼                                    ▼
 [MT6338 PMIC ACCDET] <────────────────────┘
      │
      ├── AUXADC_ACCDET (Measures MIC impedance)
      ├── Classifies: 3-Pole (HP), 4-Pole (Headset), Line-Out, or Button Key
      ▼
 [Linux Input Subsystem]
      │
      └── /dev/input/event* ("mt6983-mt6338 Headset Jack")
           ├── EV_SW: SW_HEADPHONE_INSERT (0x02)
           ├── EV_SW: SW_MICROPHONE_INSERT (0x04)
           ├── EV_SW: SW_LINEOUT_INSERT (0x06)
           └── EV_SW: SW_JACK_PHYSICAL_INSERT (0x07)
```

---

## 2. Kernel Device Tree & Source Mapping

### 2.1 Type-C Audio Mux (`fsa4480`)
From `kernel-mt6983/arch/arm64/boot/dts/mediatek/oplus6983_22823.dts`:
```dts
&i2c6 {
    fsa4480: fsa4480@42 {
        compatible = "qcom,fsa4480-i2c";
        reg = <0x42>;
        fsa_audio-supply = <&mt6373_vio28>;
        pinctrl-names = "default";
        pinctrl-0 = <&fsa_hs_det>;
        fsa4480,hs-det-gpio = <&pio 98 0>;
    };
};

&pio {
    fsa_hs_det: fsa_hs_det {
        pins_cmd_dat {
            pinmux = <PINMUX_GPIO98__FUNC_GPIO98>;
            slew-rate = <1>;
            output-high;
        };
    };
};
```
- **Driver Module:** `fsa4480-i2c.ko` (depends on `tcpc_class`, `mux_switch`, `oplus_mm_kevent_fb`).
- **Power Supply:** `mt6373_vio28` (2.8V LDO rail powered up during audio accessory mode).
- **Control Interface:** I2C Bus 6, 7-bit slave address `0x42`.
- **Interrupt / Detection Pin:** `GPIO98` configured as headset detection output to the AP / PMIC.

### 2.2 PMIC ACCDET (`mt6338_accdet`)
From `kernel-mt6983/arch/arm64/boot/dts/mediatek/mt6983.dts`:
```dts
sound: sound {
    compatible = "mediatek,mt6983-mt6338-sound";
    mediatek,headset-codec = <&mt6338_accdet>;
    mediatek,platform = <&afe>;
};

mt6338_accdet: mt6338_accdet {
    compatible = "mediatek,mt6338-accdet";
    accdet-name = "mt6338-accdet";
    accdet-mic-vol = <8>;
    accdet-plugout-debounce = <1>;
    accdet-mic-mode = <2>;
    eint_use_ext_res = <0>;
    headset-mode-setting = <0x500 0x500 1 0x1f0
                            0x800 0x800 0x20 0x44
                            0x4 0x1
                            0x5 0x3 0x3 0x5 0xe>;
    headset-use-ap-eint = <0>;
    headset-eint-num = <0>;
    headset-eint-trig-mode = <1>;
    headset-key-mode = <0>;
    headset-three-key-threshold = <0 82 170 306>;
    headset-three-key-threshold-CDD = <0 121 192 600>;
    headset-four-key-threshold = <0 58 121 192 400>;
    io-channels = <&mt6338_auxadc AUXADC_ACCDET>;
    io-channel-names = "pmic_accdet";
    nvmem = <&mt6338_efuse>;
    nvmem-names = "mt63xx-accdet-efuse";
    status = "okay";
};
```
- **Driver Module:** `mt6338-accdet.ko` (depends on `scp`, `mtk_tinysys_ipi`, `oplus_mm_kevent_fb`).
- **ADC Channel:** `mt6338_auxadc AUXADC_ACCDET` (calibrated against `mt63xx-accdet-efuse`).

---

## 3. Switch-Bit Meanings on Nord 3

The kernel exports accessory state through Linux Input subsystem switches (`EV_SW` on device `"mt6983-mt6338 Headset Jack"`, queryable via `ioctl(fd, EVIOCGSW(8))`):

| Switch Code | Name | Value | Physical Hardware Meaning on OnePlus Nord 3 |
|---|---|---|---|
| `0x02` | `SW_HEADPHONE_INSERT` | `0` or `1` | **Headphone Output Active:** Asserted when headphone impedance is detected on Left/Right channels routed through FSA4480 DP/DM. Present for both 3-pole headphones and 4-pole headsets. |
| `0x04` | `SW_MICROPHONE_INSERT` | `0` or `1` | **Microphone Input Active:** Asserted when AUXADC measures microphone capsule resistance (nominally 1kΩ–3kΩ) on SBU line. Deasserted for 3-pole headphones where MIC is tied to AGND. |
| `0x06` | `SW_LINEOUT_INSERT` | `0` or `1` | **Line-Out Active:** Asserted when impedance comparator detects high load resistance (> 10kΩ). PMIC configures driver stage for line-level voltage rather than headphone power. |
| `0x07` | `SW_JACK_PHYSICAL_INSERT`| `0` or `1` | **Accessory Mechanically Present:** Master presence bit. Driven by TCPC $R_a/R_a$ detection on Type-C CC pins and FSA4480 assertion of GPIO98 (`hs-det-gpio`). |

### 3.1 State Truth Table

| Accessory Plugged In | `physical (0x07)` | `headphone (0x02)` | `microphone (0x04)` | `lineout (0x06)` | Classification |
|---|---|---|---|---|---|
| **Unplugged** | 0 | 0 | 0 | 0 | `ACCESSORY_UNPLUGGED` |
| **4-Pole Headset (CTIA/OMTP)** | 1 | 1 | 1 | 0 | `ACCESSORY_HEADSET_4POLE` |
| **3-Pole Headphones** | 1 | 1 | 0 | 0 | `ACCESSORY_HEADPHONES_3POLE` |
| **Line-Out Cable / Amp** | 1 | 0 | 0 | 1 | `ACCESSORY_LINEOUT` |
| **Inconsistent Permutations** | Any other combination (e.g. physical=0 but headphone=1) | `ACCESSORY_INVALID` |

---

## 4. Key Impedance Comparator Thresholds

When a 4-pole headset with inline buttons is inserted, pressing a button places a shunt resistor across MIC and GND, dropping the voltage measured by `AUXADC_ACCDET`.

From the OnePlus Nord 3 DT configuration:
- `headset-three-key-threshold = <0 82 170 306>` (millivolts):
  - **0 mV to 82 mV:** `KEY_PLAYPAUSE` (0Ω hook switch short to ground)
  - **82 mV to 170 mV:** `KEY_VOLUMEUP` (~240Ω shunt)
  - **170 mV to 306 mV:** `KEY_VOLUMEDOWN` (~470Ω shunt)
  - **> 306 mV:** Normal open microphone audio streaming state.
- `headset-four-key-threshold = <0 58 121 192 400>`:
  - Supports 4-button accessories incorporating `KEY_VOICECOMMAND` (Google Assistant).

---

## 5. Architectural Boundary

> [!IMPORTANT]
> **Switch Sense vs Routed Audio Separation:**
> Mechanical and impedance switch detection (`EV_SW`) verifies **only** the physical presence and electrical classification of the attached accessory.
>
> Switch state **DOES NOT**:
> 1. Verify ALSA PCM stream negotiation or buffer allocation.
> 2. Verify ADSP / SCP firmware operation or audio IPI messaging.
> 3. Verify DAC enablement or unmute status on MT6338 ADDA codec.
> 4. Guarantee acoustic output from speakers/earpieces or capture from the microphone.
>
> Evaluators and collectors must report `routed_audio_validated: false` whenever querying switch states.

---

## 6. Software Implementation & Verification

The detection logic is implemented in `lynx/tools/headset/lynx_headset_collector.py` and tested hermetically in `lynx/tools/headset/test_lynx_headset_collector.py`:
- `decode_accessory_type(switches)`: Strict classification of 3-pole, 4-pole, line-out, unplugged, and invalid states.
- Enhanced fixture support for Type-C MUX metadata (`FSA4480`, `GPIO98`, `mt6375_typec`), line-out detection, and invalid permutations.
- Hermetic test suite covers all combinations offline with 100% test pass rate.
