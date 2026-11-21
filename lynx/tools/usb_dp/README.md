# Lynx USB-C DisplayPort Alternate Mode & Redriver Preflight Gate

Strict read-only preflight and topology evaluator for USB-C DisplayPort Alternate Mode and the Parade Technologies PS5170 Type-C redriver on the OnePlus Nord 3 (Dimensity 9000, MT6983).

## Hardware Components
- **Type-C Redriver:** Parade Technologies PS5170 on I2C6 @ 0x28 (`&ps5170`), controlled via pinctrl `&ps_enable` and `&ps_disable`.
- **USB DP Selector:** MediaTek MMIO selector @ 0x10005600 (`&usb_dp_selector`).
- **TCPC Port Manager:** MediaTek MT6375 sub-PMIC TCPC (`&mt6375_typec` / `typec_mux_switch`).
- **Standard VDM SVID:** `0xff01` (VESA DisplayPort Standard).

## Supported Modes & Pin Assignments
- **Pin Assignment C:** 4-lane DisplayPort (lanes 0..3 dedicated to DP sink, USB 2.0 D+/D- only).
- **Pin Assignment D:** Multi-function 2-lane DP + USB 3.x SuperSpeed.
- **Pin Assignment E:** 4-lane DisplayPort alternate pin configuration.

## Safety Boundaries
- **Strictly Offline by Default:** Use `--validate <FIXTURE>` to replay and test without target hardware.
- **Double-Gated Live Probes:** `--live --allow-live` required for read-only status interrogation over SSH.
- **Zero Register Writes:** Never forces mux modes, never actuates lane polarity or power switches, never initiates link training.

## Usage
```bash
# Offline verification against fixture
python3 lynx_usb_dp_preflight.py --validate fixtures/usb-dp-baseline-disconnected.json

# Offline verification with JSON output
python3 lynx_usb_dp_preflight.py --validate fixtures/usb-dp-altmode-connected.json --json

# Run unit tests
python3 -m unittest test_lynx_usb_dp_preflight.py
```
