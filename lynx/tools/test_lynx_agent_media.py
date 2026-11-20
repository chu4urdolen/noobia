"""Validation and output boundaries for Lynx's local media agent bridge."""

import unittest

from lynx_agent_media import arguments, compact


class MediaAgentTest(unittest.TestCase):
    def test_catalog_and_status_reject_arguments(self):
        self.assertEqual(arguments("catalog", {}), ["/usr/local/bin/lynx-media", "catalog"])
        with self.assertRaises(ValueError):
            arguments("status", {"kind": "sound"})

    def test_play_uses_fixed_argv_and_rejects_unlisted_shapes(self):
        self.assertEqual(arguments("play", {"kind": "sound", "item": "chime"}),
                         ["/usr/local/bin/lynx-media", "play", "sound", "chime"])
        for item in ("../etc", "a;reboot", "", "UPPER", "x" * 64):
            with self.assertRaises(ValueError):
                arguments("play", {"kind": "sound", "item": item})
        with self.assertRaises(ValueError):
            arguments("play", {"kind": "sound", "item": "chime", "extra": 1})

    def test_status_discards_history_and_catalog_details(self):
        status = compact("status", {"ok": True, "channels": {
            "sound": {"mode": "stopped", "current": None, "queue": [], "history": ["beep"]}}})
        self.assertEqual(status["channels"]["sound"]["queue_count"], 0)
        self.assertNotIn("history", str(status))
        catalog = compact("catalog", {"ok": True, "sounds": {"chime": {"file": "x.wav"}},
                                      "images": {"dance": {"frames": [1, 2]}}})
        self.assertEqual(catalog, {"ok": True, "sounds": ["chime"], "images": ["dance"]})
        played = compact("play", {"ok": True, "channel": {"mode": "playing",
                                 "current": "beep", "queue": [], "history": ["private"]}})
        self.assertEqual(played, {"ok": True, "channel": {"mode": "playing",
                                        "current": "beep", "queue_count": 0}})


if __name__ == "__main__":
    unittest.main()
