import csv
import json
from pathlib import Path
import tempfile
import unittest
import wave

from party import make_grid, run, window_stats


def write_wav(path, frames, channels=2, width=2, rate=8000):
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(channels)
        audio.setsampwidth(width)
        audio.setframerate(rate)
        samples = [v for frame in frames for v in frame]
        if width == 1:
            data = bytes(v + 128 for v in samples)
        else:
            data = b"".join(v.to_bytes(width, "little", signed=True) for v in samples)
        audio.writeframes(data)


class PartyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def measure(self, frames, channels=2, width=2):
        path = self.base / "audio.wav"
        write_wav(path, frames, channels, width)
        return window_stats(path, [{"start_s": 0, "end_s": len(frames) / 8000}])[0]

    def test_antiphase_is_not_silence(self):
        result = self.measure([(16384, -16384)] * 100)
        self.assertAlmostEqual(result["rms_dbfs"], -6.0206, places=4)
        self.assertEqual(result["pan_pct"], 50)

    def test_pan_extremes_and_silence(self):
        self.assertEqual(self.measure([(16384, 0)] * 100)["pan_pct"], 0)
        self.assertEqual(self.measure([(0, 16384)] * 100)["pan_pct"], 100)
        result = self.measure([(0, 0)] * 100)
        self.assertEqual(result["pan_valid"], 0)
        self.assertEqual(result["pan_pct"], "")
        self.assertEqual(result["rms_dbfs"], -120)

    def test_mono_and_pcm_widths(self):
        for width in (1, 2, 3, 4):
            result = self.measure([(2 ** (8 * width - 2),)] * 100, 1, width)
            self.assertEqual(result["pan_pct"], 50)
            self.assertEqual(result["rms"], 0.5)

    def test_quarter_beat_grid_and_offset(self):
        bpm, beats, grid = make_grid({"bpm": 120, "offset_s": 0.2}, 1, None, self.base)
        self.assertAlmostEqual(bpm, 120)
        self.assertEqual(beats[0], 0.2)
        self.assertEqual(grid[0]["start_s"], 0)
        self.assertEqual(grid[-1]["end_s"], 1)
        self.assertTrue(any(abs(t["start_s"] - 0.325) < 1e-9 for t in grid))
        for a, b in zip(grid, grid[1:]):
            self.assertAlmostEqual(a["end_s"], b["start_s"])

    def test_variable_tempo_and_extrapolation(self):
        (self.base / "beats.json").write_text(json.dumps({"beat_times_s": [0.2, 0.7, 1.3]}))
        _, beats, grid = make_grid({"mode": "json", "path": "beats.json"}, 2, None, self.base)
        self.assertTrue(any(abs(t["start_s"] - 0.85) < 1e-9 for t in grid))
        self.assertEqual(grid[0]["timing_source"], "extrapolated")
        self.assertEqual(grid[-1]["end_s"], 2)
        (self.base / "beats.json").write_text('{"beat_times_s": [0.5, 0.4]}')
        with self.assertRaises(ValueError):
            make_grid({"mode": "json", "path": "beats.json"}, 2, None, self.base)

    def config(self):
        write_wav(self.base / "mix.wav", [(16384, 0)] * 8000)
        config = {"song_id": "test", "tracks": {"mix": "mix.wav"},
                  "grid": {"bpm": 120}, "analyses": {"levels": {"enabled": True},
                  "panning": {"enabled": True}, "missing_plugin": {"enabled": False}}}
        path = self.base / "config.json"
        path.write_text(json.dumps(config))
        return path, config

    def test_end_to_end_and_no_overwrite(self):
        path, _ = self.config()
        out = self.base / "run"
        manifest = run(path, out)
        self.assertEqual(manifest["status"], "complete")
        self.assertEqual(manifest["analyses"]["missing_plugin"]["status"], "disabled")
        with (out / "levels.csv").open() as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 8)
        self.assertEqual(float(rows[-1]["end_s"]), 1)
        self.assertEqual(len(manifest["tracks"]["mix"]["sha256"]), 64)
        with self.assertRaises(FileExistsError):
            run(path, out)

    def test_words_keep_unaligned_and_exact_times(self):
        path, config = self.config()
        (self.base / "words.json").write_text(json.dumps({"word_segments": [
            {"word": "hello", "start": 0.13, "end": 0.42, "score": 0.8}, {"word": "world"}]}))
        config["analyses"]["words_json"] = {"enabled": True, "path": "words.json", "track": "mix"}
        path.write_text(json.dumps(config))
        run(path, self.base / "run")
        with (self.base / "run" / "words.csv").open() as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(float(rows[0]["start_s"]), 0.13)
        self.assertEqual(rows[1]["status"], "unaligned")
        self.assertEqual(rows[1]["start_s"], "")

    def test_duration_mismatch_rejected(self):
        path, config = self.config()
        write_wav(self.base / "bass.wav", [(0, 0)] * 4000)
        config["tracks"]["bass"] = "bass.wav"
        path.write_text(json.dumps(config))
        with self.assertRaisesRegex(ValueError, "duration differs"):
            run(path, self.base / "run")
        self.assertFalse((self.base / "run").exists())


if __name__ == "__main__":
    unittest.main()
