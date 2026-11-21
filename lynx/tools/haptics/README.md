# Lynx Haptics (LRA) Preflight (D21)

Offline preflight gate and hardware dependency map for the OnePlus Nord 3
linear resonant actuator (vibrator node under `&odm`).

- `lynx_haptics_preflight.py` — spec audit + double-gated read-only live collector
- `fixtures/` — hermetic fixtures: bound, unbound, missing-dt, active-pulse
- `test_lynx_haptics_preflight.py` — hermetic unit tests

See `lynx/linux-port/docs/LYNX-HAPTICS-LRA-PREFLIGHT-20261121.md` for the
full hardware map and safety boundary.
