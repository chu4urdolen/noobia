# Lynx Flashlight Core Gate (D22)

Offline preflight gate and hardware dependency map for the OnePlus Nord 3
flashlight core (`flashlight_core`), single-channel TI LM3642 flash LED
(`lm3642@63` on `&i2c6`), and flash NTC sensor (`cam_temp` on MT6373 ADC).

- `lynx_flashlight_gate.py` — spec audit + double-gated read-only live collector
- `fixtures/` — hermetic fixtures: torch-quiescent, unbound, missing-dt, torch-active
- `test_lynx_flashlight_gate.py` — hermetic unit tests

See `lynx/linux-port/docs/LYNX-FLASHLIGHT-CORE-PREFLIGHT-20261121.md` for the
full hardware map and safety boundary.
