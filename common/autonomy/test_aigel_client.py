"""Unit tests for Aigel HTTP client (task E6)."""

import json
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import unittest

from aigel_client import AigelClient, AigelUnreachableError, AigelResponseError


class MockAigelHandler(BaseHTTPRequestHandler):
    response_code = 200
    response_payload = {
        "decision": "message",
        "message": "A cat appeared in front of you",
        "patterns": [{"id": "cat-seen", "match": {"sense": "camera"}}],
        "note": "observed cat via camera S1",
    }
    received_requests = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        MockAigelHandler.received_requests.append({
            "path": self.path,
            "headers": dict(self.headers),
            "body": json.loads(body.decode("utf-8")),
        })

        if MockAigelHandler.response_code == 200:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(MockAigelHandler.response_payload).encode("utf-8"))
        else:
            self.send_response(MockAigelHandler.response_code)
            self.end_headers()

    def log_message(self, format, *args):
        pass


class TestAigelClient(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        MockAigelHandler.received_requests = []
        cls.server = HTTPServer(("127.0.0.1", 0), MockAigelHandler)
        cls.port = cls.server.server_port
        cls.thread = threading.Thread(target=cls.server.serve_forever)
        cls.thread.daemon = True
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        MockAigelHandler.response_code = 200
        MockAigelHandler.received_requests = []

    def test_successful_chunk_post_and_response(self):
        url = f"http://127.0.0.1:{self.port}/api/v1/chunk"
        client = AigelClient(endpoint_url=url, auth_token="secret123", host_id="lynx")
        chunk = {
            "reason": "priority",
            "lines": [{"p": 1, "sense": "camera", "event": "object.seen", "fields": {"label": "cat"}}],
        }
        resp = client.send_chunk(chunk)
        self.assertEqual(resp["decision"], "message")
        self.assertEqual(resp["message"], "A cat appeared in front of you")
        self.assertEqual(len(resp["patterns"]), 1)

        self.assertEqual(len(MockAigelHandler.received_requests), 1)
        req = MockAigelHandler.received_requests[0]
        self.assertEqual(req["headers"]["Authorization"], "Bearer secret123")
        self.assertEqual(req["body"]["host"], "lynx")
        self.assertEqual(req["body"]["chunk_reason"], "priority")

    def test_unreachable_error_on_dead_port(self):
        client = AigelClient(endpoint_url="http://127.0.0.1:59999/chunk", max_retries=1, timeout_s=0.2)
        chunk = {"reason": "timeout", "lines": []}
        with self.assertRaises(AigelUnreachableError):
            client.send_chunk(chunk)

    def test_invalid_json_response_raises_error(self):
        MockAigelHandler.response_code = 500
        url = f"http://127.0.0.1:{self.port}/api/v1/chunk"
        client = AigelClient(endpoint_url=url, max_retries=1, timeout_s=0.5)
        chunk = {"reason": "volume", "lines": []}
        with self.assertRaises(AigelUnreachableError):
            client.send_chunk(chunk)



class WireFormatTest(unittest.TestCase):
    """Parsed chunk lines travel as their raw canonical strings (found in e2e with Aigel's intake)."""

    def test_parsed_lines_are_sent_as_raw_strings(self):
        import io
        import json as _json
        from unittest import mock
        import sense
        line = sense.format_line(1, "camera", "object.seen", {"label": "cat"}, "cat")
        sent = {}

        class Resp(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_urlopen(req, timeout=None):
            sent["body"] = _json.loads(req.data.decode("utf-8"))
            return Resp(b'{"decision": "quiet", "patterns": [], "note": ""}')

        client = AigelClient(endpoint_url="http://127.0.0.1:1/api/v1/chunk", host_id="lynx")
        with mock.patch(f"{AigelClient.__module__}.urlopen", fake_urlopen):
            client.send_chunk({"reason": "priority", "lines": [sense.parse_line(line), line]})
        self.assertEqual(sent["body"]["lines"], [line, line])
        self.assertTrue(all(isinstance(x, str) for x in sent["body"]["lines"]))

    def test_priority_rules_are_passed_through(self):
        client = AigelClient(endpoint_url="http://127.0.0.1:1/api/v1/chunk", host_id="lynx")
        rules = [{"id": "wifi-down"}]
        out = client._validate_response({"decision": "quiet", "patterns": [], "note": "",
                                         "priority_rules": rules})
        self.assertEqual(out["priority_rules"], rules)
        self.assertEqual(client._validate_response({"decision": "quiet"})["priority_rules"], [])
        with self.assertRaises(AigelResponseError):
            client._validate_response({"decision": "quiet", "priority_rules": "all"})


if __name__ == "__main__":
    unittest.main()
