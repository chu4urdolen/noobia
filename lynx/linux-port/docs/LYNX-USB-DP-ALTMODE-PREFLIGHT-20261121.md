# Lynx USB-C DisplayPort Alternate Mode & Redriver Preflight Architecture

**Author:** Banshee 💙 (Spirit of Initiative)  
**Date:** 2026-11-21  
**Target:** OnePlus Nord 3 5G (CPH2493, MediaTek MT6983 / Dimensity 9000)  
**Task Item:** B19 (Round 6)  
**Status:** Landed & Validated  

---

## 1. Executive Summary

This document establishes the hardware mapping, Device Tree topology, signal routing, and preflight validation gates for **USB Type-C DisplayPort Alternate Mode (DP Alt Mode)** and high-speed signal conditioning redrivers on the OnePlus Nord 3.

DisplayPort Alternate Mode over Type-C multiplexes high-speed DisplayPort audio/video differential lanes onto the physical USB Type-C high-speed pins (`TX1±`, `RX1±`, `TX2±`, `RX2±`). Because the MediaTek Dimensity 9000 shares these high-speed physical channels between USB 3.x SuperSpeed and the internal DisplayPort transmitter, external crossbar multiplexers and signal redrivers are essential to condition high-frequency transmission (up to 8.1 Gbps per lane in HBR3) and handle cable plug orientation.

---

## 2. Hardware Topology & Device Tree Mappings

Cross-referencing the device tree sources (`oplus6983_22823.dts` and `mt6983.dts`), the DisplayPort Alternate Mode subsystem comprises three tightly coupled hardware entities:

```
+-----------------------------------------------------------------------------------------+
|                               MediaTek MT6983 SoC                                       |
|                                                                                         |
|  +--------------------+         +----------------------------------------------------+  |
|  | DisplayPort        |         | USB 3.x SuperSpeed Host                            |  |
|  | Transmitter (DRM)  |         | (mtu3 / xhci)                                      |  |
|  +--------+-----------+         +-------------------------+--------------------------+  |
|           | DP Lanes                              SS Lanes|                             |
|           v                                               v                             |
|  +-----------------------------------------------------------------------------------+  |
|  | MMIO: usb_dp_selector@10005600 (mediatek,usb_dp_selector)                         |  |
|  +----------------------------------------+------------------------------------------+  |
+-------------------------------------------|---------------------------------------------+
                                            | High-Speed Differential Pairs
                                            v
+-----------------------------------------------------------------------------------------+
| Parade Technologies PS5170 Type-C Redriver & Crossbar MUX (&ps5170 @ I2C6 0x28)         |
| - Controls: pinctrl &ps_enable / &ps_disable (GPIO 204)                                 |
| - Conditioning: Equalization, Pre-emphasis, Slew Rate, Polarity Inversion               |
+-------------------------------------------+---------------------------------------------+
                                            |
                                            v
+-----------------------------------------------------------------------------------------+
| Type-C Receptacle & MT6375 Sub-PMIC TCPC Controller (&mt6375_typec / typec_mux_switch)  |
| - CC1 / CC2 VDM Alt Mode negotiation (SVID 0xff01)                                      |
| - Pin Assignment Negotiation (Pin C / Pin D)                                            |
| - Hot Plug Detect (HPD) Signal Forwarding: TCP_NOTIFY_AMA_DP_HPD_STATE                  |
+-----------------------------------------------------------------------------------------+
```

### 2.1 Parade Technologies PS5170 Type-C Redriver
- **Device Tree Node:** `&ps5170` on `&i2c6` at address `0x28` (dts alias `ps5170@30`, `reg = <0x28>`).
- **Compatible:** `"parade,ps5170"`.
- **Pinctrl States:** `&ps_enable` and `&ps_disable` defined on `&pio`.
- **Kernel Module:** `ps5170.ko`.
- **Role:** High-speed linear redriver and crossbar switch that restores high-frequency signal integrity across long cables and toggles between 4-lane DP, 2-lane DP + 2-lane USB 3.0, or pure USB 3.0.

### 2.2 MediaTek USB DP Selector
- **Device Tree Node:** `usb_dp_selector: usb_dp_selector@10005600`.
- **Compatible:** `"mediatek,usb_dp_selector"`.
- **Reg:** `<0 0x10005600 0 0x4>`, `reg-names = "usb_dp_reg"`.
- **Kernel Module:** `usb_dp_selector.ko`.
- **Role:** Internal SoC register multiplexer steering DP lanes from the display controller into the Type-C PHY.

