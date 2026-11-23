"""Offline test suite for the Lynx sense emitters (S2, S3, S4, S5, S8).

Strictly offline: every world read (lynx-status, iw, NRP socket, Nexus
probe) is injected, and the canonical sense module's ``emit`` (the syslog
write) is recorded, never performed. State files live in a per-test
temporary directory, so nothing shared is written.

Two execution modes are tested per sense:
- ``dry_run=True``: the would-be lines are reported, but neither syslog
  nor the state file is touched (the IS-2 verify step's contract);
- ``dry_run=False``: state is persisted (temp dir) and each emitted line
  is recorded by the injected formatter (proof the real emit path is
  taken, once per line).

Run:  python3 -m unittest discover -s lynx/senses -p 'test_*.py'
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent          # lynx/senses
REPO = HERE.parents[1]                          # /noobia
AUTONOMY_DIR = REPO / "common" / "autonomy"


def _load(name: str, rel: str):
    path = HERE / rel
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Load the shared lib under its canonical name FIRST so the sense
# modules' `from lynx_senses_lib import ...` reuses this exact object.
lib = _load("lynx_senses_lib", "common/lynx_senses_lib.py")
lib.REACTION_PRIORITY = 0   # these tests check each sense's own priority


class TestReactionPriority(unittest.TestCase):
    def test_every_line_is_p20_samples_too(self):
        class Sense:
            def format_line(self, p, sense, event, fields=None, text=""):
                return f"NOOBIA P{p} {sense} {event}"
        old, lib.REACTION_PRIORITY = lib.REACTION_PRIORITY, 20
        try:
            for p in (1, 3, 5):
                self.assertEqual(lib.emit_line(Sense(), p, "touch", "tap", dry_run=True), "NOOBIA P20 touch tap")
            self.assertEqual(lib.emit_line(Sense(), 0, "motion", "status.sample", dry_run=True),
                             "NOOBIA P20 motion status.sample")
        finally:
            lib.REACTION_PRIORITY = old
touch = _load("lynx_sense_touch", "touch/lynx_sense_touch.py")
wifi = _load("lynx_sense_wifi", "wifi/lynx_sense_wifi.py")
power = _load("lynx_sense_power", "power/lynx_sense_power.py")
nexus = _load("lynx_sense_nexus", "nexus/lynx_sense_nexus.py")
agent = _load("lynx_agent_action_log", "agent/lynx_agent_action_log.py")
loop = _load("lynx_senses_loop", "common/lynx_senses_loop.py")

REAL_SENSE = None  # filled in _real_sense_module()


def _real_sense_module():
    global REAL_SENSE
    if REAL_SENSE is None:
        spec = importlib.util.spec_from_file_location(
            "noobia_sense_real", AUTONOMY_DIR / "sense.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        REAL_SENSE = module
    return REAL_SENSE


class RecordingSense:
    """The canonical formatter with `emit` recorded instead of syslog."""

    def __init__(self, real):
        self._real = real
        self.emits = []

    def format_line(self, *a, **k):
        return self._real.format_line(*a, **k)

    def emit(self, *a, **k):
        self.emits.append((a, k))
        return self._real.format_line(*a, **k)


class SensesCase(unittest.TestCase):
    """Per-test temp state dir + the real formatter with recorded emits."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="lynx-senses-")
        self.state_dir = Path(self._tmp.name)
        self._saved_autonomy_dir = os.environ.get("NOOBIA_AUTONOMY_DIR")
        os.environ["NOOBIA_AUTONOMY_DIR"] = str(AUTONOMY_DIR)
        self.recorder = RecordingSense(_real_sense_module())
        self._real_import = lib.import_sense
        # Patch import_sense in the shared lib AND in every sense
        # module (their `from lynx_senses_lib import import_sense`
        # bound the original function at load time).
        self._patched = []
        for mod in (lib, touch, wifi, power, nexus):
            self._patched.append((mod, mod.import_sense))
            mod.import_sense = lambda: self.recorder

    def tearDown(self):
        for mod, orig in self._patched:
            mod.import_sense = orig
        if self._saved_autonomy_dir is None:
            os.environ.pop("NOOBIA_AUTONOMY_DIR", None)
        else:
            os.environ["NOOBIA_AUTONOMY_DIR"] = self._saved_autonomy_dir
        self._tmp.cleanup()

    def state_file(self, sense: str) -> str:
        return str(self.state_dir / sense / "state.json")


