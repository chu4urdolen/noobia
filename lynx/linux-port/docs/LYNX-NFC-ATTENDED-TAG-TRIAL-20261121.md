# Lynx NFC Tag-Exchange Attended Trial Plan

**Document ID:** LYNX-DOC-20261121-NFC-TAG-TRIAL  
**Author:** Banshee 💙 (Spirit of Initiative)  
**Date:** 2026-11-21  
**Status:** DRAFT / ATTENDED TRIAL SPECIFICATION  
**Target Hardware:** OnePlus 11R 5G (Lynx / MT6895 / Dimensity 9000-series platform)  
**NFC Controller:** NXP SN110T NFC / eSE / eUICC combo (`/dev/nq-nci`, I2C address `0x28`)  

---

## 1. Executive Summary & Diagnostic Separation

During the V53 testing phase, the kernel modules `oplus_nfc.ko` and `nfc_i2c.ko` successfully probed the NXP SN110T controller over I2C, creating `/dev/nq-nci` and returning a valid chip version response:
```json
{
  "chip_type": "0xa4",
  "rom_version": "0x01",
  "fw_version": "0x10.68"
}
```

### Critical Boundary Statement
> **A successful chip version response validates only host-to-controller I2C bus wiring, power rail enablement, and controller bootloader/firmware responsiveness. It does NOT prove RF field generation, antenna resonance matching, transmitter RF power delivery, receiver sensitivity, or bidirectional tag exchange.**

Operating an active RF polling loop draws significant current, emits electromagnetic radiation, and requires physical presentation of a compatible NFC tag near the antenna coil (located around the rear camera island). This trial must only be executed as an attended, bounded session.

---

## 2. Pre-Requisites & Safety Gates

Prior to initiating the attended NFC RF polling sequence, the test operator and test harness must satisfy the following preconditions:

1. **Battery Gate:** Battery charge level must be $\ge 50\%$ (`lynx_battery_status` or `/sys/class/power_supply/battery/capacity`). If below 50%, the trial must be blocked to prevent brownouts under dynamic RF transmitter power load.
2. **Thermal Gate:** AP and battery temperatures must be $< 40^\circ\text{C}$.
3. **Physical Tag Presence:** A passive ISO/IEC 14443 Type A test tag (e.g., NTAG213/215/216 or MIFARE Classic/Ultralight) must be physically positioned adjacent to the upper rear chassis / camera bump.
4. **Time-Bounded RF Polling:** Maximum continuous RF polling duration is strictly capped at **15 seconds**. If no tag is activated within 15 seconds, the controller must immediately de-assert the RF carrier.
5. **Recovery Route Non-Interference:** The trial must not alter or reload Wi-Fi (`wlan0`) or USB gadget networking. The primary SSH session on port `2222` must remain uninhibited.

---

## 3. NCI Command Flow Specification

Communication with the SN110T occurs via the NFC Controller Interface (NCI 1.0 / 2.0) over `/dev/nq-nci`.

```
Host (Lynx Linux)                               NXP SN110T Controller
      |                                                  |
      |--------------- CORE_RESET_CMD ------------------>|
      |<-------------- CORE_RESET_RSP -------------------|
      |<-------------- CORE_RESET_NTF -------------------| (NCI 2.0 reset keep config)
      |                                                  |
      |--------------- CORE_INIT_CMD ------------------->|
      |<-------------- CORE_INIT_RSP --------------------|
      |                                                  |
      |--- RF_DISCOVER_CMD (Type A Poll Mode: 0x00) ---->|
      |<-------------- RF_DISCOVER_RSP ------------------|
      |                                                  | [RF Field ON: Polling 106 kbps]
      |                                                  |   | (Tag enters field)
      |                                                  |   v
      |<---------- RF_INTF_ACTIVATED_NTF ----------------| (UID, SAK, ATQA extracted)
      |                                                  |
      |---- RF_DEACTIVATE_CMD (Discovery / Idle) ------->|
      |<----------- RF_DEACTIVATE_RSP -------------------| [RF Field OFF]
      |                                                  |
```

