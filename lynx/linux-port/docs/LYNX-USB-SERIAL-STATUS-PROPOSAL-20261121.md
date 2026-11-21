# Lynx USB Serial Status Tool Proposal

**Tool Name:** `lynx_usb_serial_status`  
**Target Hardware:** OnePlus Nord 3 5G (`CPH2493` / platform `MT6983` / UDC `11201000.usb0`)  
**Host Controller:** Nexus host Linux environment  
**Author:** Banshee 💙 (Spirit of Initiative)  
**Date:** 2026-11-21  
**Status:** Catalog Proposal (Staged Outside `local_calls`)  

---

## 1. Executive Summary & Proposal Rationale

The Lynx device catalog currently provides `lynx_usb_status` (reporting high-level USB device-controller inventory via `lynx-platform-status usb`). However, an agent or operator diagnosing low-level USB gadget connectivity currently lacks a discrete, read-only companion tool to evaluate the **USB CDC ACM serial continuity**.

This proposal specifies `lynx_usb_serial_status`:
- **Read-Only / Safe:** Strictly passive; inspects sysfs, configfs, udev, and character devices without toggling UDCs, reloading kernel modules, or transmitting test traffic.
- **Dual-Endpoint Inspection:** Inspects both the phone-side virtual gadget (`/dev/ttyGS0`, `acm.usb0` in configfs, MTU3 device mode) and the host-side enumeration (`/dev/ttyACM*`, VID `1d6b`, PID `0104`, cdc_acm driver).
- **Staged Outside `local_calls`:** Adheres strictly to the architectural governance pattern established in B6 (`lynx_bluetooth_link_state`). All artifacts reside in `lynx/tools/usb/catalog_proposal/` until Aria authorizes formal catalog registration.

---

## 2. Catalog Manifest & Metadata

### 2.1 Tool Schema (`lynx_usb_serial_status.json`)
```json
{
  "name": "lynx_usb_serial_status",
  "description": "Entity: Lynx. Read USB CDC ACM serial link continuity, phone ttyGS0 endpoint, MTU3 gadget binding, and host /dev/ttyACM* enumeration without actuation.",
  "inputSchema": {
    "type": "object",
    "properties": {},
    "required": [],
    "additionalProperties": false
  },
  "timeout": 8
}
```

### 2.2 Host Wrapper (`lynx_usb_serial_status.sh`)
```sh
#!/bin/sh
# Entity: Lynx. Read-only USB CDC ACM serial status evaluation.
exec /usr/bin/python3 /usr/local/bin/lynx-usb-serial-status
```

### 2.3 Catalog Registration Entries
- **Manifest Entry (`manifest_entry.json`):**
  - Component: `usb`
  - Group: `hardware`
  - Effect: `read_only`
  - Status Source: `hardware`
  - Target Executable: `/usr/local/bin/lynx-usb-serial-status`
  - Timeout: 8 seconds.
- **Coverage Entry (`coverage_entry.json`):**
  - Tool Map Tuple: `["read_only", "hardware", ["hardware", "usb"], false]`
  - Coverage Role: `read_tool`
  - Target Component: `hardware/usb`

---

## 3. Hardware & Architectural Continuity Model

The tool evaluates four discrete states of the USB serial link:

| Link State | Phone Gadget (`ttyGS0` + MTU3) | Host Enumeration (`ttyACM*`) | Diagnostic Meaning |
|---|---|---|---|
| `CONTINUOUS_ACTIVE` | Active (mode 3, UDC bound) | Active (VID:PID 1d6b:0104) | Full physical and logical USB serial continuity established; ready for console or framed NRP telemetry. |
| `PHONE_ONLY_UNENUMERATED`| Active (mode 3, UDC bound) | Missing / Inactive | Gadget created on phone, but physical USB cable unplugged or host controller suspended. |
| `HOST_ONLY_STALE` | Inactive | Present | Stale udev node on host or phone crashed/rebooted without cleanly dropping connection. |
| `DISCONNECTED_SAFE` | Inactive | Inactive | Normal quiescent disconnected state; zero bus traffic. |

---

## 4. Safety & Governance Boundary

> [!IMPORTANT]
> **Strict Staging Requirement:**
> 1. `lynx_usb_serial_status.json` and `lynx_usb_serial_status.sh` must **NOT** be copied into `/noobia/lynx/tools/local_calls/` during this turn.
> 2. Installing the backend executable `/usr/local/bin/lynx-usb-serial-status` on the Nexus host or Lynx phone requires attended authorization from Aria.
> 3. Hermetic unit tests in `test_lynx_usb_proposal.py` explicitly verify that the files are absent from `local_calls`.

---

## 5. Verification & Test Suite

The test suite in `lynx/tools/usb/test_lynx_usb_proposal.py` verifies:
- Valid MCP JSON schema (timeout 8s, empty properties, no additional properties).
- Shell wrapper syntax and shebang.
- Manifest and coverage metadata alignment.
- Local calls boundary enforcement (asserts files do not exist in `local_calls/`).

Combined with existing USB tools (`test_lynx_usb_boot_persistence.py`, `test_lynx_usb_collector.py`, `test_lynx_usb_nrp_transport.py`), the USB test suite now consists of **39 passing tests**.