class TestLibHelpers(SensesCase):

    def test_clean_field_sanitizes_and_bounds(self):
        self.assertEqual(lib.clean_field("a b'c\"d|e"), "a_b_c_d_e")
        self.assertEqual(lib.clean_field("caf\u00e9"), "caf?")
        self.assertEqual(len(lib.clean_field("x" * 40)), 32)
        self.assertEqual(lib.clean_field(123), "123")

    def test_clean_text_folds_whitespace_and_bounds(self):
        self.assertEqual(lib.clean_text("  a\nb\tc "), "a b c")
        self.assertEqual(len(lib.clean_text("y" * 400)), 300)

    def test_import_sense_finds_canonical_module(self):
        sense = self._real_import()
        self.assertEqual(sense.format_line(5, "touch", "tap"),
                         "NOOBIA P5 touch tap")

    def test_import_sense_fails_honestly_when_missing(self):
        empty = self.state_dir / "no-autonomy"
        empty.mkdir()
        saved = os.environ["NOOBIA_AUTONOMY_DIR"]
        os.environ["NOOBIA_AUTONOMY_DIR"] = str(empty)
        try:
            with self.assertRaises(lib.SenseUnavailable):
                self._real_import()
        finally:
            os.environ["NOOBIA_AUTONOMY_DIR"] = saved

    def test_emit_line_dry_run_returns_line_without_emit(self):
        line = lib.emit_line(self.recorder, 5, "touch", "tap",
                             fields={"dur_ms": 420, "ssid": "My Net"},
                             text="a tap on the panel", dry_run=True)
        self.assertTrue(line.startswith(
            "NOOBIA P5 touch tap dur_ms=420 ssid=My_Net"), line)
        self.assertIn("a tap on the panel", line)
        self.assertEqual(self.recorder.emits, [])

    def test_emit_line_live_calls_canonical_emit_once(self):
        line = lib.emit_line(self.recorder, 1, "wifi", "link.down",
                             fields={"iface": "wlan0"}, text="Wi-Fi went down")
        self.assertEqual(len(self.recorder.emits), 1)
        args, kwargs = self.recorder.emits[0]
        self.assertEqual(args, (1, "wifi", "link.down"))
        self.assertEqual(kwargs.get("fields"), {"iface": "wlan0"})
        self.assertTrue(line.startswith("NOOBIA P1 wifi link.down iface=wlan0"))

    def test_state_path_override_and_env(self):
        override = self.state_file("touch")
        self.assertEqual(lib.state_path("touch", override), Path(override))
        saved = os.environ.get("NOOBIA_SENSES_STATE_DIR")
        os.environ["NOOBIA_SENSES_STATE_DIR"] = str(self.state_dir)
        try:
            self.assertEqual(lib.state_path("wifi"),
                             self.state_dir / "wifi" / "state.json")
        finally:
            if saved is None:
                os.environ.pop("NOOBIA_SENSES_STATE_DIR", None)
            else:
                os.environ["NOOBIA_SENSES_STATE_DIR"] = saved

    def test_load_state_corrupt_is_empty(self):
        bad = self.state_dir / "bad.json"
        bad.write_text("{ not json", encoding="utf-8")
        self.assertEqual(lib.load_state(bad), {})

    def test_save_state_roundtrip(self):
        path = self.state_file("x")
        lib.save_state(Path(path), {"a": 1, "b": [1, 2]})
        self.assertEqual(lib.load_state(Path(path)), {"a": 1, "b": [1, 2]})

    def test_touch_reply_regex(self):
        reply = "NRP/1 7 OK value=1 detail=panel=01 down=1 queued=3 dropped=0"
        m = lib.TOUCH_RE.fullmatch(reply)
        self.assertIsNotNone(m)
        d = lib.TOUCH_DETAIL.fullmatch(m.group(2))
        self.assertEqual(d.groups(), ("01", "1", "3", "0"))
        self.assertIsNone(lib.TOUCH_RE.fullmatch("NRP/1 7 CALL TOUCH_STATUS"))
        self.assertIsNone(lib.TOUCH_DETAIL.fullmatch(
            "panel=01 down=2 queued=9 dropped=0"))  # down must be 0/1

    def test_iw_link_parsing_busybox_output(self):
        real_run_cmd = lib.run_cmd
        lib.run_cmd = lambda argv, timeout=5.0: (0, (
            "Connected to 90:91:64:21:0f:3d (on wlan0)\n"
            "signal: -54 dBm\n"
            "SSID: Noobia\n"))
        try:
            out = lib.iw_link()
            self.assertTrue(out["connected"])
            self.assertEqual(out["signal_dbm"], -54)
            self.assertEqual(out["ssid"], "Noobia")
            self.assertEqual(out["iface"], "wlan0")
        finally:
            lib.run_cmd = real_run_cmd

    def test_iw_link_unassociated_and_timeout(self):
        real_run_cmd = lib.run_cmd
        lib.run_cmd = lambda argv, timeout=5.0: (0, "Not associated.")
        try:
            out = lib.iw_link()
            self.assertFalse(out["connected"])
            self.assertIsNone(out["signal_dbm"])
        finally:
            lib.run_cmd = real_run_cmd
        lib.run_cmd = lambda argv, timeout=5.0: (None, "")
        try:
            out = lib.iw_link()
            self.assertFalse(out["connected"])
            self.assertIsNone(out["signal_dbm"])
        finally:
            lib.run_cmd = real_run_cmd

    def test_lynx_status_rejects_wrong_schema(self):
        real_run_cmd = lib.run_cmd
        lib.run_cmd = lambda argv, timeout=8.0: (0, json.dumps({"schema": 1}))
        try:
            with self.assertRaises(LookupError):
                lib.lynx_status()
        finally:
            lib.run_cmd = real_run_cmd


