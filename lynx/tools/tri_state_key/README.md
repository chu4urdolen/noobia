# OnePlus Alert Slider (Tri-State Key) Preflight Gate

Offline preflight validator and hardware topology auditor for the OnePlus Nord 3 (`oplus6983_22823`) contact-less magnetic Alert Slider.

## Overview

The Alert Slider operates via two high-sensitivity digital Hall effect ICs (MagnaChip MXM1120 or Isentek IST8801) on `i2c0` (`0x11e00000`).
- Down-Hall: I2C `0x0C` (or `0x18`), IRQ GPIO 5, pinctrl `downhall_tri_state_key_active`
- Up-Hall: I2C `0x0D` (or `0x19`), IRQ GPIO 4, pinctrl `uphall_tri_state_key_active`
- Power: VIO18 (1.8V), VIO28 (2.8V)

## Usage

```bash
# Validate offline fixture
python3 lynx_tri_state_key_preflight.py --validate fixtures/tri-state-key-preflight-silent.json

# Live read-only interrogation (requires double-gate)
python3 lynx_tri_state_key_preflight.py --live --allow-live
```
