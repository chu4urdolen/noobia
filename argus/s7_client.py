#!/usr/bin/env python3
import time, snap7

IP = "10.10.10.1"

# --- Get a proper Enum for Area; if missing, patch the client module ---
try:
    from snap7.types import Area as _AreaEnum  # preferred
except Exception:
    try:
        from snap7.snap7types import Area as _AreaEnum  # alt
    except Exception:
        # Last resort: patch snap7.client.Area so membership checks pass
        import snap7.client as _c
        from enum import IntEnum
        class _AreaEnum(IntEnum):
            PE = 0x81  # process inputs
            PA = 0x82  # process outputs
            MK = 0x83  # merkers
            DB = 0x84  # data blocks
            CT = 0x1C  # counters
            TM = 0x1D  # timers
        _c.Area = _AreaEnum  # monkey-patch the module enum

AREA_MK = _AreaEnum.MK  # real enum member now

cli = snap7.client.Client()

# connect (rack/slot don't matter to snap7 server)
for rack, slot in [(0,0),(0,1),(0,2)]:
    try:
        cli.connect(IP, rack, slot)
        if cli.get_connected():
            print(f"Connected to {IP} rack={rack} slot={slot}")
            break
    except Exception as e:
        print(f"Connect {rack}/{slot} failed: {e}")
else:
    raise SystemExit("Could not connect to server")

# --- Write & read MK (index=0, start=0) ---
payload = bytes(range(1, 17))
cli.write_area(AREA_MK, 0, 0, payload)
print("MK write_area OK")

rb = cli.read_area(AREA_MK, 0, 0, 16)
print("MK read_area ->", list(rb))

for i in range(3):
    blob = bytes([(i*55) & 0xFF] * 16)
    cli.write_area(AREA_MK, 0, 0, blob)
    time.sleep(10.0)
    rb = cli.read_area(AREA_MK, 0, 0, 16)
    print(f"Cycle {i}: MK[0:16] =", list(rb))

cli.disconnect()
print("Done.")