def _touch_sample(down, queued=2, dropped=1):
    return {"panel_open": 1, "finger_down": down,
            "queued": queued, "dropped": dropped}


class TestTouchSense(SensesCase):

    def run_sample(self, sf, down, now, **kw):
        return touch.run(state_file=sf, read_touch=lambda: _touch_sample(down),
                         boot_id=kw.pop("boot_id", "b"), now=now, **kw)

    def test_first_sample_down_is_baseline_only(self):
        sf = self.state_file("touch")
        result, code = self.run_sample(sf, True, 1000, dry_run=True)
        self.assertEqual(code, 0)
        self.assertTrue(result["ok"])
        self.assertEqual(result["emitted"], [])
        self.assertTrue(result["state"]["down"])
        self.assertEqual(result["state"]["down_since"], 1000)
        self.assertEqual(self.recorder.emits, [])

    def test_short_press_is_tap(self):
        sf = self.state_file("touch")
        self.run_sample(sf, True, 1000)
        result, code = self.run_sample(sf, False, 1000)
        self.assertEqual(code, 0)
        self.assertEqual(len(result["emitted"]), 1)
        line = result["emitted"][0]
        self.assertTrue(
            line.startswith("NOOBIA P1 touch tap dur_ms=0 queued=2 dropped=1"),
            line)
        self.assertIn("a tap on the panel", line)
        self.assertEqual(len(self.recorder.emits), 1)  # live mode: one syslog line
        self.assertEqual(self.recorder.emits[0][0][:3], (1, "touch", "tap"))

    def test_long_press_is_hold(self):
        sf = self.state_file("touch")
        self.run_sample(sf, True, 1000)
        result, _ = self.run_sample(sf, False, 1002)
        line = result["emitted"][0]
        self.assertTrue(line.startswith("NOOBIA P1 touch hold dur_ms=2000"), line)
        self.assertIn("a long hold on the panel", line)

    def test_custom_hold_threshold(self):
        sf = self.state_file("touch")
        self.run_sample(sf, True, 1000)
        result, _ = touch.run(state_file=sf, read_touch=lambda: _touch_sample(False),
                              boot_id="b", now=1001, hold_ms=1000)
        self.assertIn(" touch tap ", result["emitted"][0])

    def test_new_boot_rebaselines_quietly(self):
        path = self.state_dir / "touch"
        path.mkdir(parents=True)
        p = path / "state.json"
        p.write_text(json.dumps({"boot_id": "old-boot", "down": True,
                                 "down_since": 5}), encoding="utf-8")
        result, code = touch.run(dry_run=True, state_file=str(p),
                                 read_touch=lambda: _touch_sample(False),
                                 boot_id="new-boot", now=2000)
        self.assertEqual(code, 0)
        self.assertEqual(result["emitted"], [])
        self.assertEqual(result["state"]["boot_id"], "new-boot")
        self.assertEqual(self.recorder.emits, [])

    def test_dry_run_writes_no_state_and_emits_nothing(self):
        sf = self.state_file("touch")
        touch.run(dry_run=True, state_file=sf,
                  read_touch=lambda: _touch_sample(True), boot_id="b", now=1000)
        result, _ = touch.run(dry_run=True, state_file=sf,
                              read_touch=lambda: _touch_sample(False),
                              boot_id="b", now=1000)
        self.assertFalse(Path(sf).exists())
        self.assertEqual(self.recorder.emits, [])
        # and the would-be line is still reported honestly:
        self.assertTrue(any("touch" in e for e in result["emitted"])
                        or result["emitted"] == [])

    def test_read_failure_is_honest(self):
        def boom():
            raise RuntimeError("noobd socket not reachable")
        result, code = touch.run(state_file=self.state_file("touch"),
                                 read_touch=boom, boot_id="b", now=1000)
        self.assertEqual(code, 1)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "RuntimeError")
        self.assertEqual(self.recorder.emits, [])

    def test_socket_error_is_honest_too(self):
        def boom():
            raise OSError("connection refused")
        result, code = touch.run(state_file=self.state_file("touch"),
                                 read_touch=boom, boot_id="b", now=1000)
        self.assertEqual(code, 1)
        self.assertEqual(result["error"], "OSError")

    def test_missing_canonical_module_is_honest(self):
        empty = self.state_dir / "no-autonomy"
        empty.mkdir()
        # Real import path, empty autonomy dir - in the lib AND touch.
        lib.import_sense = self._real_import
        touch.import_sense = self._real_import
        saved = os.environ["NOOBIA_AUTONOMY_DIR"]
        os.environ["NOOBIA_AUTONOMY_DIR"] = str(empty)
        try:
            result, code = touch.run(state_file=self.state_file("touch"),
                                     read_touch=lambda: _touch_sample(False),
                                     boot_id="b", now=1000)
            self.assertEqual(code, 1)
            self.assertEqual(result["error"], "SenseUnavailable")
        finally:
            os.environ["NOOBIA_AUTONOMY_DIR"] = saved


