#!/usr/bin/env python3
"""Offline tests for Aigel's intake service (A1).

Runs the real HTTP handler on a 127.0.0.1 ephemeral port with a fake
LLM; includes a round-trip through the harness's real AigelClient so
the two sides of the wire contract stay honest with each other.

    cd /noobia && python3 -m unittest discover -s aigel/service -p 'test_aigel_intake.py' -v
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

SERVICE_DIR = os.path.dirname(os.path.abspath(__file__))
NOOBIA = os.environ.get("NOOBIA", "/noobia")
sys.path.insert(0, SERVICE_DIR)
sys.path.insert(0, NOOBIA)

from aigel_intake import AigelIntake, load_host_registry, make_handler  # noqa: E402
from aigel_log import ViewLogger  # noqa: E402
from aigel_think import AigelThinker, QwenError  # noqa: E402
from common.autonomy.aigel_client import (  # noqa: E402
    AigelClient,
    AigelClientError,
    AigelUnreachableError,
    RateLimitError,
)

SECRET = "ab" * 32  # hex
LINES = ["NOOBIA P1 camera object.seen label=cat conf=0.91"]


class FakeLLM:
    def __init__(self, replies):
        self.replies = list(replies)

    def chat(self, messages, max_tokens=1024):
        if not self.replies:
            raise QwenError("fake: out of replies")
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def reply(decision="quiet", message=None, note="saw it"):
    return json.dumps({"decision": decision, "message": message,
                       "patterns": [], "priority_rules": [], "note": note})


class IntakeServerCase(unittest.TestCase):
    reply_auth_enabled = False

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.hosts_file = os.path.join(self.tmp.name, "hosts.json")
        with open(self.hosts_file, "w", encoding="utf-8") as fh:
            json.dump({"lynx": {"hmac_secret": SECRET, "silence_s": 60},
                       "rosie": {"bearer": "top-secret"}}, fh)
        self.hosts = load_host_registry(self.hosts_file)
        self.state_file = os.path.join(self.tmp.name, "state.json")
        self.view_dir = os.path.join(self.tmp.name, "views")
        self.log = ViewLogger("noobia-aigel", file_dir=self.view_dir, force_file=True)
        self.thinker = AigelThinker(llm=FakeLLM([reply("message", "A cat appeared in front of you")]))
        self.intake = AigelIntake(self.thinker, self.hosts, log=self.log,
                                  state_file=self.state_file)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(
            self.intake, require_signed_agent_replies=self.reply_auth_enabled))
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.httpd.server_close)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def restart_server(self, intake) -> None:
        self.httpd.server_close()
        self.thread.join(timeout=2)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(
            intake, require_signed_agent_replies=self.reply_auth_enabled))
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.httpd.server_close)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def view_log(self) -> str:
        path = os.path.join(self.view_dir, "noobia-aigel.log")
        return open(path, encoding="utf-8").read() if os.path.exists(path) else ""

    def signed_post(self, path, body: bytes, secret=SECRET, token=None, extra=None):
        import hashlib
        import hmac as _hmac
        headers = {"Content-Type": "application/json"}
        if secret is not None:
            headers["X-Noobia-Signature"] = _hmac.new(
                secret.encode(), body, hashlib.sha256).hexdigest()
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        headers.update(extra or {})
        req = urllib.request.Request(self.base + path, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))


class AuthTests(IntakeServerCase):
    def test_reply_auth_switch_off_preserves_existing_client(self):
        body = json.dumps({"host": "lynx", "text": "legacy reply"}).encode()
        code, obj = self.signed_post("/api/v1/agent_response", body, secret=None)
        self.assertEqual((code, obj), (200, {"status": "ok"}))

    def test_valid_hmac_accepted(self):
        body = json.dumps({"host": "lynx", "chunk_reason": "PRIORITY", "lines": LINES}).encode()
        code, obj = self.signed_post("/api/v1/chunk", body)
        self.assertEqual(code, 200)
        self.assertEqual(obj["decision"], "message")

    def test_wrong_signature_refused_401(self):
        body = json.dumps({"host": "lynx", "chunk_reason": "PRIORITY", "lines": LINES}).encode()
        code, obj = self.signed_post("/api/v1/chunk", body, secret="cd" * 32)
        self.assertEqual(code, 401)
        self.assertEqual(obj, {"error": "bad signature"})
        self.assertIn("bad signature", self.view_log())

    def test_missing_signature_refused_401(self):
        body = json.dumps({"host": "lynx", "chunk_reason": "PRIORITY", "lines": LINES}).encode()
        req = urllib.request.Request(self.base + "/api/v1/chunk", data=body,
                                     headers={"Content-Type": "application/json"}, method="POST")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 401)

    def test_unknown_host_refused_401(self):
        body = json.dumps({"host": "ghost", "chunk_reason": "PRIORITY", "lines": LINES}).encode()
        code, obj = self.signed_post("/api/v1/chunk", body)
        self.assertEqual(code, 401)
        self.assertEqual(obj, {"error": "unknown host"})

    def test_bearer_host_route(self):
        body = json.dumps({"host": "rosie", "chunk_reason": "TIMEOUT", "lines": LINES}).encode()
        code, obj = self.signed_post("/api/v1/chunk", body, secret=None, token="top-secret")
        self.assertEqual(code, 200)
        code, obj = self.signed_post("/api/v1/chunk", body, secret=None, token="wrong")
        self.assertEqual(code, 401)

    def test_client_wrong_secret_is_final_4xx_not_unreachable(self):
        client = AigelClient(endpoint_url=self.base + "/api/v1/chunk",
                             hmac_secret="cd" * 32, host_id="lynx")
        with self.assertRaises(AigelClientError) as ctx:
            client.send_chunk({"reason": "PRIORITY", "lines": LINES}, now=1000.0)
        self.assertNotIsInstance(ctx.exception, AigelUnreachableError)
        self.assertIn("401", str(ctx.exception))


class BoundsTests(IntakeServerCase):
    def test_oversized_body_413(self):
        body = b"x" * (262_144 + 1)
        code, obj = self.signed_post("/api/v1/chunk", body)
        self.assertEqual(code, 413)

    def test_too_many_lines_400(self):
        body = json.dumps({"host": "lynx", "chunk_reason": "PRIORITY",
                           "lines": [f"line {i}" for i in range(201)]}).encode()
        code, obj = self.signed_post("/api/v1/chunk", body)
        self.assertEqual(code, 400)
        self.assertIn("lines", obj["error"])

    def test_line_over_512_bytes_400(self):
        body = json.dumps({"host": "lynx", "chunk_reason": "PRIORITY",
                           "lines": ["y" * 513]}).encode()
        code, obj = self.signed_post("/api/v1/chunk", body)
        self.assertEqual(code, 400)

    def test_not_json_400(self):
        code, obj = self.signed_post("/api/v1/chunk", b"not json at all")
        self.assertEqual(code, 400)

    def test_lines_not_a_list_400(self):
        body = json.dumps({"host": "lynx", "chunk_reason": "PRIORITY", "lines": "nope"}).encode()
        code, obj = self.signed_post("/api/v1/chunk", body)
        self.assertEqual(code, 400)

    def test_unknown_path_404(self):
        body = b"{}"
        code, obj = self.signed_post("/api/v1/nope", body)
        self.assertEqual(code, 404)


class DecisionTests(IntakeServerCase):
    reply_auth_enabled = True
    def test_reply_is_the_decision_and_state_is_updated(self):
        body = json.dumps({"host": "lynx", "chunk_reason": "PRIORITY", "lines": LINES}).encode()
        code, obj = self.signed_post("/api/v1/chunk", body)
        self.assertEqual(code, 200)
        self.assertEqual(set(obj), {"decision", "message", "patterns", "priority_rules", "note"})
        self.assertEqual(obj["decision"], "message")
        status = self.intake.host_status(now=100.0)
        lynx = status["hosts"]["lynx"]
        self.assertEqual(lynx["last_decision"], "message")
        self.assertEqual(lynx["chunks"], 1)
        self.assertFalse(lynx["silent"])
        log = self.view_log()
        self.assertIn("request host=lynx", log)
        self.assertIn("decision host=lynx decision=message", log)

    def test_priority_rules_visible_in_reply(self):
        rule = {"id": "wifi-down", "source": "wpa_supplicant",
                "match": {"text_contains": ["CTRL-EVENT-DISCONNECTED"]},
                "emit": {"p": 1, "sense": "wifi", "event": "link.down"},
                "examples": {"must": ["CTRL-EVENT-DISCONNECTED bssid=aa:bb reason=3"],
                             "must_not": ["CTRL-EVENT-CONNECTED - Connection completed"]}}
        self.thinker = AigelThinker(llm=FakeLLM([json.dumps(
            {"decision": "quiet", "message": None, "patterns": [],
             "priority_rules": [rule], "note": "raw wifi line deserves a priority"})]))
        self.intake = AigelIntake(self.thinker, self.hosts, log=self.log, state_file=self.state_file)
        self.restart_server(self.intake)
        body = json.dumps({"host": "lynx", "chunk_reason": "TIMEOUT",
                           "lines": ["NOOBIA P0 raw line src=wpa_supplicant ..."]}).encode()
        code, obj = self.signed_post("/api/v1/chunk", body)
        self.assertEqual(code, 200)
        self.assertEqual(len(obj["priority_rules"]), 1)
        self.assertEqual(obj["priority_rules"][0]["origin"], "aigel")

    def test_llm_down_still_answers_200_quiet(self):
        self.thinker = AigelThinker(llm=FakeLLM([QwenError("ollama unreachable")]))
        self.intake = AigelIntake(self.thinker, self.hosts, log=self.log, state_file=self.state_file)
        self.restart_server(self.intake)
        body = json.dumps({"host": "lynx", "chunk_reason": "TIMEOUT", "lines": LINES}).encode()
        code, obj = self.signed_post("/api/v1/chunk", body)
        self.assertEqual(code, 200)
        # LINES is a cat perception: the floor still forwards it with Qwen down.
        self.assertEqual(obj["decision"], "message")
        self.assertIn("cat", obj["message"])
        self.assertIn("unavailable", obj["note"])

    def test_llm_down_non_perception_stays_quiet(self):
        self.thinker = AigelThinker(llm=FakeLLM([QwenError("ollama unreachable")]))
        self.intake = AigelIntake(self.thinker, self.hosts, log=self.log, state_file=self.state_file)
        self.restart_server(self.intake)
        body = json.dumps({"host": "lynx", "chunk_reason": "TIMEOUT",
                           "lines": ["NOOBIA P1 wifi rssi.low dbm=-80"]}).encode()
        code, obj = self.signed_post("/api/v1/chunk", body)
        self.assertEqual(code, 200)
        self.assertEqual(obj["decision"], "quiet")
        self.assertIn("unavailable", obj["note"])

    def test_agent_response_endpoint_and_status(self):
        body = json.dumps({
            "host": "lynx",
            "text": "A laptop, just sitting there — good, my eyes are sharp today. *purr*",
            "tools": ["lynx_haptic_pulse"],
            "job_id": "job123",
            "t": time.time()
        }).encode("utf-8")
        code, data = self.signed_post("/api/v1/agent_response", body)
        self.assertEqual(code, 200)
        self.assertEqual(data.get("status"), "ok")

        with urllib.request.urlopen(f"{self.base}/api/v1/status") as resp:
            st = json.loads(resp.read().decode())
            self.assertIn("agent_replies", st)
            self.assertEqual(len(st["agent_replies"]), 1)
            self.assertEqual(st["agent_replies"][0]["host"], "lynx")
            self.assertIn("sharp today", st["agent_replies"][0]["text"])
            self.assertEqual(st["agent_replies"][0]["tools"], ["lynx_haptic_pulse"])

    def test_agent_response_rejects_unsigned_and_wrong_key(self):
        body = json.dumps({"host": "lynx", "text": "spoof"}).encode()
        code, _ = self.signed_post("/api/v1/agent_response", body, secret=None)
        self.assertEqual(code, 401)
        code, _ = self.signed_post("/api/v1/agent_response", body, secret="wrong")
        self.assertEqual(code, 401)
        self.assertEqual(self.intake.status_body()["agent_replies"], [])

    def test_agent_response_rejects_unknown_host_and_oversized_body(self):
        body = json.dumps({"host": "intruder", "text": "spoof"}).encode()
        code, _ = self.signed_post("/api/v1/agent_response", body)
        self.assertEqual(code, 401)
        code, _ = self.signed_post("/api/v1/agent_response", b"x" * 262_145)
        self.assertEqual(code, 413)

    def test_signed_reply_replay_is_idempotent_across_restart(self):
        body = json.dumps({"host": "lynx", "job_id": "job-replay-1",
                           "text": "once", "t": time.time()}).encode()
        self.assertEqual(self.signed_post("/api/v1/agent_response", body)[1]["status"], "ok")
        self.assertEqual(self.signed_post("/api/v1/agent_response", body)[1]["status"], "duplicate")
        self.assertEqual(len(self.intake.recent_agent_replies()), 1)
        restarted = AigelIntake(self.thinker, self.hosts, log=self.log,
                                 state_file=self.state_file)
        self.restart_server(restarted)
        self.assertEqual(self.signed_post("/api/v1/agent_response", body)[1]["status"], "duplicate")
        self.assertEqual(len(restarted.recent_agent_replies()), 1)

    def test_signed_reply_rejects_stale_timestamp(self):
        body = json.dumps({"host": "lynx", "job_id": "job-stale-1",
                           "text": "old", "t": time.time() - 301}).encode()
        code, obj = self.signed_post("/api/v1/agent_response", body)
        self.assertEqual((code, obj), (400, {"error": "stale reply timestamp"}))
        self.assertEqual(self.intake.recent_agent_replies(), [])

    def test_signed_reply_does_not_ack_when_state_cannot_be_saved(self):
        blocker = os.path.join(self.tmp.name, "not-a-directory")
        with open(blocker, "w", encoding="utf-8") as stream:
            stream.write("x")
        self.intake.state_file = Path(blocker) / "state.json"
        body = json.dumps({"host": "lynx", "job_id": "job-save-fail",
                           "text": "unpersisted", "t": time.time()}).encode()
        code, obj = self.signed_post("/api/v1/agent_response", body)
        self.assertEqual((code, obj), (503, {"error": "reply state unavailable"}))


class LivenessTests(IntakeServerCase):
    def test_silence_flag_flips_after_silence_s(self):
        body = json.dumps({"host": "lynx", "chunk_reason": "TIMEOUT", "lines": LINES}).encode()
        self.signed_post("/api/v1/chunk", body)
        last_seen = self.intake.host_status()["hosts"]["lynx"]["last_seen"]
        self.assertFalse(self.intake.host_status(now=last_seen + 59)["hosts"]["lynx"]["silent"])
        self.assertTrue(self.intake.host_status(now=last_seen + 61)["hosts"]["lynx"]["silent"])

    def test_status_lists_registered_and_seen_hosts(self):
        status = self.intake.host_status()
        self.assertIn("lynx", status["hosts"])
        self.assertIn("rosie", status["hosts"])
        self.assertTrue(status["hosts"]["rosie"]["silent"])  # never seen


class ClientRoundTripTests(IntakeServerCase):
    def test_real_client_sends_and_receives_decision(self):
        client = AigelClient(endpoint_url=self.base + "/api/v1/chunk",
                             hmac_secret=SECRET, host_id="lynx")
        out = client.send_chunk({"reason": "PRIORITY", "lines": LINES}, now=5000.0)
        self.assertEqual(out["decision"], "message")
        self.assertEqual(out["message"], "A cat appeared in front of you")

    def test_client_rate_limit_is_client_side(self):
        client = AigelClient(endpoint_url=self.base + "/api/v1/chunk",
                             hmac_secret=SECRET, host_id="lynx")
        client.send_chunk({"reason": "TIMEOUT", "lines": LINES}, now=6000.0)
        with self.assertRaises(RateLimitError):
            client.send_chunk({"reason": "TIMEOUT", "lines": LINES}, now=6000.5)


class RegistryTests(unittest.TestCase):
    def test_missing_file_is_empty_registry(self):
        self.assertEqual(load_host_registry("/no/such/file.json"), {})

    def test_malformed_registry_raises(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            fh.write("not json")
            path = fh.name
        with self.assertRaises(ValueError):
            load_host_registry(path)

    def test_entries_are_cleaned(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump({"lynx": {"hmac_secret": "  secret  ", "silence_s": "nope",
                                "junk": 1}, "bad": "nope"}, fh)
            path = fh.name
        reg = load_host_registry(path)
        self.assertEqual(reg["lynx"], {"hmac_secret": "secret"})
        self.assertNotIn("bad", reg)


if __name__ == "__main__":
    unittest.main(verbosity=2)
