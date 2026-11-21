#!/usr/bin/env python3
"""Offline tests for Aigel's web page and chat (A4).

Real HTTP handler on a 127.0.0.1 ephemeral port, fake LLM; the
thinker's chat turn is tested directly too.

    cd /noobia && python3 -m unittest discover -s aigel/service -p 'test_aigel_web.py' -v
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

SERVICE_DIR = os.path.dirname(os.path.abspath(__file__))
NOOBIA = os.environ.get("NOOBIA", "/noobia")
sys.path.insert(0, SERVICE_DIR)
sys.path.insert(0, NOOBIA)

from aigel_intake import AigelIntake, load_host_registry, make_handler  # noqa: E402
from aigel_log import ViewLogger  # noqa: E402
from aigel_think import (  # noqa: E402
    AigelChatUnavailable,
    AigelThinker,
    QwenError,
)
from aigel_web import AigelWeb  # noqa: E402

SECRET = "cd" * 32
LINES = ["NOOBIA P1 wifi link.down interface=wlan0"]


class FakeLLM:
    """Replies in order, for decide() and chat() alike."""

    def __init__(self, replies):
        self.replies = list(replies)

    def chat(self, messages, max_tokens=1024):
        if not self.replies:
            raise QwenError("fake: out of replies")
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def decision(decision="quiet", message=None, note="saw it"):
    return json.dumps({"decision": decision, "message": message,
                       "patterns": [], "priority_rules": [], "note": note})


class WebCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        hosts_file = os.path.join(self.tmp.name, "hosts.json")
        with open(hosts_file, "w", encoding="utf-8") as fh:
            json.dump({"lynx": {"hmac_secret": SECRET}}, fh)
        self.hosts = load_host_registry(hosts_file)
        self.view_dir = os.path.join(self.tmp.name, "views")
        self.log = ViewLogger("noobia-aigel", file_dir=self.view_dir, force_file=True)
        self.thinker = AigelThinker(llm=FakeLLM([]))
        self.state_file = os.path.join(self.tmp.name, "state.json")
        self.web = None  # set where a page/chat is under test
        self.intake = AigelIntake(self.thinker, self.hosts, log=self.log,
                                  state_file=self.state_file)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.intake, self.web))
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.httpd.server_close)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    # -- helpers ------------------------------------------------------------

    def post(self, path, body: bytes, token: str | None = None,
             sign: bool = True) -> tuple[int, dict]:
        headers = {"Content-Type": "application/json"}
        if sign and path == "/api/v1/chunk":
            headers["X-Noobia-Signature"] = hmac.new(
                SECRET.encode(), body, hashlib.sha256).hexdigest()
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        req = urllib.request.Request(self.base + path, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    def get(self, path) -> tuple[int, str, str]:
        try:
            with urllib.request.urlopen(self.base + path, timeout=5) as resp:
                return resp.status, resp.headers.get("Content-Type", ""), resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            return e.code, e.headers.get("Content-Type", ""), e.read().decode("utf-8")

    def send_chunk(self, reason="priority") -> None:
        body = json.dumps({"host": "lynx", "chunk_reason": reason,
                           "lines": LINES}).encode("utf-8")
        self.thinker.llm.replies.insert(0, decision(
            "message", "Lynx lost Wi-Fi", "link went down"))
        code, obj = self.post("/api/v1/chunk", body)
        self.assertEqual(code, 200)
        self.assertEqual(obj["decision"], "message")

    def view_log(self) -> str:
        path = os.path.join(self.view_dir, "noobia-aigel.log")
        return open(path, encoding="utf-8").read() if os.path.exists(path) else ""

    # -- status + recent -----------------------------------------------------

    def test_status_includes_recent_chunks(self):
        self.send_chunk(reason="priority")
        code, _, text = self.get("/api/v1/status")
        self.assertEqual(code, 200)
        data = json.loads(text)
        self.assertEqual(data["hosts"]["lynx"]["last_decision"], "message")
        self.assertFalse(data["hosts"]["lynx"]["silent"])
        recent = data["recent"]
        self.assertEqual(len(recent), 1)
        c = recent[0]
        self.assertEqual(c["host"], "lynx")
        self.assertEqual(c["reason"], "priority")
        self.assertEqual(c["lines"], len(LINES))
        self.assertEqual(c["decision"], "message")
        self.assertEqual(c["message"], "Lynx lost Wi-Fi")
        self.assertEqual(c["note"], "link went down")

    def test_recent_is_bounded_per_host(self):
        for _ in range(25):
            self.send_chunk()
        with open(self.state_file, encoding="utf-8") as fh:
            state = json.load(fh)
        self.assertEqual(len(state["lynx"]["recent"]), 20)
        code, _, text = self.get("/api/v1/status")
        self.assertEqual(len(json.loads(text)["recent"]), 20)

    def test_recent_sorted_newest_first(self):
        self.send_chunk()
        self.send_chunk()
        code, _, text = self.get("/api/v1/status")
        recent = json.loads(text)["recent"]
        self.assertGreaterEqual(recent[0]["t"], recent[1]["t"])

    # -- chat ----------------------------------------------------------------

    def chat_setup(self, replies, **kw):
        self.thinker.llm.replies = replies
        self.web = AigelWeb(self.intake, self.log, **kw)
        self.httpd.server_close()
        self.thread.join(timeout=2)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.intake, self.web))
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.httpd.server_close)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def test_chat_replies_and_logs(self):
        self.chat_setup(["Hello, Noob. I am here, listening."])
        body = json.dumps({"message": "Hello Aigel"}).encode("utf-8")
        code, obj = self.post("/api/v1/chat", body, sign=False)
        self.assertEqual(code, 200)
        self.assertEqual(obj["reply"], "Hello, Noob. I am here, listening.")
        log = self.view_log()
        self.assertIn("chat in: 11 chars", log)
        self.assertIn("chat out: 34 chars", log)

    def test_chat_reply_is_bounded(self):
        self.chat_setup(["word " * 3000])
        body = json.dumps({"message": "tell me everything"}).encode("utf-8")
        code, obj = self.post("/api/v1/chat", body, sign=False)
        self.assertEqual(code, 200)
        self.assertLessEqual(len(obj["reply"]), 1000)

    def test_chat_empty_message_rejected(self):
        self.chat_setup(["unused"])
        code, obj = self.post("/api/v1/chat", json.dumps(
            {"message": "   "}).encode(), sign=False)
        self.assertEqual(code, 400)
        self.assertIn("error", obj)

    def test_chat_message_too_long_rejected(self):
        self.chat_setup(["unused"])
        code, obj = self.post("/api/v1/chat", json.dumps(
            {"message": "a" * 1001}).encode(), sign=False)
        self.assertEqual(code, 400)
        self.assertIn("bound", obj["error"])

    def test_chat_body_too_large(self):
        self.chat_setup(["unused"])
        body = (b'{"message": "' + b"x" * 9000 + b'"}')
        code, obj = self.post("/api/v1/chat", body, sign=False)
        self.assertEqual(code, 413)

    def test_chat_qwen_down_is_honest_503(self):
        self.chat_setup([QwenError("ollama unreachable")])
        body = json.dumps({"message": "hello?"}).encode("utf-8")
        code, obj = self.post("/api/v1/chat", body, sign=False)
        self.assertEqual(code, 503)
        self.assertIn("aigel unavailable", obj["error"])

    def test_chat_rate_limited(self):
        self.chat_setup(["one", "two"])
        body = json.dumps({"message": "hi"}).encode("utf-8")
        code1, _ = self.post("/api/v1/chat", body, sign=False)
        code2, obj2 = self.post("/api/v1/chat", body, sign=False)
        self.assertEqual(code1, 200)
        self.assertEqual(code2, 429)
        self.assertIn("thinking", obj2["error"])

    def test_chat_token_auth(self):
        self.chat_setup(["a", "b", "c"])
        self.web = AigelWeb(self.intake, self.log, chat_token="top-secret")
        self.httpd.server_close()
        self.thread.join(timeout=2)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.intake, self.web))
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.httpd.server_close)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        body = json.dumps({"message": "hi"}).encode("utf-8")
        code, obj = self.post("/api/v1/chat", body, sign=False)
        self.assertEqual(code, 401)
        code, obj = self.post("/api/v1/chat", body, sign=False, token="wrong")
        self.assertEqual(code, 401)
        code, obj = self.post("/api/v1/chat", body, sign=False, token="top-secret")
        self.assertEqual(code, 200)

    def test_chat_not_enabled_when_no_web(self):
        body = json.dumps({"message": "hi"}).encode("utf-8")
        code, obj = self.post("/api/v1/chat", body, sign=False)
        self.assertEqual(code, 404)

    # -- the page ---------------------------------------------------------------

    def test_page_is_self_contained(self):
        self.web = AigelWeb(self.intake, self.log)
        self.httpd.server_close()
        self.thread.join(timeout=2)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.intake, self.web))
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.httpd.server_close)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        code, ctype, text = self.get("/")
        self.assertEqual(code, 200)
        self.assertIn("text/html", ctype)
        self.assertIn("Aigel", text)
        self.assertIn("/api/v1/status", text)
        self.assertIn("/api/v1/chat", text)
        # fully offline: no external resources, no scripts from elsewhere
        self.assertNotIn("http://", text)
        self.assertNotIn("https://", text)
        self.assertNotIn("src=", text)

    def test_unknown_paths_404(self):
        code, _, _ = self.get("/api/v1/nope")
        self.assertEqual(code, 404)
        code, _ = self.post("/api/v1/status", b"{}", sign=False)
        self.assertEqual(code, 404)

    def test_chunk_still_strict_without_web(self):
        # A1 semantics unchanged when the web layer is absent
        self.thinker.llm.replies.insert(0, decision("quiet", None, "fine"))
        body = json.dumps({"host": "lynx", "chunk_reason": "timeout",
                           "lines": LINES}).encode("utf-8")
        code, obj = self.post("/api/v1/chunk", body)
        self.assertEqual(code, 200)
        self.assertEqual(obj["decision"], "quiet")
        self.assertIn("priority_rules", obj)


class ThinkerChatTest(unittest.TestCase):
    """A2-style bounds on the A4 chat turn, without HTTP."""

    def test_cleans_and_bounds(self):
        thinker = AigelThinker(llm=FakeLLM(["  lots   \nof  \nwords  "]))
        reply = thinker.chat("  hello \n there  ")
        self.assertEqual(reply, "lots of words")
        thinker = AigelThinker(llm=FakeLLM(["x" * 5000]))
        self.assertLessEqual(len(thinker.chat("hi")), 1000)

    def test_empty_message_rejected(self):
        thinker = AigelThinker(llm=FakeLLM(["unused"]))
        with self.assertRaises(ValueError):
            thinker.chat("   ")

    def test_llm_down_raises_unavailable(self):
        thinker = AigelThinker(llm=FakeLLM([QwenError("down")]))
        with self.assertRaises(AigelChatUnavailable):
            thinker.chat("hi")

    def test_blank_reply_gets_an_honest_one(self):
        thinker = AigelThinker(llm=FakeLLM(["   "]))
        reply = thinker.chat("hi")
        self.assertTrue(reply)


if __name__ == "__main__":
    unittest.main()