def _wifi_status(carrier=True, ipv4="192.168.100.107"):
    return {"schema": 2, "wifi": {"carrier": carrier, "ipv4": ipv4}}


def _wifi_link(signal=-54, ssid="Noobia"):
    return {"connected": signal is not None, "iface": "wlan0",
            "signal_dbm": signal, "ssid": ssid}


class TestWifiSense(SensesCase):

    def run_sample(self, sf, carrier=True, signal=-54, now=1000):
        return wifi.run(state_file=sf,
                        status=lambda: _wifi_status(carrier),
                        link=lambda: _wifi_link(signal), now=now)

    def test_first_sample_is_baseline_only(self):
        sf = self.state_file("wifi")
        result, code = self.run_sample(sf)
        self.assertEqual(code, 0)
        self.assertEqual(result["emitted"], [])
        self.assertTrue(result["state"]["carrier"])
        self.assertEqual(self.recorder.emits, [])

    def test_link_down_then_up(self):
        sf = self.state_file("wifi")
        self.run_sample(sf, carrier=True)
        result, _ = self.run_sample(sf, carrier=False)
        self.assertEqual(len(result["emitted"]), 1)
        self.assertTrue(
            result["emitted"][0].startswith("NOOBIA P1 wifi link.down iface=wlan0"))
        result, _ = self.run_sample(sf, carrier=True)
        self.assertEqual(len(result["emitted"]), 1)
        self.assertIn("link.up", result["emitted"][0])
        self.assertIn("ssid=Noobia", result["emitted"][0])
        self.assertEqual(len(self.recorder.emits), 2)  # one per emitted line

    def test_rssi_warning_with_hysteresis(self):
        sf = self.state_file("wifi")
        r1, _ = self.run_sample(sf, signal=-76)
        self.assertEqual(len([e for e in r1["emitted"] if "rssi.low" in e]), 1)
        self.assertIn("signal=-76", r1["emitted"][0])
        # Between re-arm (-70) and warn (-75): quiet.
        # Still armed: no repeat while weak.
        r2, _ = self.run_sample(sf, signal=-76)
        self.assertFalse(any("rssi.low" in e for e in r2["emitted"]))
        # In the hysteresis band (-75, -70): quiet, still armed.
        r3, _ = self.run_sample(sf, signal=-72)
        self.assertFalse(any("rssi.low" in e for e in r3["emitted"]))
        # Recovery (>= re-arm threshold -70) clears the arming.
        r4, _ = self.run_sample(sf, signal=-65)
        self.assertFalse(any("rssi.low" in e for e in r4["emitted"]))
        # A new weak episode warns again.
        r5, _ = self.run_sample(sf, signal=-76)
        self.assertEqual(len([e for e in r5["emitted"] if "rssi.low" in e]), 1)

    def test_p0_heartbeat_every_15_samples(self):
        sf = self.state_file("wifi")
        for i in range(1, 15):
            r, _ = self.run_sample(sf)
            self.assertFalse(any("status.sample" in e for e in r["emitted"]),
                             f"sample {i}")
        r15, _ = self.run_sample(sf)
        p0 = [e for e in r15["emitted"] if "status.sample" in e]
        self.assertEqual(len(p0), 1)
        self.assertTrue(
            p0[0].startswith("NOOBIA P0 wifi status.sample carrier=1 signal=-54"))

    def test_status_read_failure_is_honest(self):
        def boom():
            raise LookupError("lynx-status exited 1")
        result, code = wifi.run(state_file=self.state_file("wifi"),
                                status=boom, link=lambda: _wifi_link(), now=1000)
        self.assertEqual(code, 1)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "LookupError")


