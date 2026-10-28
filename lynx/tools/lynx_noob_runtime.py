#!/usr/bin/env python3
"""Linux NRP/1 runtime for Lynx: ESP common VM, sequences, threads, native calls."""

import argparse
from collections import deque
import fcntl
import json
import os
from pathlib import Path
import re
import selectors
import signal
import socket
import struct
import subprocess
import time

VERSION = "NRP/1"
PHONE_IP = "192.168.100.107"
NEXUS_IP = "192.168.100.106"
NAME = re.compile(r"[a-z0-9_]{1,63}\Z")
LED = Path("/sys/class/leds/vibrator")
DISPLAY = Path("/var/lib/lynx-display")
MEDIA = Path("/run/lynx/media.sock")
GAUGE = Path("/sys/bus/i2c/devices/7-0055/battery_snapshot")
THERMAL = Path("/sys/class/thermal")
SOUND_CARDS = Path("/proc/asound/cards")
TFA_FIRMWARE = Path("/sys/module/snd_soc_tfa98xx/parameters/fw_name")
TOUCH_DEVICE = "/dev/input/event0"
HF_MANAGER = Path("/dev/hf_manager")
HF_SAMPLE = Path("/usr/local/bin/lynx-hf-sample")
_haptic_ready_at = 0.0


class NativeError(ValueError):
    pass


def i32(value):
    value &= 0xffffffff
    return value - 0x100000000 if value & 0x80000000 else value


def media(action, kind, item=None):
    request = {"action": action, "kind": kind, "item": item}
    with socket.socket(socket.AF_UNIX) as conn:
        conn.settimeout(2)
        conn.connect(str(MEDIA))
        conn.sendall(json.dumps(request).encode())
        result = json.loads(conn.recv(4096))
    if not result.get("ok"):
        raise NativeError(result.get("error", "media failed"))
    return result


def image_names():
    manifest = json.loads((DISPLAY / "frames/manifest.json").read_text())
    return sorted(entry["name"] for entry in manifest["frames"])


def native_image(name, animation=False):
    if not NAME.fullmatch(name):
        raise NativeError("invalid image name")
    manifest = json.loads((DISPLAY / "frames/manifest.json").read_text())
    available = (manifest["animations"] if animation else
                 {entry["name"] for entry in manifest["frames"]})
    if name not in available:
        raise NativeError("unknown animation" if animation else "unknown pose")
    # The media service owns the portrait selection and handles atomic updates.
    media("play", "image", name)
    return 1, f"name={name}"


def haptic_stop():
    if LED.joinpath("oplus_activate").exists():
        LED.joinpath("oplus_activate").write_text("0\n")


def haptic_set(numbers, _text):
    global _haptic_ready_at
    if len(numbers) != 2 or numbers[1] not in (0, 1):
        raise NativeError("usage: duration_ms(20..250) bit(0|1)")
    duration, bit = numbers
    if not LED.is_dir() or "haptic " not in Path("/proc/modules").read_text():
        raise NativeError("haptic driver unavailable")
    if bit == 0:
        haptic_stop()
        return 0, "motor=off"
    if not 20 <= duration <= 250:
        raise NativeError("duration must be 20..250 ms")
    now = time.monotonic()
    if now < _haptic_ready_at:
        raise NativeError("haptic cooldown")
    LED.joinpath("oplus_duration").write_text(f"{duration}\n")
    LED.joinpath("oplus_activate").write_text("1\n")
    _haptic_ready_at = now + (duration + 50) / 1000
    return 1, f"duration_ms={duration}"


def no_args(numbers, text):
    if numbers or text:
        raise NativeError("usage: no arguments")


def gauge_reading(field, error, low, high):
    try:
        fields = dict(line.split("=", 1) for line in GAUGE.read_text().splitlines()
                      if "=" in line)
        if int(fields["gauge_device_type"]) != 42495 or int(fields[error + "_error"]) != 0:
            raise NativeError("battery gauge read failed")
        value = int(fields[field])
    except (OSError, KeyError, ValueError) as exc:
        raise NativeError("battery gauge unavailable") from exc
    if not low <= value <= high:
        raise NativeError("battery reading out of range")
    return value


def battery_percent(numbers, text):
    no_args(numbers, text)
    return gauge_reading("capacity_percent", "capacity", 0, 100), "unit=percent"


def battery_temp(numbers, text):
    no_args(numbers, text)
    return gauge_reading("temperature_millidegrees_celsius", "temperature", -20000, 80000), "unit=mC"


def battery_current(numbers, text):
    no_args(numbers, text)
    return gauge_reading("gauge_current_ma_signed", "current", -10000, 10000), "unit=mA_signed"


def battery_voltage(numbers, text):
    no_args(numbers, text)
    return gauge_reading("pack_voltage_mv", "voltage", 5000, 10000), "unit=mV"


def soc_temp(numbers, text):
    no_args(numbers, text)
    try:
        readings = [int((zone / "temp").read_text()) for zone in THERMAL.glob("thermal_zone*")
                    if (zone / "type").read_text().strip() == "soc_max"]
    except (OSError, ValueError) as exc:
        raise NativeError("SoC thermal reading unavailable") from exc
    if len(readings) != 1 or not -20000 <= readings[0] <= 120000:
        raise NativeError("SoC thermal reading invalid")
    return readings[0], "unit=mC"


