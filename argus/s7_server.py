#!/usr/bin/env python3
import os, sys, time, math, signal, argparse
import ctypes as ct
from struct import pack_into, unpack_from
import snap7
from snap7.server import Server

# ---------- args ----------
ap = argparse.ArgumentParser(description="Snap7 mini PLC sim (DB1+MK) for Argus")
ap.add_argument("--bind", default="10.10.10.1", help="IP to bind (default: 10.10.10.1)")
ap.add_argument("--db-size", type=int, default=256)
ap.add_argument("--mk-size", type=int, default=256)
ap.add_argument("--hz", type=float, default=2.0, help="sim heartbeat Hz (default: 2)")
ap.add_argument("--image", default="db1.bin", help="optional DB image file")
ap.add_argument("--autosnap", type=int, default=0, help="seconds; 0=off")
ap.add_argument("--temp-rate", type=int, default=5, help="INT units/tick (x10 degC); default 5 = 0.5°C/tick")
args = ap.parse_args()

# ---------- SrvArea constants (server side: MK=2, DB=3) ----------
def _srv_db_mk():
    try:
        from snap7.types import SrvArea;  return SrvArea.DB, SrvArea.MK
    except Exception:
        try:
            from snap7.snap7types import SrvArea;  return SrvArea.DB, SrvArea.MK
        except Exception:
            class _W: pass
            a=_W(); a.value=3  # DB
            b=_W(); b.value=2  # MK
            return a,b
SRV_DB, SRV_MK = _srv_db_mk()

DB_NUM  = 1
DB_SIZE = args.db_size
MK_SIZE = args.mk_size

db1 = ct.create_string_buffer(DB_SIZE)
mk  = ct.create_string_buffer(MK_SIZE)
db8 = (ct.c_ubyte * DB_SIZE).from_buffer(db1)  # byte-int views
mk8 = (ct.c_ubyte * MK_SIZE).from_buffer(mk)

# ---------- typed helpers ----------
def db_set_dint(o, v): pack_into(">I", db1, o, v & 0xFFFFFFFF)
def db_get_dint(o):    return unpack_from(">I", db1, o)[0]
def db_set_real(o, v): pack_into(">f", db1, o, float(v))
def db_get_real(o):    return unpack_from(">f", db1, o)[0]
def db_set_int(o, v):  pack_into(">h", db1, o, int(v))
def db_get_int(o):     return unpack_from(">h", db1, o)[0]
def db_set_bool(byte_o, bit_i, val):
    m = 1 << bit_i
    if val: db8[byte_o] |= m
    else:   db8[byte_o] &= (~m) & 0xFF
def db_get_bool(byte_o, bit_i): return (db8[byte_o] >> bit_i) & 1
def db_set_string20(o, s: str):
    s = (s or "")[:20].encode("latin1", "ignore")
    db8[o+0] = 20; db8[o+1] = len(s)
    db1[o+2:o+2+len(s)] = s
    db1[o+2+len(s):o+22] = b"\x00" * (20 - len(s))
def db_get_string20(o):
    end = o + 2 + min(db8[o+1], db8[o+0])
    return bytes(db1[o+2:end]).decode("latin1", "ignore")

# ---------- DB1 layout (freeze) ----------
OFF_TICK   = 0      # DINT
OFF_SINE   = 4      # REAL
OFF_TEMP   = 8      # INT (x10 °C)
OFF_ALRM_B = 10     # BOOL bit0
OFF_STR    = 12     # STRING[20]

# Operator-writable controls:
OFF_TEMP_SP = 40    # INT (x10 °C)   setpoint
OFF_THRESH  = 42    # INT (x10 °C)   alarm threshold
OFF_ACK_B   = 44    # BOOL bit0      alarm acknowledge (edge)
OFF_EN_B    = 45    # BOOL bit0      simulation enable

# ---------- init defaults ----------
db_set_dint(OFF_TICK, 0)
db_set_real(OFF_SINE, 0.0)
db_set_int (OFF_TEMP, 250)          # 25.0°C
db_set_bool(OFF_ALRM_B, 0, 0)
db_set_string20(OFF_STR, "Argus PLC sim")

db_set_int (OFF_TEMP_SP, 260)       # 26.0°C
db_set_int (OFF_THRESH,  300)       # 30.0°C
db_set_bool(OFF_ACK_B,   0, 0)
db_set_bool(OFF_EN_B,    0, 1)      # enabled by default

# restore image (overrides defaults)
if args.image and os.path.exists(args.image):
    with open(args.image, "rb") as f:
        blob = f.read()[:DB_SIZE]
        db1.raw[:len(blob)] = blob
        print(f"[load] restored DB1 from {args.image} ({len(blob)} bytes)")

# ---------- server ----------
srv = Server()
srv.register_area(SRV_DB, DB_NUM, db1)
srv.register_area(SRV_MK, 0, mk)
try: srv.start_to(args.bind)
except AttributeError: srv.start()
print(f"S7 server @{args.bind}:102 | DB{DB_NUM}={DB_SIZE} bytes, MK={MK_SIZE} bytes | {args.hz} Hz")

# ---------- external-write detector (only for operator fields) ----------
prev_db = bytes(db1.raw)
prev_mk = bytes(mk.raw)