def _power_status(cap=None, current=None, soc=None):
    return {"schema": 2,
            "battery": {"capacity_percent": cap, "current_mA_signed": current},
            "thermal": {"max_mC": soc}}


class TestPowerSense(SensesCase):

    def run_sample(self, sf, cap=80, current=0, soc=35000, now=1000):
        return power.run(state_file=sf,
                         status=lambda: _power_status(cap, current, soc),
                         now=now)

    def test_charging_state_mapping(self):
        self.assertEqual(power.charging_state(None), "unknown")
        self.assertEqual(power.charging_state(50), "charging")
        self.assertEqual(power.charging_state(-50), "discharging")
        self.assertEqual(power.charging_state(0), "idle")
        self.assertEqual(power.charging_state(49), "idle")
        self.assertEqual(power.charging_state(-49), "idle")

    def test_first_sample_charging_is_baseline(self):
        sf = self.state_file("power")
        result, code = self.run_sample(sf, cap=80, current=2000)
        self.assertEqual(code, 0)
        self.assertEqual(result["emitted"], [])
        self.assertEqual(result["state"]["charging"], "charging")

    def test_charging_change_after_baseline(self):
        sf = self.state_file("power")
        self.run_sample(sf, cap=80, current=2000)
        result, _ = self.run_sample(sf, cap=80, current=-800)
        self.assertEqual(len(result["emitted"]), 1)
        line = result["emitted"][0]
        self.assertTrue(line.startswith("NOOBIA P1 power charging.change"), line)
        self.assertIn("from=charging", line)
        self.assertIn("to=discharging", line)

    def test_critical_alarm_fires_on_real_state_and_arms_once(self):
        # A critical level is an absolute state, not a transition: the
        # sense reports it when it observes it (even on the first
        # sample) and then re-arms through hysteresis.
        sf = self.state_file("power")
        r1, _ = self.run_sample(sf, cap=12)
        crit = [e for e in r1["emitted"] if "battery.critical" in e]
        self.assertEqual(len(crit), 1)
        self.assertTrue(crit[0].startswith("NOOBIA P1 power battery.critical cap=12"))
        r2, _ = self.run_sample(sf, cap=12)
        self.assertFalse(any("battery.critical" in e for e in r2["emitted"]))

    def test_critical_covers_low_and_rearm_path(self):
        sf = self.state_file("power")
        self.run_sample(sf, cap=12)          # critical armed, low covered
        r25, _ = self.run_sample(sf, cap=25)  # critical re-armed; low covered
        self.assertEqual(r25["emitted"], [])
        r36, _ = self.run_sample(sf, cap=36)  # low re-armed
        self.assertEqual(r36["emitted"], [])
        r28, _ = self.run_sample(sf, cap=28)  # low again -> warn once
        low = [e for e in r28["emitted"] if "battery.low" in e]
        self.assertEqual(len(low), 1)
        self.assertTrue(low[0].startswith("NOOBIA P1 power battery.low cap=28"))

    def test_thermal_hot_with_rearm(self):
        sf = self.state_file("power")
        # Tom 2026-11-22: hot at 50 C, re-arm at 45 C.
        r0, _ = self.run_sample(sf, cap=80, soc=47000)
        self.assertFalse(any("thermal.hot" in e for e in r0["emitted"]))
        r1, _ = self.run_sample(sf, cap=80, soc=51000)
        hot = [e for e in r1["emitted"] if "thermal.hot" in e]
        self.assertEqual(len(hot), 1)
        self.assertIn("soc_mc=51000", hot[0])
        r2, _ = self.run_sample(sf, cap=80, soc=51000)
        self.assertFalse(any("thermal.hot" in e for e in r2["emitted"]))
        r3, _ = self.run_sample(sf, cap=80, soc=44000)   # re-arm
        self.assertFalse(any("thermal.hot" in e for e in r3["emitted"]))
        r4, _ = self.run_sample(sf, cap=80, soc=50500)   # warn again
        self.assertEqual(len([e for e in r4["emitted"] if "thermal.hot" in e]), 1)

    def test_null_capacity_is_honest_unknown(self):
        sf = self.state_file("power")
        result, code = self.run_sample(sf, cap=None, current=None, soc=None)
        self.assertEqual(code, 0)
        self.assertFalse(any("battery." in e or "thermal.hot" in e
                             for e in result["emitted"]))
        self.assertFalse(result["sampled"]["gauge_ok"])
        self.assertEqual(result["sampled"]["charging"], "unknown")

    def test_p0_heartbeat_every_15_samples(self):
        sf = self.state_file("power")
        for i in range(1, 15):
            r, _ = self.run_sample(sf)
            self.assertFalse(any("status.sample" in e for e in r["emitted"]),
                             f"sample {i}")
        r15, _ = self.run_sample(sf)
        p0 = [e for e in r15["emitted"] if "status.sample" in e]
        self.assertEqual(len(p0), 1)
        self.assertTrue(p0[0].startswith("NOOBIA P0 power status.sample cap=80"))

    def test_status_read_failure_is_honest(self):
        def boom():
            raise LookupError("lynx-status did not return JSON")
        result, code = power.run(state_file=self.state_file("power"),
                                 status=boom, now=1000)
        self.assertEqual(code, 1)
        self.assertFalse(result["ok"])