def audio_ready(numbers, text):
    no_args(numbers, text)
    try:
        cards = SOUND_CARDS.read_text()
        firmware = TFA_FIRMWARE.read_text().strip()
    except OSError:
        return 0, "card=0 firmware=0"
    card = "mt6983mt6338" in cards
    if not card or firmware != "tfa98xx.cnt":
        return 0, f"card={int(card)} firmware=0"
    try:
        result = subprocess.run(["amixer", "-c0", "cget", "name=TFA98XX Firmware"],
                                capture_output=True, text=True, timeout=2, check=False)
        loaded = result.returncode == 0 and ": values=1" in result.stdout
    except (OSError, subprocess.TimeoutExpired):
        loaded = False
    return int(loaded), f"card=1 firmware={int(loaded)}"


class RecordQueue:
    def __init__(self):
        self.items = deque(maxlen=8)
        self.dropped = 0
        self.last = None

    def push(self, record):
        if len(self.items) == 8:
            self.dropped += 1
        self.items.append(record)

    def pop(self, empty_ok=False):
        if not self.items:
            if empty_ok:
                return 0, "event=0 queued=0"
            raise NativeError("channel queue empty")
        self.last = self.items.popleft()
        key = next(iter(self.last))
        value = self.last[key]
        return value, f"event=1 remaining={len(self.items)} dropped={self.dropped} record={self.serialize(self.last)}"

    @staticmethod
    def serialize(record):
        return ",".join(f"{k}:{v}" for k, v in record.items())


