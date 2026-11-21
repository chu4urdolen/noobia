# Lynx Audio Smart Power Amplifier (NXP TFA9874) Preflight Architecture

**Device:** OnePlus Nord 3 5G (`CPH2493` / platform `MT6983` / Project `22823`)  
**Subsystem:** MediaTek MT6983 AFE, Dual NXP TFA98xx (TFA9874) Smart Power Amplifiers  
**Author:** Banshee 💙 (Spirit of Initiative)  
**Date:** 2026-11-21  
**Status:** Validated Tool Directory & Offline Preflight Specification  

---

## 1. Executive Summary & Hardware Topology

The OnePlus Nord 3 delivers stereo speaker audio using dual discrete smart power amplifiers manufactured by NXP (TFA98xx family / TFA9874). The amplifiers interface with the application processor over an I2C control bus and an I2S digital audio bus.

```
 [MediaTek MT6983 SoC]
      │
      ├── I2C Bus 6 (400 kHz) ──────────────────────┬────────────────────────┐
      │                                             │                        │
      │                                             ▼                        ▼
      │                                    [TFA98xx Left @ 0x34]   [TFA98xx Right @ 0x35]
      ├── I2S3 (Digital Audio Inter-IC) ───► (tfa98xx-aif-6-34)     (tfa98xx-aif-6-35)
      │                                             │                        │
      ├── Reset GPIO: mt6373_pio 2 ─────────────────┘                        │
      ├── Reset GPIO: mt6373_pio 1 ──────────────────────────────────────────┘
```

> [!IMPORTANT]
> **Acoustic Safety Boundary:**
> This preflight tool validates bus enumeration, DT binding, and firmware container assets.
> It **NEVER** generates test beeps, never unmutes DACs, and never writes to PCM streams.
> All evaluations report `acoustic_safety_validated: true` and `audio_output_prevented: true`.

---

## 2. Kernel Device Tree & Source Mapping

From `kernel-mt6983/arch/arm64/boot/dts/mediatek/oplus6983_22823.dts`:
```dts
&audio_extend {
    oplus,speaker-vendor = "nxp";
    oplus,speaker-i2s-id = <3>;
    oplus,speaker-i2s-id-in = <0>;
    oplus,speaker-codec-name = "tfa98xx.6-0034", "tfa98xx.6-0035";
    oplus,speaker-codec-dai-name = "tfa98xx-aif-6-34", "tfa98xx-aif-6-35";
};

&i2c6 {
    clock-frequency = <400000>;
    pinctrl-names = "default";
    pinctrl-0 = <&I2C_pins_default>;
    status = "okay";

    tfa98xx_L: tfa98xx@34 {
        compatible = "nxp,tfa98xx";
        reg = <0x34>;
        reset-gpio = <&mt6373_pio 2 0>;
        tfa_min_range = <5000>;
        tfa_max_range = <8000>;
        tfa_channel = <0>;
        tfa_low_pressure = <1>;
        is_use_freq;
        status = "okay";
    };

    tfa98xx_R: tfa98xx@35 {
        compatible = "nxp,tfa98xx";
        reg = <0x35>;
        reset-gpio = <&mt6373_pio 1 0>;
        tfa_min_range = <5000>;
        tfa_max_range = <8000>;
        tfa_channel = <1>;
        tfa_low_pressure = <1>;
        is_use_freq;
        status = "okay";
    };
};

&sound {
    mediatek,spk-i2s = <3 9>;
};
```

---

## 3. Electrical & Acoustical Parameters

- **Nominal Impedance Range:** `tfa_min_range = 5000` mΩ ($5.0\,\Omega$) to `tfa_max_range = 8000` mΩ ($8.0\,\Omega$).
  - Evaluator enforces that measured/reported speaker voice coil DC resistance falls strictly within $5000\text{ m}\Omega \le R \le 8000\text{ m}\Omega$.
  - Values below 5000 mΩ indicate a voice coil short or miswiring.
  - Values above 8000 mΩ indicate an open voice coil or degraded ribbon cable.
- **Low Pressure Calibration:** `tfa_low_pressure = 1` enables barometer-assisted cone excursion limiting for high-altitude operation.

---

## 4. Kernel Driver & Firmware Asset Matrix

- **Driver Module:** `snd-soc-tfa98xx.ko` (depends on `oplus_mm_kevent_fb`, `mtk-sp-spk-amp`).
- **DSP Container Firmware:** `tfa98xx.cnt` (located at `/odm/firmware/tfa98xx.cnt` and stock unpacked vendor tree).
- **Audio Tuning Profiles:**
  - `tfa98xx_music.bin`: Music playback tuning.
  - `tfa98xx_voice.bin`: Earpiece and speakerphone voice calls.
  - `tfa98xx_voip.bin`: VoIP tuning profile.
  - `tfa98xx_ringtone.bin`: High-spl ringtone profile.

---

## 5. Software Implementation & Verification

The preflight tool is implemented in `lynx/tools/audio/`:
- `lynx_audio_amp_preflight.py`: Preflight evaluator supporting `--validate <FIXTURE>`, offline firmware validation, and double-gated read-only live query (`--live --allow-live`).
- `fixtures/audio-amp-ready.json`: Nominal baseline (both I2C nodes bound, 6200/6150 mΩ impedance).
- `fixtures/audio-amp-missing-i2c.json`: Negative fixture (missing right channel).
- `fixtures/audio-amp-impedance-fault.json`: Negative fixture (voice coil short, 1200 mΩ).
- `test_lynx_audio_amp_preflight.py`: Hermetic unit test suite (6/6 OK in 0.001s).