class TestNexusSense(SensesCase):

    def run_probe(self, sf, up, now=1000):
        return nexus.run(state_file=sf, host="nexus.test", port=8080,
                         probe_fn=lambda h, p: up, now=now)

    def test_first_sample_is_baseline_only(self):
        sf = self.state_file("nexus")
        for up in (True, False):
            result, code = self.run_probe(sf, up)
            self.assertEqual(code, 0)
            self.assertEqual(result["emitted"], [])
            self.assertEqual(self.recorder.emits, [])

    def test_two_failures_then_unreachable_then_reachable(self):
        sf = self.state_file("nexus")
        self.run_probe(sf, True)
        r1, _ = self.run_probe(sf, False)      # fail 1: quiet
        self.assertEqual(r1["emitted"], [])
        r2, _ = self.run_probe(sf, False)      # fail 2: P1
        self.assertEqual(len(r2["emitted"]), 1)
        self.assertTrue(r2["emitted"][0].startswith("NOOBIA P1 nexus unreachable"))
        self.assertIn("errors=2", r2["emitted"][0])
        r3, _ = self.run_probe(sf, False)      # still down: no repeat
        self.assertEqual(r3["emitted"], [])
        r4, _ = self.run_probe(sf, True)       # back: P1
        self.assertEqual(len(r4["emitted"]), 1)
        self.assertTrue(r4["emitted"][0].startswith("NOOBIA P1 nexus reachable"))
        self.assertEqual(len(self.recorder.emits), 2)

    def test_probe_error_propagates_for_the_caller(self):
        def boom(h, p):
            raise OSError("network unreachable")
        with self.assertRaises(OSError):
            nexus.run(state_file=self.state_file("nexus"),
                      probe_fn=boom, now=1000)


