#!/usr/bin/env python3
"""G1/G2: listening clips to nexus_hear, speech and sound lines, startle."""
import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault("NOOBIA_AUTONOMY_DIR", "/noobia/common/autonomy")

from lynx.senses.hearing import lynx_sense_hearing as h


def fake_emit(sense, p, s, event, fields=None, text="", dry_run=False):
    return f"P{p} {s} {event} " + " ".join(f"{k}={v}" for k, v in (fields or {}).items()) + (f" | {text}" if text else "")


class Listen(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sf = str(Path(self.tmp.name) / "state.json")
        self._emit = h.emit_line
        self.lines = []
        h.emit_line = lambda *a, **k: (self.lines.append(fake_emit(*a, **k)), self.lines[-1])[1]
        h._listen.update(thread=None, last_end=0.0, last_sound={}, error=None, ok=False)

    def tearDown(self):
        h.emit_line = self._emit
        self.tmp.cleanup()

    def test_speech_becomes_one_line_and_clip_is_dropped(self):
        seen = {}
        def asker(pcm):
            seen["len"] = len(pcm)
            return {"speech": "Good morning, Lynx.", "language": "en", "sounds": [{"label": "Speech", "score": 0.9}]}
        h.start_listening(object(), recorder=lambda: b"\x00\x01" * 1000, asker=asker, now=100.0, background=False)
        self.assertEqual(seen["len"], 2000)
        self.assertEqual(self.lines, ["P1 hearing speech lang=en | Good morning, Lynx."])

    def test_notable_sound_once_then_quiet_for_a_while(self):
        ans = {"speech": "", "sounds": [{"label": "Inside, small room", "score": 0.9},
                                        {"label": "Knock", "score": 0.7}]}
        h.heard_lines(object(), ans, 100.0, False)
        h.heard_lines(object(), ans, 150.0, False)
        h.heard_lines(object(), ans, 100.0 + h.SOUND_REPEAT_S, False)
        self.assertEqual(self.lines, ["P1 hearing sound score=0.7 | knock"] * 2)

    def test_room_tone_and_weak_sounds_say_nothing(self):
        h.heard_lines(object(), {"speech": "", "sounds": [{"label": "Static", "score": 0.9},
                                                          {"label": "Dog", "score": 0.1}]}, 100.0, False)
        self.assertEqual(self.lines, [])

    def test_failure_is_recorded_not_raised(self):
        def boom():
            raise RuntimeError("microphone busy")
        h.start_listening(object(), recorder=boom, asker=lambda pcm: {}, now=100.0, background=False)
        self.assertIn("microphone busy", h._listen["error"])
        self.assertEqual(self.lines, [])

    def run_level(self, rms, peak, t, asker=None):
        res, code = h.run(state_file=self.sf, reader=lambda: {"captured": True, "late_rms": rms, "late_peak": peak},
                          now=t, enabled=True, recorder=lambda: b"\x00" * 100,
                          asker=asker or (lambda pcm: {"speech": "", "sounds": []}))
        self.assertEqual(code, 0)
        th = h._listen.get("thread")
        if th is not None:
            th.join(5)
        return res

    def test_loud_sample_starts_a_clip_quiet_does_not(self):
        calls = []
        asker = lambda pcm: (calls.append(1), {"speech": "hi", "language": "en", "sounds": []})[1]
        for t in range(5):
            self.run_level(5.0, 20, 1000 + t * 3, asker)
        self.assertEqual(calls, [])
        self.run_level(60.0, 300, 1100, asker)
        self.assertEqual(calls, [1])
        self.assertIn("P1 hearing speech lang=en | hi", self.lines)

    def test_startle_on_a_sudden_bang_once(self):
        for t in range(6):
            self.run_level(5.0, 20, 1000 + t * 3)
        self.run_level(5000.0, 30000, 1100)
        self.run_level(5000.0, 30000, 1105)
        startles = [l for l in self.lines if " startle " in l]
        self.assertEqual(len(startles), 1, self.lines)


if __name__ == "__main__":
    unittest.main()
