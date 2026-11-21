# Lynx Headset Insertion Evidence and Architectural Boundary

**Document ID:** LYNX-DOC-20261121-HEADSET-EVIDENCE  
**Author:** Banshee 💙 (Spirit of Initiative)  
**Date:** 2026-11-21  
**Status:** ARCHITECTURAL SPECIFICATION & ATTENDED TRIAL PROTOCOL  
**Platform:** OnePlus 11R 5G (Lynx / MT6895 / Dimensity 9000-series platform)  
**Subsystem:** PMIC Audio Switch (`mt6983-mt6338 Headset Jack`, `/dev/input/event1`)  

---

## 1. Hardware Architecture & Route Tracing

The OnePlus 11R 5G chassis lacks a dedicated legacy 3.5 mm TRRS analog audio jack. Analog headset connectivity and jack detection are mediated through the USB Type-C connector via the MediaTek MT6338 PMIC audio accessory detection block and Type-C analog audio accessory mode (or Type-C DAC accessories).

### 1.1 Input Subsystem Mapping
In the Linux kernel, the MT6338 audio accessory driver registers an input device:
- **Device Name:** `mt6983-mt6338 Headset Jack`
- **Sysfs Node:** `/sys/class/input/event1` (symlinked from platform input hierarchy)
- **Character Device:** `/dev/input/event1`
- **Event Type:** `EV_SW` (`0x05` — Switch State Events)

### 1.2 Switch Event Codes
The driver exposes four distinct switch bits defined in `linux/input-event-codes.h`:
| Switch Identifier | Code (`int`) | Semantic Meaning |
|:---|:---:|:---|
| `SW_HEADPHONE_INSERT` | `0x02` | Headphone output impedance detected ($\approx 16\text{–}600\,\Omega$) |
| `SW_MICROPHONE_INSERT` | `0x04` | Microphone line detected (bias voltage drop / MIC pull-up) |
| `SW_LINEOUT_INSERT` | `0x06` | Line-out impedance detected ($> 1\,\text{k}\Omega$) |
| `SW_JACK_PHYSICAL_INSERT` | `0x07` | Physical plug insertion sense switch closed |

### 1.3 Read-Only Status Extraction
The live status of these switches is polled non-destructively through the standard Linux input ioctl:
```c
#define EVIOCGSW(len) _IOC(_IOC_READ, 'E', 0x1b, len)
```
Querying 8 bytes (`EVIOCGSW(8) = 0x8008451B`) yields a 64-bit bitmask where bit $k$ indicates whether switch $k$ is active (`1`) or inactive (`0`).

Current baseline on Lynx:
```json
{
  "headphone": false,
  "lineout": false,
  "microphone": false,
  "physical": false
}
```

---

## 2. Critical Diagnostic Boundary: Jack Sense vs. Audio Routing

A fundamental requirement of hardware verification is establishing the exact boundary of what a sensor test proves.

### Boundary Statement
> **Detecting an `EV_SW` switch state change proves only that the electrical/impedance sense circuit on the PMIC or Type-C accessory multiplexer detected connection. It does NOT prove that audio can be routed, heard, or captured.**

```
Physical Insertion (Type-C Audio Adapter)
              |
              v
[PMIC MT6338 Impedance & Contact Sense]  <--- Validated by lynx_headset_collector.py
              |
         EV_SW event
              |
              v
[Kernel Input Subsystem /dev/input/event1]
========================================================================================
[ARCHITECTURAL GAP / UNVALIDATED BOUNDARY: Routed Audio]
========================================================================================
              |
     (Userspace / ALSA Mixer)
              v
[MTK Audio DSP Firmware & IPI Messaging]
              |
              v
[ALSA PCM DAI Links (snd_soc_audiodsp)]
              |
              v
[Codec DAC / ADC & Headphone Amp Controls]
              |
              v
Acoustic Output (Sound Heard by Human)   <--- Requires separate attended audio plan
```

### Why Jack Detection Is Insufficient for Audio Routing
1. **No Mixer Binding:** The input switch driver does not automatically configure ALSA controls (`amixer` / `tinymix`). DAC output paths (`HP_L`, `HP_R`), analog gain stages, and mute switches remain unasserted.
2. **DSP Pipeline Dependency:** Modern MediaTek audio relies on an Audio DSP co-processor running proprietary firmware (`snd_soc_audiodsp_common`, `audio_ipi`). If DSP firmware fails to load or IPI communication times out, PCM stream playback fails even if jack detection is 100% functional.
3. **Power Rails & Clocks:** Headphone amplifiers and DAC reference voltages are dynamically powered via PMIC regulators (e.g., `VPP_1V8`, `VAUX18_PMIC`). Jack detection does not energize these audio output rails.
4. **Type-C Digital Dongles:** Digital USB audio dongles (containing their own USB DAC/ADC) do not trigger PMIC analog jack switches at all; they enumerate as USB Audio Class (`snd-usb-audio`) endpoints over USB host mode.

---

## 3. Passive Bounded Event Collector Design

To safely verify jack detection without altering system state, `/noobia/lynx/tools/headset/lynx_headset_collector.py` implements:

1. **Non-Blocking Operation:** Opens `/dev/input/event1` with `O_RDONLY | O_NONBLOCK`.
2. **Time-Bounded Polling:** Uses `select.select()` with a default 5.0-second timeout. It never blocks or hangs waiting for user action.
3. **Zero Audio-Route Writes:** No calls to ALSA kcontrols, no module reloads, and no sysfs writes.
4. **Strict Verdict Classification:**
   - `PASS_UNPLUGGED`: Switch device is accessible and reads all switches as false.
   - `PASS_DETECTED`: Switch device reads one or more active switches (headphone/mic/physical), but explicitly marks `routed_audio_validated: False`.
   - `FAILED`: IO error, missing device node, or malformed bitmask.

---

## 4. Attended Physical Insertion Protocol (Future Human Trial)

When Noob is present with Lynx and a compatible USB Type-C analog audio adapter or headset:

1. **Safety Preconditions:**
   - Lynx battery $\ge 20\%$.
   - Primary Wi-Fi SSH connection active on port 2222.
   - Zero concurrent audio playback processes running.
2. **Execution Steps:**
   - Step 1: Start collector in bounded listen mode on Lynx:
     ```bash
     python3 /noobia/lynx/tools/headset/lynx_headset_collector.py --listen --timeout 15.0
     ```
   - Step 2: During the 15-second window, insert the Type-C headset into Lynx.
   - Step 3: Observe captured `EV_SW` event trace:
     - Expect `SW_JACK_PHYSICAL_INSERT` (`code 7, value 1`).
     - Expect `SW_HEADPHONE_INSERT` (`code 2, value 1`).
     - If microphone is present on headset, expect `SW_MICROPHONE_INSERT` (`code 4, value 1`).
   - Step 4: Validate generated receipt using offline validator:
     ```bash
     python3 /noobia/lynx/tools/headset/lynx_headset_collector.py --validate /path/to/receipt.json
     ```
3. **Acceptance Criteria:**
   - Receipt records transition to inserted state.
   - Offline validator reports `PASS_DETECTED` with `is_valid: true`.
   - `routed_audio_validated` remains strictly `false`.
