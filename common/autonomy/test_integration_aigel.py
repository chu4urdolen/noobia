"""Cross-component integration: harness -> real AigelClient -> real Aigel intake (HTTP).

Both sides passed their own tests while being unable to talk to each other
(the client sent parsed dicts, the intake requires raw line strings, and the
client dropped priority_rules). This test keeps them honest. Only Qwen is
faked; HTTP, HMAC, chunking, routing and delivery are real.
"""

from http.server import ThreadingHTTPServer
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("NOOBIA", HERE.parents[1]))
sys.path.insert(0, str(HERE))

import agent_link  # noqa: E402
import aigel_client  # noqa: E402
import harness as hm  # noqa: E402
import sense  # noqa: E402
import trigger  # noqa: E402

try:
    sys.path.insert(0, str(ROOT / "aigel" / "service"))
    sys.path.insert(0, str(ROOT / "aigel"))
    import aigel_intake  # noqa: E402
except ImportError:  # Aigel's service not present in this checkout
    aigel_intake = None


class FakeQwenThinker:
    def __init__(self):
        self.seen = []

    def decide(self, host, reason, lines):
        self.seen.append((host, reason, list(lines)))
        return {"decision": "message", "message": "A dog is in front of you",
                "patterns": [], "note": "fake qwen",
                "priority_rules": [{"id": "wifi-down", "source": "wpa_supplicant"}]}


class Recorder(agent_link.Adapter):
    def _send(self, message):
        self.sent.append(message)


@unittest.skipIf(aigel_intake is None, "aigel/service not in this checkout")
class HarnessToAigelTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.thinker = FakeQwenThinker()
        self.logs = []
        log = type("L", (), {"write": lambda _self, line: self.logs.append(line)})()
        self.intake = aigel_intake.AigelIntake(self.thinker, {"lynx": {"hmac_secret": "test-secret"}},
                                               log=log)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), aigel_intake.make_handler(self.intake))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/api/v1/chunk"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def build(self, secret="test-secret"):
        adapter = Recorder(Path(self.tmp.name) / "state",
                           kill_switch=Path(self.tmp.name) / "off", log=lambda l: None)
        adapter.sent = []
        client = aigel_client.AigelClient(endpoint_url=self.url, hmac_secret=secret,
                                          host_id="lynx", max_retries=1, timeout_s=5)
        inbox, rules = [], []

        def read_new():
            out, inbox[:] = list(inbox), []
            return out
        h = hm.Harness(host="lynx", read_new=read_new, chunker=trigger.Chunker(), client=client,
                       adapter=adapter, ranker=None, on_priority_rules=rules.extend,
                       log=lambda l: None, clock=lambda: 0.0)
        return h, inbox, adapter, rules

    def test_priority_line_reaches_aigel_and_her_message_reaches_the_noob(self):
        h, inbox, adapter, rules = self.build()
        line = sense.format_line(1, "camera", "object.seen", {"label": "dog", "conf": "0.88"}, "dog")
        inbox.append(line)
        h.step()
        (host, reason, lines), = self.thinker.seen
        self.assertEqual((host, reason, lines), ("lynx", "priority", [line]))
        self.assertEqual([m["text"] for m in adapter.sent], ["A dog is in front of you"])
        self.assertEqual(adapter.sent[0]["source"], "aigel")
        self.assertEqual(rules, [{"id": "wifi-down", "source": "wpa_supplicant"}])

    def test_wrong_secret_is_refused_and_chunk_stays_queued(self):
        h, inbox, adapter, _ = self.build(secret="wrong")
        inbox.append(sense.format_line(1, "camera", "object.seen", {"label": "dog"}))
        summary = h.step()
        self.assertEqual(self.thinker.seen, [])
        self.assertEqual(adapter.sent, [])
        self.assertEqual(summary["queued"], 1)
        self.assertTrue(any("bad signature" in l for l in self.logs))


if __name__ == "__main__":
    unittest.main()
