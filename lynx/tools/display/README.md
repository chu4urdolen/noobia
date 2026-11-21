# Lynx Display & AMOLED Panel Preflight (D17)

Offline preflight gate and hardware dependency map for the OnePlus Nord 3
AMOLED display (Tianma NT37705 active panel, BOE NT37701A second-source).

- `lynx_display_preflight.py` — spec audit + double-gated read-only live collector
- `fixtures/` — hermetic fixtures: bound, unbound, missing-dt
- `test_lynx_display_preflight.py` — hermetic unit tests

See `lynx/linux-port/docs/LYNX-DISPLAY-PANEL-PREFLIGHT-20261121.md` for the
full hardware map and safety boundary.