### 3.1 Step 1: Core Reset (`CORE_RESET_CMD`)
- **Host Send:** `20 00 01 01` (Reset Type: Keep Configuration)
- **Expected RSP:** `40 00 03 00 10 01` (Status: `0x00` OK, NCI Version: `0x10`, Configuration Status)

### 3.2 Step 2: Core Initialization (`CORE_INIT_CMD`)
- **Host Send:** `20 01 00` (Length 0)
- **Expected RSP:** `40 01 ...` (Status: `0x00` OK, Controller Features, Max Payload, Routing tables)

### 3.3 Step 3: RF Discovery Configuration (`RF_DISCOVER_CMD`)
Configure polling for NFC-A (ISO/IEC 14443 Type A) technology:
- **Host Send:** `21 03 05 01 00 01 03 01`
  - Number of Configurations: `01`
  - RF Technology and Mode: `0x00` (NFC-A Poll Mode)
  - Discovery Frequency: `0x01` (Every discovery cycle)
- **Expected RSP:** `41 03 01 00` (Status: `0x00` OK)

### 3.4 Step 4: RF Activation Notification (`RF_INTF_ACTIVATED_NTF`)
When the physical tag is modulated and responds to WUPA / REQA and Anticollision cascade:
- **Expected NTF:** `61 05 <Payload Length> ...`
  - RF Discovery ID: `0x01`
  - RF Interface: `0x02` (Frame RF Interface)
  - RF Protocol: `0x02` (T2T or ISO-DEP / T4T)
  - Activation RF Technology & Mode: `0x00` (NFC-A Poll)
  - Specific Parameters:
    - SENS_RES / ATQA (2 bytes)
    - NFCID1 / UID Length (e.g., 4, 7, or 10 bytes)
    - NFCID1 / UID Data bytes
    - SEL_RES / SAK (1 byte)

### 3.5 Step 5: RF Deactivation (`RF_DEACTIVATE_CMD`)
Immediately following tag activation receipt, or upon expiration of the 15-second watchdog timer:
- **Host Send:** `21 06 01 00` (Deactivate to Idle Mode)
- **Expected RSP:** `41 06 01 00` (Status: `0x00` OK)
- **Expected NTF:** `61 06 02 00 00` (Deactivation Notification, Reason: Normal / Host Request)

---

## 4. Teardown & Rollback Procedures

To guarantee that the NFC radio does not remain powered or cycling discovery after the trial:

1. **Software Carrier Stop:** Issue `RF_DEACTIVATE_CMD` to return controller to Idle state (`STATUS_OK`).
2. **Handle Closure:** Close open file descriptor to `/dev/nq-nci`.
3. **Module Unload:** Unload kernel drivers in sequence:
   ```bash
   modprobe -r oplus_nfc
   modprobe -r nfc_i2c
   ```
4. **Power Rail Depowering:** Verify regulator/GPIO state returns to off (`/sys/class/gpio` or DT regulators).
5. **Verification of Quiescence:** Confirm `/dev/nq-nci` node is removed or unreferenced, and system current returns to idle baseline.

---

## 5. Success Criteria for Future Attended Run

The attended trial will be marked **PASSED** if and only if all of the following conditions are met:
1. `CORE_RESET` and `CORE_INIT` complete with `STATUS_OK` (`0x00`).
2. `RF_DISCOVER_CMD` returns `STATUS_OK`.
3. Within 15 seconds of RF discovery activation, an `RF_INTF_ACTIVATED_NTF` packet is captured from `/dev/nq-nci`.
4. The captured notification contains a valid Type A UID ($\ge 4$ bytes) matching the physical test tag.
5. `RF_DEACTIVATE_CMD` cleanly shuts down the RF field with confirmation `RF_DEACTIVATE_RSP` (`STATUS_OK`).
6. Kernel modules unload cleanly without panic or kernel taint.