class TouchInput:
    """Read one verified Synaptics contact without grabbing the display's fd."""

    EVENT = struct.Struct("llHHi")
    NAME_IOCTL = (2 << 30) | (64 << 16) | (ord("E") << 8) | 0x06
    ABS_IOCTL = staticmethod(lambda code: (2 << 30) | (24 << 16) | (ord("E") << 8) | (0x40 + code))

    def __init__(self):
        self.fd = None
        self.retry_at = 0.0
        self.pending = b""
        self.slot = 0
        self.down = False
        self.x = None
        self.y = None
        self.changed = False
        self.was_down = False
        self.events = RecordQueue()

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        self.pending = b""
        self.retry_at = time.monotonic() + 1

    def open_verified(self):
        if self.fd is not None or time.monotonic() < self.retry_at:
            return
        try:
            fd = os.open(TOUCH_DEVICE, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
            name = bytearray(64)
            fcntl.ioctl(fd, self.NAME_IOCTL, name, True)
            if name.split(b"\0", 1)[0] != b"touchpanel":
                os.close(fd)
                self.retry_at = time.monotonic() + 1
                return
            for code, expected in ((53, 12399), (54, 27719)):
                axis = bytearray(24)
                fcntl.ioctl(fd, self.ABS_IOCTL(code), axis, True)
                _, low, high, _, _, _ = struct.unpack("6i", axis)
                if (low, high) != (0, expected):
                    os.close(fd)
                    self.retry_at = time.monotonic() + 1
                    return
            self.fd = fd
        except OSError:
            if 'fd' in locals():
                os.close(fd)
            self.retry_at = time.monotonic() + 1

    def feed(self, typ, code, value):
        if typ == 3:  # EV_ABS
            if code == 47:  # ABS_MT_SLOT
                self.slot = value
            elif self.slot == 0:
                if code == 57:  # ABS_MT_TRACKING_ID
                    self.down = value >= 0
                    self.changed = True
                elif code == 53:  # ABS_MT_POSITION_X
                    self.x = value
                    self.changed = True
                elif code == 54:  # ABS_MT_POSITION_Y
                    self.y = value
                    self.changed = True
        elif typ == 0 and code == 0 and self.changed:  # SYN_REPORT
            if self.x is not None and self.y is not None:
                phase = 1 if self.down and not self.was_down else (2 if self.down else 0)
                if 0 <= self.x <= 12399 and 0 <= self.y <= 27719:
                    self.events.push({"phase": phase, "x": self.x, "y": self.y,
                                      "px": self.x // 10, "py": self.y // 10})
            self.was_down = self.down
            self.changed = False

    def tick(self):
        self.open_verified()
        if self.fd is None:
            return
        try:
            for _ in range(4):
                chunk = os.read(self.fd, self.EVENT.size * 64)
                if not chunk:
                    break
                self.pending += chunk
                count = len(self.pending) // self.EVENT.size
                for offset in range(0, count * self.EVENT.size, self.EVENT.size):
                    _, _, typ, code, value = self.EVENT.unpack_from(self.pending, offset)
                    self.feed(typ, code, value)
                self.pending = self.pending[count * self.EVENT.size:]
        except BlockingIOError:
            pass
        except OSError:
            self.close()


class NoobThreadProgram:
    def __init__(self, interval_ms):
        self.interval_ms = interval_ms
        self.running = False
        self.next_at = 0.0
        self.events = RecordQueue()
        self.busy = False

    def start(self, interval_ms=None):
        if interval_ms is not None:
            if not 100 <= interval_ms <= 60000:
                raise NativeError("interval must be 100..60000 ms")
            self.interval_ms = interval_ms
        self.events = RecordQueue()
        self.running = True
        self.busy = True
        self.next_at = time.monotonic()
        return 1, self.status()[1]

    def stop(self):
        self.running = False
        self.busy = False
        return 0, self.status()[1]

    def status(self):
        return int(self.running), (f"type=thread running={int(self.running)} "
                                   f"interval_ms={self.interval_ms} channel_busy={int(self.busy)} "
                                   f"queued={len(self.events.items)} dropped={self.events.dropped}")

    def tick(self):
        if not self.running or time.monotonic() < self.next_at:
            return
        self.next_at = time.monotonic() + self.interval_ms / 1000
        self.step()

    def step(self):
        raise NotImplementedError


class ImageCycleThread(NoobThreadProgram):
    def __init__(self):
        super().__init__(500)
        self.index = 0

    def step(self):
        poses = ["01_standing_smile", "02_talking"]
        media("play", "image", poses[self.index])
        self.events.push({"value": self.index, "time_ms": int(time.monotonic() * 1000) & 0x7fffffff})
        self.index ^= 1


class Sequence:
    def __init__(self, registry):
        self.registry = registry
        self.tracks = [None] * 4
        self.queues = [RecordQueue() for _ in range(4)]
        self.running = False
        self.repeat = False
        self.events = deque(maxlen=16)

    def set(self, args, text="", mixed=False):
        if self.running:
            raise NativeError("stop sequence before editing")
        if mixed:
            if len(args) < 6 or args[5] not in (0, 1):
                raise NativeError("usage: slot interval function count bits append_bit [args] ASCII")
            append = bool(args[5])
            args = args[:5] + args[6:]
        else:
            append = True
        if not 5 <= len(args) <= 12:
            raise NativeError("usage: slot interval function count bits [args]")
        slot, interval, function, count, packed, *fixed = args
        if not 0 <= slot < 4 or not 1 <= interval <= 60000 or not 1 <= count <= 32:
            raise NativeError("invalid sequence slot, interval or bit count")
        if not 0 <= function <= 65535 or function not in self.registry.by_id:
            raise NativeError("unknown sequence function")
        bits = [((packed & 0xffffffff) >> (count - n - 1)) & 1 for n in range(count)]
        self.tracks[slot] = dict(interval=interval, function=function, bits=bits,
                                 fixed=fixed, text=text, append=append,
                                 position=0, next_at=0.0, active=False)
        return slot, f"slot={slot} interval_ms={interval} function={function} bits={''.join(map(str,bits))}"

    def set_text(self, raw):
        if self.running:
            raise NativeError("stop sequence before editing")
        fields = raw.split()
        if not 4 <= len(fields) <= 11:
            raise NativeError("usage: slot interval function bits [args]")
        try:
            slot, interval = int(fields[0]), int(fields[1])
            function = self.registry.resolve(fields[2])
            fixed = [int(x) for x in fields[4:]]
        except ValueError as exc:
            raise NativeError("invalid sequence arguments") from exc
        bits = fields[3]
        if not 0 <= slot < 4 or not 1 <= interval <= 60000 or not 1 <= len(bits) <= 64 or set(bits) - {"0", "1"}:
            raise NativeError("invalid sequence definition")
        self.tracks[slot] = dict(interval=interval, function=function,
                                 bits=[int(x) for x in bits], fixed=fixed,
                                 text="", append=True, position=0,
                                 next_at=0.0, active=False)
        return slot, f"slot={slot} interval_ms={interval} function={function} bits={bits}"

    def start(self, args):
        if len(args) > 1 or (args and args[0] not in (0, 1)):
            raise NativeError("usage: [repeat(0|1)]")
        if self.running or not any(self.tracks):
            raise NativeError("sequence running or unconfigured")
        self.repeat = bool(args[0]) if args else False
        now = time.monotonic()
        for track in self.tracks:
            if track:
                track.update(position=0, next_at=now, active=True)
        self.running = True
        return sum(bool(t) for t in self.tracks), self.status()[1]

    def stop(self):
        self.running = False
        for track in self.tracks:
            if track:
                track["active"] = False
        haptic_stop()
        return 0, self.status()[1]

    def status(self):
        active = sum(bool(t and t["active"]) for t in self.tracks)
        busy = ",".join(str(int(bool(t and t["active"]))) for t in self.tracks)
        positions = ",".join(f"{t['position']}/{len(t['bits'])}" if t else "-" for t in self.tracks)
        return int(self.running), (f"running={int(self.running)} repeat={int(self.repeat)} "
                                   f"configured={sum(bool(t) for t in self.tracks)} active={active} "
                                   f"channel_busy={busy} positions={positions}")

    def tick(self):
        if not self.running:
            return
        now = time.monotonic()
        for slot, track in enumerate(self.tracks):
            if not track or not track["active"] or now < track["next_at"]:
                continue
            bit = track["bits"][track["position"]]
            args = track["fixed"] + ([bit] if track["append"] else [])
            try:
                value, _ = self.registry.call(track["function"], args, track["text"])
                self.queues[slot].push({"value": value, "time_ms": int(now * 1000) & 0x7fffffff})
            except Exception as exc:
                self.stop()
                self.events.append(f"SEQUENCE_ERROR slot={slot} detail={str(exc).replace(' ', '_')}")
                return
            track["position"] += 1
            if track["position"] >= len(track["bits"]):
                if self.repeat:
                    track["position"] = 0
                else:
                    track["active"] = False
            track["next_at"] = now + track["interval"] / 1000
        if not any(t and t["active"] for t in self.tracks):
            self.running = False
            self.events.append("SEQUENCE_COMPLETE")


class Registry:
    def __init__(self):
        self.by_id = {}
        self.by_name = {}
        self.mixed_by_id = {}

    def add(self, ident, name, callback, mixed_callback=None):
        if ident in self.by_id or name in self.by_name:
            raise ValueError("duplicate native")
        self.by_id[ident] = (name, callback)
        self.by_name[name] = ident
        if mixed_callback:
            self.mixed_by_id[ident] = mixed_callback

    def resolve(self, selector):
        ident = int(selector) if str(selector).isdigit() else self.by_name.get(selector)
        if ident not in self.by_id:
            raise NativeError(f"no function {selector}")
        return ident

    def call(self, selector, numbers, text="", mixed=False):
        ident = self.resolve(selector)
        if len(numbers) > 8 or len(text) > 255 or not text.isascii() or any(ord(c) < 32 for c in text):
            raise NativeError("argument exceeds common ABI")
        callback = self.mixed_by_id.get(ident) if mixed else None
        return (callback or self.by_id[ident][1])(numbers, text)


class Vm:
    def __init__(self, registry):
        self.registry = registry
        self.reset()

    def reset(self):
        self.code = b""
        self.memory = bytearray(256)
        self.reg = [0] * 8
        self.stack = []
        self.pc = 0
        self.state = "EMPTY"
        self.fault = ""
        self.wake = 0.0

    def load(self, code):
        if self.state in ("RUNNING", "WAITING"):
            raise NativeError("stop VM before replacing program")
        if not 1 <= len(code) <= 1024:
            raise NativeError("program size must be 1..1024 bytes")
        self.reset()
        self.code = code
        self.state = "READY"

    def run(self):
        if not self.code or self.state in ("RUNNING", "WAITING"):
            raise NativeError("no program or already running")
        self.pc = 0
        self.stack = []
        self.state = "RUNNING"

    def stop(self):
        if self.state in ("RUNNING", "WAITING"):
            self.state = "STOPPED"

    def status(self):
        suffix = f" fault={self.fault}" if self.fault else ""
        return f"state={self.state} pc={self.pc} bytes={len(self.code)} regs={','.join(map(str,self.reg))}{suffix}"

    def take(self, count):
        if self.pc + count > len(self.code):
            raise NativeError("truncated instruction")
        data = self.code[self.pc:self.pc + count]
        self.pc += count
        return data

    def regid(self, value):
        if value >= 8:
            raise NativeError("invalid register")
        return value

    def jump(self, target):
        if target >= len(self.code):
            raise NativeError("jump outside program")
        self.pc = target

    def tick(self):
        if self.state == "WAITING":
            if time.monotonic() < self.wake:
                return
            self.state = "RUNNING"
        for _ in range(32):
            if self.state != "RUNNING":
                return
            try:
                self.one()
            except Exception as exc:
                self.fault = str(exc).replace(" ", "_")[:120]
                self.state = "FAULT"
                return

    def one(self):
        op = self.take(1)[0]
        if op == 0:
            self.state = "HALTED"
        elif op == 1:
            d = self.regid(self.take(1)[0])
            self.reg[d] = struct.unpack("<i", self.take(4))[0]
        elif op == 2:
            d, s = self.take(2)
            self.reg[self.regid(d)] = self.reg[self.regid(s)]
        elif 3 <= op <= 6:
            d, a, b = (self.regid(x) for x in self.take(3))
            if op == 3:
                v = self.reg[a] + self.reg[b]
            elif op == 4:
                v = self.reg[a] - self.reg[b]
            elif op == 5:
                v = self.reg[a] * self.reg[b]
            else:
                if self.reg[b] == 0:
                    raise NativeError("division by zero")
                v = int(self.reg[a] / self.reg[b])
            self.reg[d] = i32(v)
        elif op == 0x10:
            self.jump(struct.unpack("<H", self.take(2))[0])
        elif op in (0x11, 0x12):
            r = self.regid(self.take(1)[0])
            target = struct.unpack("<H", self.take(2))[0]
            if (self.reg[r] == 0) == (op == 0x11):
                self.jump(target)
        elif op == 0x13:
            target = struct.unpack("<H", self.take(2))[0]
            if len(self.stack) == 8:
                raise NativeError("invalid call")
            ret = self.pc
            self.jump(target)
            self.stack.append(ret)
        elif op == 0x14:
            if not self.stack:
                raise NativeError("return stack empty")
            self.pc = self.stack.pop()
        elif op in (0x20, 0x22):
            d = self.regid(self.take(1)[0])
            ident = struct.unpack("<H", self.take(2))[0]
            count = self.take(1)[0]
            if count > 8:
                raise NativeError("too many syscall arguments")
            args = [self.reg[self.regid(x)] for x in self.take(count)]
            text = ""
            if op == 0x22:
                text = self.take(self.take(1)[0]).decode("ascii")
            value, _ = self.registry.call(ident, args, text, mixed=op == 0x22)
            self.reg[d] = i32(value)
        elif op == 0x21:
            delay = struct.unpack("<H", self.take(2))[0]
            self.wake = time.monotonic() + delay / 1000
            self.state = "WAITING"
        elif op == 0x30:
            d, addr = self.take(2)
            self.reg[self.regid(d)] = self.memory[addr]
        elif op == 0x31:
            addr, s = self.take(2)
            self.memory[addr] = self.reg[self.regid(s)] & 255
        else:
            raise NativeError(f"unknown opcode {op}")


class Runtime:
    def __init__(self):
        self.registry = Registry()
        self.sequence = Sequence(self.registry)
        self.cycle = ImageCycleThread()
        self.vm = Vm(self.registry)
        self.epoch = time.monotonic()
        self.accel_cache = None
        self.gyro_cache = None
        self.mag_cache = None
        self.optical_cache = {}
        self.touch = TouchInput()
        self.register()

    def register(self):
        reg = self.registry.add
        reg(1, "TIME_NOW", lambda a, t: (i32(int((time.monotonic()-self.epoch)*1000)), "monotonic_ms"))
        reg(2, "TIME_RESET", self.time_reset)
        reg(3, "SEQUENCE_SET", lambda a, t: self.sequence.set(a, t),
            lambda a, t: self.sequence.set(a, t, True))
        reg(4, "SEQUENCE_START", lambda a, t: self.sequence.start(a))
        reg(5, "SEQUENCE_STOP", lambda a, t: self.sequence.stop())
        reg(6, "SEQUENCE_STATUS", lambda a, t: self.sequence.status())
        reg(7, "SEQUENCE_CLEAR", self.seq_clear)
        reg(8, "SEQUENCE_POP", lambda a, t: self.sequence.queues[self.slot(a)].pop())
        reg(9, "SEQUENCE_QUEUE_SIZE", lambda a, t: (len(self.sequence.queues[self.slot(a)].items), f"dropped={self.sequence.queues[self.slot(a)].dropped}"))
        reg(10, "SEQUENCE_QUEUE_CLEAR", self.seq_queue_clear)
        reg(11, "SEQUENCE_BUSY", lambda a, t: (int(bool(self.sequence.tracks[self.slot(a)] and self.sequence.tracks[self.slot(a)]["active"])), ""))
        reg(12, "SEQUENCE_FIELD", self.seq_field)
        reg(300, "HAPTIC_SET", haptic_set)
        reg(301, "HAPTIC_STATUS", self.haptic_status)
        reg(302, "HAPTIC_STOP", self.haptic_stop_call)
        reg(310, "IMAGE_SELECT", self.image_select)
        reg(311, "IMAGE_CHOOSE", self.image_choose)
        reg(312, "IMAGE_POSE", self.image_pose)
        reg(313, "IMAGE_ANIMATE", self.image_animate)
        reg(314, "IMAGE_QUEUE", self.image_queue)
        reg(315, "IMAGE_PAUSE", lambda a, t: self.media_transport(a, t, "pause", "image"))
        reg(316, "IMAGE_RESUME", lambda a, t: self.media_transport(a, t, "resume", "image"))
        reg(317, "IMAGE_STOP", lambda a, t: self.media_transport(a, t, "stop", "image"))
        reg(318, "IMAGE_NEXT", lambda a, t: self.media_transport(a, t, "next", "image"))
        reg(319, "IMAGE_PREVIOUS", lambda a, t: self.media_transport(a, t, "previous", "image"))
        reg(330, "IMAGE_CYCLE_START", self.cycle_start)
        reg(331, "IMAGE_CYCLE_STOP", lambda a, t: self.cycle.stop())
        reg(332, "IMAGE_CYCLE_STATUS", lambda a, t: self.cycle.status())
        reg(333, "IMAGE_CYCLE_POLL", lambda a, t: self.cycle.events.pop(True))
        reg(340, "SOUND_PLAY", self.sound_play)
        reg(341, "SOUND_QUEUE", self.sound_queue)
        reg(342, "SOUND_PAUSE", lambda a, t: self.media_transport(a, t, "pause", "sound"))
        reg(343, "SOUND_RESUME", lambda a, t: self.media_transport(a, t, "resume", "sound"))
        reg(344, "SOUND_STOP", lambda a, t: self.media_transport(a, t, "stop", "sound"))
        reg(345, "SOUND_NEXT", lambda a, t: self.media_transport(a, t, "next", "sound"))
        reg(346, "SOUND_PREVIOUS", lambda a, t: self.media_transport(a, t, "previous", "sound"))
        reg(350, "BATTERY_PERCENT", battery_percent)
        reg(351, "BATTERY_TEMP", battery_temp)
        reg(352, "BATTERY_CURRENT", battery_current)
        reg(353, "BATTERY_VOLTAGE", battery_voltage)
        reg(354, "SOC_TEMP", soc_temp)
        reg(355, "AUDIO_READY", audio_ready)
        reg(360, "ACCEL_X", lambda a, t: self.accel_axis(a, t, 0))
        reg(361, "ACCEL_Y", lambda a, t: self.accel_axis(a, t, 1))
        reg(362, "ACCEL_Z", lambda a, t: self.accel_axis(a, t, 2))
        reg(363, "ACCEL_STATUS", self.accel_status)
        reg(364, "ACCEL_VECTOR", self.accel_vector)
        reg(365, "GYRO_X", lambda a, t: self.gyro_axis(a, t, 0))
        reg(366, "GYRO_Y", lambda a, t: self.gyro_axis(a, t, 1))
        reg(367, "GYRO_Z", lambda a, t: self.gyro_axis(a, t, 2))
        reg(368, "GYRO_STATUS", self.gyro_status)
        reg(369, "GYRO_VECTOR", self.gyro_vector)
        reg(370, "PROX_STATUS", lambda a, t: self.optical_status(a, t, "tcs3701 ps"))
        reg(371, "PROX_RAW", lambda a, t: self.optical_read(a, t, 8, "tcs3701 ps"))
        reg(372, "LIGHT_STATUS", lambda a, t: self.optical_status(a, t, "tcs3408 als"))
        reg(373, "LIGHT_RAW", lambda a, t: self.optical_read(a, t, 98, "tcs3408 als"))
        reg(374, "MAG_X", lambda a, t: self.mag_axis(a, t, 0))
        reg(375, "MAG_Y", lambda a, t: self.mag_axis(a, t, 1))
        reg(376, "MAG_Z", lambda a, t: self.mag_axis(a, t, 2))
        reg(377, "MAG_STATUS", self.mag_status)
        reg(378, "MAG_VECTOR", self.mag_vector)
        reg(380, "TOUCH_STATUS", self.touch_status)
        reg(381, "TOUCH_POLL", self.touch_poll)

    def touch_status(self, args, text):
        no_args(args, text)
        return int(self.touch.fd is not None), (f"panel=touchpanel down={int(self.touch.down)} "
                                                f"queued={len(self.touch.events.items)} "
                                                f"dropped={self.touch.events.dropped}")

    def touch_poll(self, args, text):
        no_args(args, text)
        return self.touch.events.pop(True)

    @staticmethod
    def accel_status(args, text):
        no_args(args, text)
        try:
            ready = HF_MANAGER.is_char_device() and "bmi2xy acc" in Path("/proc/hf_manager").read_text()
        except OSError:
            ready = False
        return int(ready), f"registered={int(ready)}"

    def accel_sample(self):
        if self.accel_cache and time.monotonic() - self.accel_cache[0] < 0.8:
            return self.accel_cache[1]
        if self.accel_status([], "")[0] != 1:
            raise NativeError("accelerometer unavailable")
        try:
            result = subprocess.run(["/usr/bin/python3", str(HF_SAMPLE),
                                     "--seconds", "1", "--events", "3"],
                                    capture_output=True, text=True, timeout=3, check=False)
            if result.returncode:
                raise NativeError("accelerometer sample failed")
            sample = json.loads(result.stdout)
            if (not sample.get("disabled") or not sample.get("events") or
                sample.get("info", {}).get("name") != "bmi2xy acc" or
                sample["info"].get("gain") != 1000):
                raise NativeError("accelerometer result invalid")
            xyz = sample["events"][-1]["raw_xyz"]
            if len(xyz) != 3 or any(not isinstance(v, int) or abs(v) > 100000 for v in xyz):
                raise NativeError("accelerometer axes invalid")
        except (OSError, subprocess.TimeoutExpired, ValueError, KeyError) as exc:
            raise NativeError("accelerometer sample unavailable") from exc
        self.accel_cache = time.monotonic(), xyz
        return xyz

    def accel_axis(self, args, text, axis):
        no_args(args, text)
        xyz = self.accel_sample()
        return xyz[axis], "unit=raw gain=1000"

    def accel_vector(self, args, text):
        no_args(args, text)
        x, y, z = self.accel_sample()
        return 1, f"x={x} y={y} z={z} gain=1000"

    @staticmethod
    def gyro_status(args, text):
        no_args(args, text)
        try:
            ready = HF_MANAGER.is_char_device() and "bmi2xy gyro" in Path("/proc/hf_manager").read_text()
        except OSError:
            ready = False
        return int(ready), f"registered={int(ready)}"

    def gyro_sample(self):
        if self.gyro_cache and time.monotonic() - self.gyro_cache[0] < 0.8:
            return self.gyro_cache[1]
        if self.gyro_status([], "")[0] != 1:
            raise NativeError("gyroscope unavailable")
        try:
            result = subprocess.run(["/usr/bin/python3", str(HF_SAMPLE), "--sensor", "4",
                                     "--seconds", "1", "--events", "3"],
                                    capture_output=True, text=True, timeout=3, check=False)
            if result.returncode:
                raise NativeError("gyroscope sample failed")
            sample = json.loads(result.stdout)
            if (not sample.get("disabled") or not sample.get("events") or
                sample.get("info", {}).get("name") != "bmi2xy gyro" or
                sample["info"].get("gain") != 1000000):
                raise NativeError("gyroscope result invalid")
            xyz = sample["events"][-1]["raw_xyz"]
            if len(xyz) != 3 or any(not isinstance(v, int) or abs(v) > 100000000 for v in xyz):
                raise NativeError("gyroscope axes invalid")
        except (OSError, subprocess.TimeoutExpired, ValueError, KeyError) as exc:
            raise NativeError("gyroscope sample unavailable") from exc
        self.gyro_cache = time.monotonic(), xyz
        return xyz

    def gyro_axis(self, args, text, axis):
        no_args(args, text)
        xyz = self.gyro_sample()
        return xyz[axis], "unit=raw gain=1000000"

    def gyro_vector(self, args, text):
        no_args(args, text)
        x, y, z = self.gyro_sample()
        return 1, f"x={x} y={y} z={z} gain=1000000"

    @staticmethod
    def mag_status(args, text):
        no_args(args, text)
        try:
            ready = HF_MANAGER.is_char_device() and "akm09918 mag" in Path("/proc/hf_manager").read_text()
        except OSError:
            ready = False
        return int(ready), f"registered={int(ready)}"

    def mag_sample(self):
        if self.mag_cache and time.monotonic() - self.mag_cache[0] < 0.8:
            return self.mag_cache[1]
        if self.mag_status([], "")[0] != 1:
            raise NativeError("magnetometer unavailable")
        try:
            result = subprocess.run(["/usr/bin/python3", str(HF_SAMPLE), "--sensor", "2",
                                     "--seconds", "1", "--events", "3"],
                                    capture_output=True, text=True, timeout=3, check=False)
            if result.returncode:
                raise NativeError("magnetometer sample failed")
            sample = json.loads(result.stdout)
            if (not sample.get("disabled") or not sample.get("events") or
                sample.get("info", {}).get("name") != "akm09918 mag" or
                sample["info"].get("gain") != 1000):
                raise NativeError("magnetometer result invalid")
            xyz = sample["events"][-1]["raw_xyz"]
            if len(xyz) != 3 or any(not isinstance(v, int) or abs(v) > 100000000 for v in xyz):
                raise NativeError("magnetometer axes invalid")
        except (OSError, subprocess.TimeoutExpired, ValueError, KeyError) as exc:
            raise NativeError("magnetometer sample unavailable") from exc
        self.mag_cache = time.monotonic(), xyz
        return xyz

    def mag_axis(self, args, text, axis):
        no_args(args, text)
        xyz = self.mag_sample()
        return xyz[axis], "unit=raw gain=1000"

    def mag_vector(self, args, text):
        no_args(args, text)
        x, y, z = self.mag_sample()
        return 1, f"x={x} y={y} z={z} gain=1000"

    @staticmethod
    def optical_status(args, text, name):
        no_args(args, text)
        try:
            ready = HF_MANAGER.is_char_device() and name in Path("/proc/hf_manager").read_text()
        except OSError:
            ready = False
        return int(ready), f"registered={int(ready)}"

    def optical_read(self, args, text, sensor, name):
        no_args(args, text)
        cached = self.optical_cache.get(sensor)
        if cached and time.monotonic() - cached[0] < 0.5:
            words = cached[1]
        else:
            if self.optical_status([], "", name)[0] != 1:
                raise NativeError("optical sensor unavailable")
            try:
                result = subprocess.run(["/usr/bin/python3", str(HF_SAMPLE),
                                         "--sensor", str(sensor), "--seconds", "2",
                                         "--events", "1"], capture_output=True,
                                        text=True, timeout=3, check=False)
                if result.returncode:
                    raise NativeError("optical sensor sample failed")
                sample = json.loads(result.stdout)
                if (not sample.get("disabled") or not sample.get("events") or
                    sample.get("info", {}).get("name") != name or
                    sample["info"].get("gain") != 1):
                    raise NativeError("optical sensor result invalid")
                words = sample["events"][-1]["raw_xyz"]
                if len(words) != 3 or any(not isinstance(v, int) for v in words):
                    raise NativeError("optical sensor fields invalid")
            except (OSError, subprocess.TimeoutExpired, ValueError, KeyError) as exc:
                raise NativeError("optical sensor sample unavailable") from exc
            self.optical_cache[sensor] = time.monotonic(), words
        return words[0], f"raw1={words[1]} raw2={words[2]} gain=1"

    @staticmethod
    def slot(args):
        if len(args) != 1 or not 0 <= args[0] < 4:
            raise NativeError("usage: slot(0..3)")
        return args[0]

    def time_reset(self, args, text):
        if args or text:
            raise NativeError("usage: no arguments")
        self.epoch = time.monotonic()
        return 0, "reset=1"

    def seq_clear(self, args, text):
        if self.sequence.running:
            raise NativeError("stop sequence before clearing")
        if not args:
            self.sequence.tracks = [None] * 4
            self.sequence.queues = [RecordQueue() for _ in range(4)]
            return 0, "cleared=all"
        slot = self.slot(args)
        self.sequence.tracks[slot] = None
        self.sequence.queues[slot] = RecordQueue()
        return slot, f"cleared={slot}"

    def seq_queue_clear(self, args, text):
        slot = self.slot(args)
        self.sequence.queues[slot] = RecordQueue()
        return 0, f"slot={slot} cleared=1"

    def seq_field(self, args, text):
        if len(args) != 2 or not 0 <= args[0] < 4 or not 0 <= args[1] < 6:
            raise NativeError("usage: slot field_index")
        record = self.sequence.queues[args[0]].last
        if not record or args[1] >= len(record):
            raise NativeError("record field absent")
        key = list(record)[args[1]]
        return record[key], f"field={args[1]} name={key}"

    @staticmethod
    def haptic_status(args, text):
        if args or text:
            raise NativeError("usage: no arguments")
        if not LED.is_dir():
            raise NativeError("haptic unavailable")
        value = int(LED.joinpath("oplus_activate").read_text())
        return value, f"active={value}"

    @staticmethod
    def haptic_stop_call(args, text):
        if args or text:
            raise NativeError("usage: no arguments")
        haptic_stop()
        return 0, "motor=off"

    @staticmethod
    def image_select(args, text):
        if len(args) != 1 or text:
            raise NativeError("usage: pose_index")
        poses = image_names()
        if not 0 <= args[0] < len(poses):
            raise NativeError("pose index out of range")
        return native_image(poses[args[0]])

    @staticmethod
    def image_choose(args, text):
        if len(args) != 3 or args[2] not in (0, 1) or text:
            raise NativeError("usage: pose0 pose1 bit")
        return Runtime.image_select([args[args[2]]], "")

    @staticmethod
    def image_pose(args, text):
        if args or not text:
            raise NativeError("usage: ASCII pose name")
        return native_image(text)

    @staticmethod
    def image_animate(args, text):
        if args or not text:
            raise NativeError("usage: ASCII animation name")
        return native_image(text, True)

    def cycle_start(self, args, text):
        if len(args) > 1 or text:
            raise NativeError("usage: [interval_ms]")
        return self.cycle.start(args[0] if args else None)

    @staticmethod
    def sound_play(args, text):
        if args or not text or not NAME.fullmatch(text):
            raise NativeError("usage: ASCII sound name")
        media("play", "sound", text)
        return 1, f"name={text}"

    @staticmethod
    def image_queue(args, text):
        if args or not text or not NAME.fullmatch(text):
            raise NativeError("usage: ASCII image name")
        media("queue", "image", text)
        return 1, f"queued={text}"

    @staticmethod
    def sound_queue(args, text):
        if args or not text or not NAME.fullmatch(text):
            raise NativeError("usage: ASCII sound name")
        media("queue", "sound", text)
        return 1, f"queued={text}"

    @staticmethod
    def media_transport(args, text, action, kind):
        if args or text:
            raise NativeError("usage: no arguments")
        media(action, kind)
        return 1, f"{kind}={action}"

    def tick(self):
        self.touch.tick()
        self.vm.tick()
        self.sequence.tick()
        try:
            self.cycle.tick()
        except Exception:
            self.cycle.stop()

    def dispatch(self, line):
        match = re.fullmatch(r"NRP/1 ([0-9]{1,10}) ([A-Z_]+)(?: (.*))?", line)
        if not match:
            return "NRP/1 0 ERR BAD_REQUEST expected_NRP/1_id_command"
        rid, command, raw = match.groups()
        raw = raw or ""
        try:
            payload = self.handle(command, raw)
            return f"NRP/1 {rid} OK" + (f" {payload}" if payload else "")
        except NativeError as exc:
            return f"NRP/1 {rid} ERR NATIVE_ERROR {str(exc).replace(' ', '_')}"
        except Exception as exc:
            return f"NRP/1 {rid} ERR INTERNAL {type(exc).__name__}"

    def handle(self, command, raw):
        if command == "PING":
            return "PONG"
        if command == "INFO":
            return "name=Lynx firmware=alpine-v50 protocol=1 vm=1"
        if command == "CAPS":
            names = ",".join(f"{ident}:{name}" for ident, (name, _) in sorted(self.registry.by_id.items()))
            return f"caps=VM,SEQUENCE,THREAD,NATIVE_ASCII,HAPTIC,DISPLAY,AUDIO functions={names}"
        if command == "LOAD":
            try:
                code = bytes.fromhex(raw.replace("_", "").replace(":", ""))
            except ValueError as exc:
                raise NativeError("bad hex program") from exc
            self.vm.load(code)
            return f"loaded={len(code)}"
        if command in ("RUN", "START_THREAD"):
            self.vm.run()
            return "started"
        if command in ("STOP", "STOP_THREAD"):
            self.vm.stop()
            return self.vm.status()
        if command == "RESET_VM":
            self.vm.reset()
            return self.vm.status()
        if command in ("STATUS", "THREAD_STATUS"):
            return self.vm.status()
        if command in ("CALL", "CALL_TEXT", "CALL_MIXED"):
            selector, numbers, text = self.parse_call(command, raw)
            if command == "CALL_TEXT" and self.registry.resolve(selector) == 3:
                value, detail = self.sequence.set_text(text)
            else:
                value, detail = self.registry.call(selector, numbers, text,
                                                   mixed=command == "CALL_MIXED")
            return f"value={value}" + (f" detail={detail}" if detail else "")
        raise NativeError("unknown command")

    @staticmethod
    def parse_call(command, raw):
        head, _, tail = raw.partition(" ")
        if not head:
            raise NativeError("missing function")
        if command == "CALL_TEXT":
            return head, [], tail
        if command == "CALL_MIXED":
            match = re.fullmatch(r'([^"]*) "((?:[^"\\]|\\["\\])*)"', tail)
            if not match:
                # Empty number prefix is legal.
                match = re.fullmatch(r'"((?:[^"\\]|\\["\\])*)"', tail)
                if not match:
                    raise NativeError("expected quoted ASCII")
                nums, quoted = "", match.group(1)
            else:
                nums, quoted = match.groups()
            text = quoted.replace('\\"', '"').replace('\\\\', '\\')
            fields = nums.split() if nums else []
        else:
            fields = tail.split() if tail else []
            text = ""
        if len(fields) > 8:
            raise NativeError("too many arguments")
        try:
            numbers = [int(x, 10) for x in fields]
        except ValueError as exc:
            raise NativeError("expected integer") from exc
        if any(not -2147483648 <= x <= 2147483647 for x in numbers):
            raise NativeError("integer out of range")
        return head, numbers, text


def serve(host, port, peer):
    runtime = Runtime()
    selector = selectors.DefaultSelector()
    active = True
    def shutdown(_signum, _frame):
        nonlocal active
        active = False
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((host, port))
        server.listen(8)
        server.setblocking(False)
        selector.register(server, selectors.EVENT_READ)
        buffers = {}
        while active:
            runtime.tick()
            while runtime.sequence.events:
                event = ("NRP/1 0 EVENT " + runtime.sequence.events.popleft() + "\n").encode()
                for conn in list(buffers):
                    try:
                        conn.sendall(event)
                    except OSError:
                        selector.unregister(conn)
                        buffers.pop(conn, None)
                        conn.close()
            for key, _ in selector.select(0.02):
                if key.fileobj is server:
                    conn, address = server.accept()
                    if peer != "*" and address[0] != peer:
                        conn.close()
                        continue
                    conn.setblocking(False)
                    buffers[conn] = b""
                    selector.register(conn, selectors.EVENT_READ)
                    continue
                conn = key.fileobj
                try:
                    chunk = conn.recv(4096)
                    if not chunk:
                        raise ConnectionError
                    buffers[conn] += chunk
                    if len(buffers[conn]) > 4096:
                        raise ConnectionError
                    while b"\n" in buffers[conn]:
                        line, buffers[conn] = buffers[conn].split(b"\n", 1)
                        try:
                            request = line.decode("ascii").rstrip("\r")
                            answer = runtime.dispatch(request)
                        except UnicodeDecodeError:
                            answer = "NRP/1 0 ERR BAD_REQUEST non_ascii"
                        conn.sendall((answer + "\n").encode())
                except (ConnectionError, OSError):
                    selector.unregister(conn)
                    buffers.pop(conn, None)
                    conn.close()
        runtime.sequence.stop()
        runtime.cycle.stop()
        runtime.touch.close()
        haptic_stop()
        for conn in buffers:
            conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=PHONE_IP)
    parser.add_argument("--port", type=int, default=4243)
    parser.add_argument("--peer", default=NEXUS_IP)
    args = parser.parse_args()
    serve(args.host, args.port, args.peer)