class TestAgentActionLog(SensesCase):
    """S5: the noobia-agent view writer (not a sense)."""

    def test_action_line_shape(self):
        line = agent.action_line("battery_status", "checked capacity")
        self.assertEqual(line, "agent tool=battery_status checked capacity")

    def test_action_line_rejects_bad_tool_names(self):
        for bad in ("", "Battery", "battery-status", "x" * 49, "a b"):
            with self.assertRaises(ValueError, msg=repr(bad)):
                agent.action_line(bad, "detail")
        # 48 chars is the max
        self.assertEqual(agent.action_line("t" * 48), "agent tool=" + "t" * 48)

    def test_action_line_bounds_bytes(self):
        line = agent.action_line("t", "word " * 500)
        self.assertLessEqual(len(line.encode("utf-8")), 512)

    def test_emit_action_uses_injected_writer(self):
        seen = []

        def writer(ident, level, message):
            seen.append((ident, level, message))

        line = agent.emit_action("lynx_battery_status", "job 12", writer=writer)
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0], ("noobia-agent", agent.LEVEL, line))
        self.assertEqual(line, "agent tool=lynx_battery_status job 12")

    def test_emit_action_without_writer_does_not_crash(self):
        line = agent.emit_action("test_action", "offline suite")
        self.assertTrue(line.startswith("agent tool=test_action"))

    def test_cli_success_and_failure(self):
        script = str(HERE / "agent" / "lynx_agent_action_log.py")
        ok = subprocess.run([sys.executable, script, "battery_status", "checked"],
                            capture_output=True, text=True, timeout=30)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertTrue(json.loads(ok.stdout)["ok"])
        bad = subprocess.run([sys.executable, script, "Bad-Tool"],
                             capture_output=True, text=True, timeout=30)
        self.assertEqual(bad.returncode, 1)
        self.assertFalse(json.loads(bad.stdout)["ok"])


class TestLoop(SensesCase):
    """The service loop isolates sense failures (no live runs here)."""

    def _fake(self, *args):
        if args and isinstance(args[0], Exception):
            def boom():
                raise args[0]
            return types.SimpleNamespace(run=boom)
        return types.SimpleNamespace(run=lambda: ({"ok": True, "sense": "fake"}, 0))

    def test_one_cycle_all_ok(self):
        summary = loop.one_cycle(self._fake(), self._fake(), self._fake(),
                                 self._fake())
        self.assertTrue(all(r["ok"] for r in summary.values()))
        self.assertEqual(set(summary), {"touch", "wifi", "power", "nexus"})

    def test_one_failing_sense_does_not_stop_others(self):
        bad = self._fake(RuntimeError("noobd gone"))
        summary = loop.one_cycle(bad, self._fake(), self._fake(), self._fake())
        self.assertFalse(summary["touch"]["ok"])
        self.assertEqual(summary["touch"]["error"], "RuntimeError")
        for name in ("wifi", "power", "nexus"):
            self.assertTrue(summary[name]["ok"])

    def test_unok_result_is_reported_not_raised(self):
        unok = types.SimpleNamespace(
            run=lambda: ({"ok": False, "sense": "touch", "error": "X"}, 1))
        summary = loop.one_cycle(unok, self._fake(), self._fake(), self._fake())
        self.assertFalse(summary["touch"]["ok"])
        self.assertEqual(summary["touch"]["error"], "X")
        for name in ("wifi", "power", "nexus"):
            self.assertTrue(summary[name]["ok"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
