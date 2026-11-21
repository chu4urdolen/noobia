# Lynx NFC NCI Frame Parser & Tag-Trial Receipt Decoder

**Device:** OnePlus Nord 3 5G (`CPH2493` / MediaTek `MT6983` / Project `22823`)  
**Subsystem:** NFC Controller Interface (`NCI 1.0` / `2.0`), NXP SN110T NFC/eSE Controller  
**Author:** Banshee 💙 (Spirit of Initiative)  
**Date:** 2026-11-21  
**Status:** Hermetic Decoder Specification & Offline Test Suite  

---

## 1. Executive Summary & Diagnostic Boundary

On the OnePlus Nord 3, the NXP SN110T NFC/eSE controller communicates with the host application processor over I2C (`/dev/nq-nci`, slave address `0x28` on `&i2c6`) using the NFC Forum **NFC Controller Interface (NCI)** specification.

A critical diagnostic distinction is maintained between driver probe and physical tag exchange:
- **Driver Probe Verification:** Confirms kernel module loading (`oplus_nfc`, `nfc_i2c`), character device creation (`/dev/nq-nci`), power rail sequencing, and basic I2C communication (e.g. `GET_VERSION` returning chip `0xA4`, ROM `0x01`, FW `0x10.68`).
- **Physical Tag Exchange Verification:** Requires activating the RF polling loop, generating the 13.56 MHz carrier field, performing anticollision cascade, capturing `RF_INTF_ACTIVATED_NTF`, extracting the tag's Unique Identifier (UID) and Select Acknowledge (SAK), and exchanging data frames.

To support safe, attended tag trials, this tool (`lynx/tools/nfc/lynx_nci_parser.py`) provides an offline, hermetic parser for NCI frames and multi-frame trial receipts.

---

## 2. NCI Protocol Frame Architecture

An NCI packet consists of a 3-byte header followed by a variable-length payload (0 to 255 bytes).

### 2.1 Packet Header Structure

```
Byte 0: [ MT (3 bits) | PBF (1 bit) | GID or ConnID (4 bits) ]
Byte 1: [ RFU (2 bits) | OID (6 bits) ]  (for Control Packets)
        [ RFU (8 bits) = 0x00 ]          (for Data Packets)
Byte 2: [ Payload Length (8 bits: 0..255) ]
Bytes 3..3+L-1: Payload
```

- **Message Types (`MT`, bits 7..5):**
  - `0x00` (`MT_DATA`): Data Packet
  - `0x01` (`MT_CMD`): Control Packet — Command (Host to NFCC)
  - `0x02` (`MT_RSP`): Control Packet — Response (NFCC to Host)
  - `0x03` (`MT_NTF`): Control Packet — Notification (NFCC to Host asynchronous event)
- **Packet Boundary Flag (`PBF`, bit 4):**
  - `0`: Complete message or last fragment of segmented message.
  - `1`: Incomplete message; subsequent fragments follow.
- **Group Identifier (`GID`, bits 3..0 for Control Packets):**
  - `0x00` (`GID_CORE`): Core configuration, reset, and initialization.
  - `0x01` (`GID_RF_MANAGE`): RF discovery, mode activation, and deactivation.
  - `0x02` (`GID_NFCEE_MANAGE`): Embedded Secure Element (eSE / UICC) management.
  - `0x0F` (`GID_PROPRIETARY`): NXP manufacturer-specific commands.
- **Connection Identifier (`ConnID`, bits 3..0 for Data Packets):**
  - Logical data connection identifier (e.g. `0x00` for static RF connection).

---

## 3. Supported NCI State Transitions & Decoded Opcodes

### 3.1 Core Reset (`CORE_RESET`) — GID 0x00, OID 0x00
- **`CORE_RESET_CMD` (`20 00 01 <ResetType>`):**
  - `ResetType = 0x01`: `KEEP_CONFIGURATION` (preserves RF tuning and trim registers).
- **`CORE_RESET_RSP` (`40 00 03 00 <NciVer> <ConfigStatus>`):**
  - Byte 0: `0x00` (`STATUS_OK`).
  - Byte 1: `0x10` (NCI 1.0) or `0x20` (NCI 2.0).
  - Byte 2: `0x01` (`CONFIG_KEPT`).

### 3.2 Core Initialization (`CORE_INIT`) — GID 0x00, OID 0x01
- **`CORE_INIT_CMD` (`20 01 00`):** Initiates NFCC feature negotiation.
- **`CORE_INIT_RSP` (`40 01 <Len> ...`):**
  - Returns NFCC features, max logical connections, routing table size, max payload sizes, supported RF interfaces (Frame RF, ISO-DEP, NFC-DEP), and manufacturer info.
  - **NXP SN110 Specifics:**
    - Manufacturer ID: `0x04` (NXP Semiconductors).
    - Chip Type: `0xA4` (SN110 series).
    - ROM Version: `0x01`.
    - Firmware Version: `0x10.68`.

