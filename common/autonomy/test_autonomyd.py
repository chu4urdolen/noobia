"""Tests for noobia-autonomyd (config, secrets, wiring, prioritizer stage, persistence)."""

import io
import json
import os
from contextlib import redirect_stdout
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import agent_link  # noqa: E402
import autonomyd as ad  # noqa: E402
import sense  # noqa: E402

RULE = {"id": "wifi-down", "source": "wpa_supplicant",
        "match": {"text_contains": ["CTRL-EVENT-DISCONNECTED"]},
        "emit": {"p": 1, "sense": "wifi", "event": "link.down"},
        "examples": {"must": ["CTRL-EVENT-DISCONNECTED bssid=aa reason=3"],
                     "must_not": ["CTRL-EVENT-CONNECTED - Connection to aa completed"]},
        "origin": "aigel", "hits": 0}

ADAPTER_SRC = '''
import agent_link
class FakeAdapter(agent_link.Adapter):
    def _send(self, message):
        type(self).sent.append(message)
FakeAdapter.sent = []
'''


class FakeReader:
    backend = "fake"

    def __init__(self):
        self.sense, self.raw = [], []

    def read_new(self):
        out, self.sense[:] = list(self.sense), []
        return out

    def read_new_tagged(self, sources):
        out = [(i, t) for i, t in self.raw if i in sources]
        self.raw[:] = []
        return out


class FakeClient:
    def __init__(self):
        self.chunks, self.reply = [], {"decision": "quiet", "message": None, "patterns": [],
                                       "priority_rules": [], "note": ""}

    def send_chunk(self, chunk):
        self.chunks.append(chunk)
        return dict(self.reply)


class DaemonTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        (self.d / "adapters").mkdir()
        (self.d / "adapters" / "fake_adapter.py").write_text(ADAPTER_SRC)
        self.secret = self.d / "aigel.secret"
        self.secret.write_text("s3cret\n")
        os.chmod(self.secret, 0o600)
        self.config = {
            "host": "lynx",
            "view": {"backend": "file", "log_file": str(self.d / "messages")},
            "aigel": {"url": "http://127.0.0.1:9/api/v1/chunk", "hmac_secret_file": str(self.secret)},
            "adapter": {"path": str(self.d / "adapters"), "spec": "fake_adapter:FakeAdapter",
                        "state_dir": str(self.d / "adapter-state")},
            "ranker": {"store_file": str(self.d / "patterns.json"), "store_capacity": 200,
                       "active_capacity": 100},
            "prioritizer": {"enabled": True, "map_file": str(self.d / "priority_map.json"),
                            "sources": ["wpa_supplicant", "kernel"]},
            "kill_switch": str(self.d / "autonomy.disable"),
        }
        self.logs, self.emitted = [], []

    def tearDown(self):
        self.tmp.cleanup()

    def write_config(self, config=None):
        path = self.d / "autonomy.json"
        path.write_text(json.dumps(config or self.config))
        return path

    def daemon(self, **kw):
        kw.setdefault("reader", FakeReader())
        kw.setdefault("client", FakeClient())
        return ad.Daemon(ad.load_config(self.write_config()), emit=self.emitted.append,
                         log=self.logs.append, clock=lambda: 0.0, **kw)

    def test_inline_secrets_are_refused(self):
        for where in ({"aigel": dict(self.config["aigel"], hmac_secret="plain")},
                      {"extra": {"api_key": "sk-123"}}, {"token": "x"}):
            with self.subTest(where=where), self.assertRaisesRegex(ad.ConfigError, "inline secret"):
                ad.load_config(self.write_config(dict(self.config, **where)))

    def test_required_keys_and_shapes(self):
        for broken in ({k: v for k, v in self.config.items() if k != "aigel"},
                       dict(self.config, host="Lynx Phone"),
                       dict(self.config, aigel={"url": "ftp://x"}),
                       dict(self.config, adapter={"spec": "no_colon"})):
            with self.assertRaises(ad.ConfigError):
                ad.load_config(self.write_config(broken))

    def test_secret_file_must_be_private(self):
        os.chmod(self.secret, 0o644)
        with self.assertRaisesRegex(ad.ConfigError, "chmod 600"):
            ad.read_secret(self.secret)
        os.chmod(self.secret, 0o600)
        self.assertEqual(ad.read_secret(self.secret), "s3cret")

    def test_check_contacts_nothing_and_reports_wiring(self):
        out = self.daemon().check()
        self.assertEqual((out["ok"], out["host"], out["adapter"]), (True, "lynx", "fake_adapter:FakeAdapter"))
        self.assertIn("0 rules", out["prioritizer"])
        self.assertFalse(out["kill_switch_active"])

    def test_main_check_with_real_client_does_no_network(self):
        path = self.write_config(dict(self.config, prioritizer={"enabled": False}))
        with redirect_stdout(io.StringIO()) as buf:
            self.assertEqual(ad.main(["--config", str(path), "--check"]), 0)
        self.assertTrue(json.loads(buf.getvalue())["ok"])

    def test_prioritizer_stage_turns_raw_lines_into_sense_lines(self):
        reader = FakeReader()
        dm = self.daemon(reader=reader)
        dm._accept_rules([RULE])
        reader.raw += [("wpa_supplicant", "CTRL-EVENT-DISCONNECTED bssid=aa reason=3"),
                       ("kernel", "usb 1-1: new device"), ("sshd", "Accepted publickey")]
        summary = dm.step()
        self.assertEqual(summary["prioritized"], 2)                      # sshd not allowlisted
        parsed = [sense.parse_line(l) for l in self.emitted if "heartbeat" not in l]
        self.assertEqual([(p["p"], p["sense"], p["event"]) for p in parsed],
                         [(1, "wifi", "link.down"), (0, "raw", "line")])

    def test_aigel_rules_validated_and_persisted(self):
        dm = self.daemon()
        bad = dict(RULE, id="bad", match={"text_contains": []})
        dm._accept_rules([RULE, bad])
        self.assertTrue(any("accepted id=wifi-down" in l for l in self.logs))
        self.assertTrue(any("rejected id=bad" in l for l in self.logs))
        dm.save()
        again = self.daemon()
        self.assertEqual([r["id"] for r in again.prioritizer.rules], ["wifi-down"])

    def test_without_tagged_reader_prioritizer_is_disabled_loudly(self):
        class SenseOnly:
            backend = "fake"

            def read_new(self):
                return []
        dm = self.daemon(reader=SenseOnly())
        self.assertIsNone(dm.prioritizer)
        self.assertTrue(any("prioritizer disabled" in l for l in self.logs))
        dm._accept_rules([RULE])
        self.assertTrue(any("priority_rules ignored" in l for l in self.logs))

    def test_kill_switch_wired_into_chunker_and_adapter(self):
        reader, client = FakeReader(), FakeClient()
        dm = self.daemon(reader=reader, client=client)
        (self.d / "autonomy.disable").touch()
        reader.sense.append(sense.format_line(1, "camera", "object.seen", {"label": "dog"}))
        dm.step()
        self.assertEqual(client.chunks, [])
        self.assertTrue(dm.check()["kill_switch_active"])

    def test_adapter_must_be_an_agent_link_adapter(self):
        (self.d / "adapters" / "not_adapter.py").write_text("class Nope:\n    pass\n")
        with self.assertRaisesRegex(ad.ConfigError, "not an agent_link.Adapter"):
            ad.load_adapter("not_adapter:Nope", self.d / "adapters", self.d / "s", self.d / "k", print)


if __name__ == "__main__":
    unittest.main()
