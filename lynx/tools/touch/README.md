# Lynx Touchscreen Controller Preflight (D18)

Offline preflight gate and hardware dependency map for the OnePlus Nord 3
Synaptics S3908 touch controller on I2C-0.

- `lynx_touch_preflight.py` — spec audit + double-gated read-only live collector
- `fixtures/` — hermetic fixtures: bound, unbound, missing-dt
- `test_lynx_touch_preflight.py` — hermetic unit tests

See `lynx/linux-port/docs/LYNX-TOUCHSCREEN-PREFLIGHT-20261121.md` for the
full hardware map and safety boundary.