### 3.3 RF Discovery Configuration (`RF_DISCOVER`) — GID 0x01, OID 0x03
- **`RF_DISCOVER_CMD` (`21 03 <Len> <NumConfigs> [TechMode, Freq]...`):**
  - `TechMode = 0x00`: `NFC_A_PASSIVE_POLL_MODE` (ISO/IEC 14443 Type A, 106 kbps).
  - `Frequency = 0x01`: Discovery every loop cycle.
- **`RF_DISCOVER_RSP` (`41 03 01 <Status>`):**
  - `Status = 0x00`: Polling loop active; transmitter RF carrier energized.

### 3.4 RF Interface Activation (`RF_INTF_ACTIVATED`) — GID 0x01, OID 0x05
Asynchronous notification generated when a physical tag modulates the RF carrier and completes anticollision cascade:
- **`RF_INTF_ACTIVATED_NTF` (`61 05 <Len> ...`):**
  - Byte 0: Discovery ID.
  - Byte 1: RF Interface (`0x01` Frame RF, `0x02` ISO-DEP).
  - Byte 2: RF Protocol (`0x02` Type 2 Tag / NTAG, `0x04` ISO-DEP / Type 4, `0x80` MIFARE Classic).
  - Byte 3: Activation Technology & Mode (`0x00` NFC-A Poll).
  - Tech Specific Parameters:
    - **`SENS_RES` / `ATQA`:** 2 bytes (e.g. `0x0044` for NTAG215; `0x0004` for MIFARE Classic).
    - **`NFCID1` / `UID Length`:** 4, 7, or 10 bytes.
    - **`NFCID1` / `UID Bytes`:** Hex string representation (e.g. `04:A1:B2:C3:D4:E5:F6`).
    - **`SEL_RES` / `SAK`:** 1 byte (e.g. `0x00` for T2T NTAG; `0x08` for MIFARE Classic 1K; `0x20` for ISO-DEP).

### 3.5 Data Exchange (`DATA`) — MT 0x00
- **`DATA_CMD` (`00 00 <Len> <Payload>`):**
  - Sends NFC Forum memory commands (e.g. `30 04` to read block 4 on Type 2 Tags).
- **`DATA_RSP` (`00 00 <Len> <Payload>`):**
  - Returns 16 bytes of tag memory containing NDEF record headers.

### 3.6 RF Deactivation (`RF_DEACTIVATE`) — GID 0x01, OID 0x06
- **`RF_DEACTIVATE_CMD` (`21 06 01 <DeactType>`):**
  - `DeactType = 0x00`: Deactivate to `IDLE_MODE` (shuts down RF carrier, de-energizes transmitter).
- **`RF_DEACTIVATE_RSP` (`41 06 01 <Status>`):**
  - `Status = 0x00`: Clean RF shutdown verified.

---

## 4. Test Fixtures & Offline Verification

Four hermetic test fixtures validate all operational modes:

| Fixture | Scenario | Expected Verdict | Key Findings |
|---|---|---|---|
| `nci-tag-trial-ntag215-receipt.json` | Successful NTAG215 tag read | `TAG_EXCHANGE_VERIFIED` | 7-byte UID `04:A1:B2:C3:D4:E5:F6`, T2T protocol, NXP SN110T identified, 2 data packets exchanged, clean deactivation. |
| `nci-tag-trial-mifare-classic-receipt.json` | Successful MIFARE Classic 1K read | `TAG_EXCHANGE_VERIFIED` | 4-byte UID `12:34:56:78`, SAK `0x08`, ATQA `0x0004`. |
| `nci-tag-trial-timeout-no-tag-receipt.json` | 15-second watchdog timer expiration | `DISCOVERY_ACTIVE_NO_TAG` | RF discovery configured, no tag presented, clean deactivation to idle without hangs. |
| `nci-corrupted-frame-receipt.json` | Truncated/corrupted packets | `PARSING_FAILED` | Frame length mismatches reported cleanly in errors array. |

---

## 5. Test Suite Execution

The complete test suite runs hermetically in < 2ms:
```bash
python3 -m unittest discover -s /noobia/lynx/tools/nfc
# Ran 18 tests in 0.001s - OK
```
Zero phone rootfs writes, zero radio actuation. All tag parsing logic is pure offline python.
