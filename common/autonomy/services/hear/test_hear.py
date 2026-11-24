"""nexus_hear without the real models: input checks, gating, the HTTP contract."""
from __future__ import annotations

import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import numpy as np

try:
    from . import service
except ImportError:
    import service


def tone(seconds=2.0, rate=48000, amp=8000):
    t = np.arange(int(seconds * rate)) / rate
    return (amp * np.sin(2 * np.pi * 440 * t)).astype("<i2").tobytes()


class Fakes:
    def __init__(self, sounds, text=("hello lynx", "en")):
        self.sounds, self.text, self.whisper_calls = sounds, text, 0

    def install(self, test):
        orig = (service.classify, service.transcribe, dict(service._state))
        service.classify = lambda audio: self.sounds

        def transcribe(audio):
            self.whisper_calls += 1
            return self.text
        service.transcribe = transcribe
        service._state.update(ast=object(), whisper=object(), loading=False)

        def restore():
            service.classify, service.transcribe = orig[0], orig[1]
            service._state.clear()
            service._state.update(orig[2])
        test.addCleanup(restore)
        return self


class HearTest(unittest.TestCase):
    def test_resamples_48k_to_16k_and_measures_rms(self):
        audio, rms, seconds = service.pcm_to_audio(tone(2.0), 48000)
        self.assertEqual(len(audio), 32000)
        self.assertAlmostEqual(seconds, 2.0)
        self.assertAlmostEqual(rms, 8000 / 2 ** 0.5, delta=50)

    def test_rejects_too_short_too_long_and_odd_rates(self):
        for body, rate in ((tone(0.2), 48000), (tone(16), 48000), (tone(1), 12345)):
            with self.assertRaises(ValueError):
                service.pcm_to_audio(body, rate)

    def test_speech_runs_whisper(self):
        f = Fakes([{"label": "Speech", "score": 0.9}, {"label": "Music", "score": 0.1}]).install(self)
        out = service.hear(tone(), 48000)
        self.assertEqual(out["speech"], "hello lynx")
        self.assertEqual(out["language"], "en")
        self.assertEqual([s["label"] for s in out["sounds"]], ["Speech"], "weak sounds dropped")
        self.assertEqual(f.whisper_calls, 1)

    def test_no_speech_no_whisper(self):
        f = Fakes([{"label": "Knock", "score": 0.7}, {"label": "Speech", "score": 0.05}]).install(self)
        out = service.hear(tone(), 48000)
        self.assertEqual(out["speech"], "")
        self.assertEqual(f.whisper_calls, 0)
        self.assertEqual(out["sounds"][0]["label"], "Knock")

    def test_whisper_hallucination_on_weak_speech_is_dropped(self):
        Fakes([{"label": "Speech", "score": 0.3}], text=("Thank you.", "en")).install(self)
        self.assertEqual(service.hear(tone(), 48000)["speech"], "")

    def test_http_contract(self):
        Fakes([{"label": "Speech", "score": 0.8}]).install(self)
        server = ThreadingHTTPServer(("127.0.0.1", 0), service.Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        port = server.server_address[1]

        def post(path, body):
            req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=body, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=10) as r:
                    return r.status, json.loads(r.read())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read())
        code, body = post("/hear?rate=48000", tone())
        self.assertEqual(code, 200, body)
        self.assertEqual(body["speech"], "hello lynx")
        self.assertEqual(post("/hear?rate=48000", tone(0.1))[0], 400)
        self.assertEqual(post("/nope", tone())[0], 404)


if __name__ == "__main__":
    unittest.main()