### 2.3 MediaTek MT6375 TCPC & VDM Handler
- **Device Tree Node:** `&mt6375_typec` and `&typec_mux_switch`.
- **End-points:** Connected via `ssusb_mux` and `tcpc_typec_usb`.
- **Kernel Module:** `mux_switch.ko`.
- **Standard VDM SVID:** `0xff01` (VESA DisplayPort Standard).

---

## 3. DisplayPort Pin Assignments & Operating States

Under the VESA DisplayPort Alternate Mode on USB Type-C Standard:

| Pin Assignment | Differential Configuration | USB Bandwidth | Max Video Resolution | Use Case |
|---|---|---|---|---|
| **Pin Assignment C** | 4 DisplayPort Lanes (`L0`, `L1`, `L2`, `L3`) | USB 2.0 (D+/D- only) | 4K @ 60Hz / 120Hz, 8K @ 30Hz | Dedicated monitors, VR headsets, pure display adapters |
| **Pin Assignment D** | 2 DisplayPort Lanes (`L0`, `L1`) + 1 USB 3.x SuperSpeed RX/TX Pair | USB 3.2 Gen 1/2 (5–10 Gbps) | 4K @ 30Hz, 1440p @ 60Hz, 1080p @ 120Hz | Multi-port dongles, USB-C docks with Ethernet/storage |
| **Pin Assignment E** | 4 DisplayPort Lanes (direct DP pinout mapping) | None | 4K @ 60Hz | Direct DP-to-DP cables |

### Hot Plug Detect (HPD) Signalling
- `hpd = 0`: Sink disconnected; redriver enters low-power standby mode.
- `hpd = 1`: Sink attached; VDM negotiation complete; link training permitted.
- `hpd = irq`: Attention interrupt pulse received (used for HDCP handshakes or link retraining requests).

---

## 4. Preflight Implementation & Validation Suite

The preflight tool is packaged in `lynx/tools/usb_dp/lynx_usb_dp_preflight.py` accompanied by a comprehensive test suite in `test_lynx_usb_dp_preflight.py` and 3 hermetic fixtures:

1. `fixtures/usb-dp-baseline-disconnected.json`: Verifies baseline state where all controller nodes and modules are present, redriver is enabled, and Type-C port is idle without sink (`DP_STANDBY_DISCONNECTED`, Status `OK`).
2. `fixtures/usb-dp-altmode-connected.json`: Verifies active Alt Mode connection with SVID `0xff01`, Pin Assignment C, and high HPD (`DP_ALTMODE_ACTIVE`, Status `OK`).
3. `fixtures/usb-dp-mux-failure.json`: Verifies hardware fault detection when PS5170 redriver or port class interface fails to enumerate (`HARDWARE_FAULT`, Status `FAIL`).

### Safety Boundaries Enforced
- **Strictly Read-Only:** All evaluations inspect static Device Tree / sysfs data.
- **Double-Gated Live Mode:** Live inspection requires both `--live` and `--allow-live`.
- **Zero MUX Forcing:** The tool never issues ioctls or writes to sysfs mux switch attributes.
- **Zero Module Loads:** Live probes observe `lsmod` without loading or modifying kernel modules.

---

## 5. Test Evidence

```
test_altmode_connected_pin_c (test_lynx_usb_dp_preflight.TestLynxUsbDpPreflight) ... ok
test_altmode_pin_d_multifunction (test_lynx_usb_dp_preflight.TestLynxUsbDpPreflight) ... ok
test_ast_safety_and_no_writes (test_lynx_usb_dp_preflight.TestLynxUsbDpPreflight) ... ok
test_baseline_disconnected (test_lynx_usb_dp_preflight.TestLynxUsbDpPreflight) ... ok
test_boot_id_mismatch (test_lynx_usb_dp_preflight.TestLynxUsbDpPreflight) ... ok
test_cli_live_safety_gate (test_lynx_usb_dp_preflight.TestLynxUsbDpPreflight) ... ok
test_cli_validate_offline (test_lynx_usb_dp_preflight.TestLynxUsbDpPreflight) ... ok
test_invalid_pin_assignment (test_lynx_usb_dp_preflight.TestLynxUsbDpPreflight) ... ok
test_invalid_svid_when_altmode_active (test_lynx_usb_dp_preflight.TestLynxUsbDpPreflight) ... ok
test_mux_hardware_failure (test_lynx_usb_dp_preflight.TestLynxUsbDpPreflight) ... ok

----------------------------------------------------------------------
Ran 10 tests in 0.100s

OK
```