# map of interesting fields for pretty logging
def _fmt_deg10(v): return f"{v/10:.1f}°C"
def _read_fields():
    return {
        "temp_sp":   db_get_int(OFF_TEMP_SP),
        "thresh":    db_get_int(OFF_THRESH),
        "ack":       db_get_bool(OFF_ACK_B, 0),
        "enable":    db_get_bool(OFF_EN_B, 0),
        "name":      db_get_string20(OFF_STR),
    }

interesting_windows = [
    (OFF_STR, OFF_STR+22, "name"),
    (OFF_TEMP_SP, OFF_TEMP_SP+2, "temp_sp"),
    (OFF_THRESH,  OFF_THRESH+2,  "thresh"),
    (OFF_ACK_B,   OFF_ACK_B+1,   "ack"),
    (OFF_EN_B,    OFF_EN_B+1,    "enable"),
]

last_fields = _read_fields()

def log_deltas():
    global prev_db, prev_mk, last_fields
    cur_db = bytes(db1.raw); cur_mk = bytes(mk.raw)

    if cur_db != prev_db:
        # find changed window
        i = next((k for k,(a,b) in enumerate(zip(prev_db,cur_db)) if a!=b), None)
        if i is not None:
            j = i
            while j<len(cur_db) and prev_db[j]!=cur_db[j] and j<i+32: j+=1

            # only report if it overlaps operator-writable windows
            hit = None
            for lo,hi,name in interesting_windows:
                if not (j <= lo or i >= hi):
                    hit = name; break
            if hit:
                fields = _read_fields()
                # pretty decode per field
                if hit == "name" and fields["name"] != last_fields["name"]:
                    print(f"[WRITE] name -> '{fields['name']}'")
                if hit == "temp_sp" and fields["temp_sp"] != last_fields["temp_sp"]:
                    print(f"[WRITE] temp_setpt -> {_fmt_deg10(fields['temp_sp'])}")
                if hit == "thresh" and fields["thresh"] != last_fields["thresh"]:
                    print(f"[WRITE] alarm_thresh -> {_fmt_deg10(fields['thresh'])}")
                if hit == "ack" and fields["ack"] != last_fields["ack"]:
                    print(f"[WRITE] alarm_ack -> {fields['ack']}")
                if hit == "enable" and fields["enable"] != last_fields["enable"]:
                    print(f"[WRITE] sim_enable -> {fields['enable']}")
                last_fields = fields
        prev_db = cur_db

    if cur_mk != prev_mk:
        # MK external logging optional; keep compact for now
        prev_mk = cur_mk

# ---------- graceful shutdown & snapshot ----------
running = True
def shutdown(*_):
    global running; running = False
def snapshot(*_):
    if not args.image:
        print("[snap] no --image file specified"); return
    with open(args.image, "wb") as f: f.write(db1.raw)
    print(f"[snap] DB1 dumped to {args.image} ({DB_SIZE} bytes)")
signal.signal(signal.SIGINT,  shutdown)
signal.signal(signal.SIGTERM, shutdown)
if hasattr(signal, "SIGUSR1"): signal.signal(signal.SIGUSR1, snapshot)

# ---------- simulator ----------
t0 = time.time()
tick = db_get_dint(OFF_TICK)
period = 1.0 / max(args.hz, 0.1)
last_snap = time.time()

while running:
    # heartbeat bit (MK[0].0)
    mk8[0] ^= 0x01

    # timebase + demo signals
    tick = (tick + 1) & 0xFFFFFFFF
    db_set_dint(OFF_TICK, tick)
    db_set_real(OFF_SINE, math.sin(time.time() - t0))

    # control logic (enabled?)
    sim_en = db_get_bool(OFF_EN_B, 0)
    cur = db_get_int(OFF_TEMP)          # x10
    sp  = db_get_int(OFF_TEMP_SP)
    th  = db_get_int(OFF_THRESH)
    ack = db_get_bool(OFF_ACK_B, 0)

    if sim_en:
        delta = sp - cur
        step = max(-args.temp_rate, min(args.temp_rate, delta))
        db_set_int(OFF_TEMP, cur + step)

    # alarm: latch on over-threshold; clear on ACK
    cur = db_get_int(OFF_TEMP)
    if cur >= th:
        db_set_bool(OFF_ALRM_B, 0, 1)
    if ack:
        db_set_bool(OFF_ALRM_B, 0, 0)
        db_set_bool(OFF_ACK_B,  0, 0)   # consume ACK edge

    # mirror alarm to MK[0].1
    al = db_get_bool(OFF_ALRM_B, 0)
    if al: mk8[0] |= 0x02
    else:  mk8[0] &= ~0x02 & 0xFF

    # external write logs (only operator fields)
    log_deltas()

    # autosnapshot
    if args.autosnap and (time.time() - last_snap) >= args.autosnap:
        snapshot(); last_snap = time.time()

    # live view
    print(f"MK0={{hb:{mk8[0]&1}, al:{(mk8[0]>>1)&1}}} | "
          f"tick={db_get_dint(OFF_TICK)} | sine={db_get_real(OFF_SINE):+.3f} | "
          f"temp={db_get_int(OFF_TEMP)/10:.1f}°C | "
          f"SP={db_get_int(OFF_TEMP_SP)/10:.1f}°C | TH={db_get_int(OFF_THRESH)/10:.1f}°C | "
          f"EN={db_get_bool(OFF_EN_B,0)} | AL={db_get_bool(OFF_ALRM_B,0)} | "
          f"str='{db_get_string20(OFF_STR)}'")
    time.sleep(period)

print("\nStopping server…")
try: srv.stop()
finally: srv.destroy()
print("Bye.")
