"""Verify the one-shot API request is bounded and does not persist the key."""

import io
import json
import unittest
from unittest.mock import patch

import lynx_inference_probe


class ProbeTest(unittest.TestCase):
    def test_request_is_one_bounded_nonstored_response(self):
        sent = []

        def answer(request, timeout):
            sent.append((request, timeout))
            body = {"model": "gpt-5.4-mini", "output": [{"type": "message",
                    "content": [{"type": "output_text", "text": "Lynx is online."}]}],
                    "usage": {"input_tokens": 20, "output_tokens": 5}}
            return io.BytesIO(json.dumps(body).encode())

        with patch.object(lynx_inference_probe.urllib.request, "urlopen", side_effect=answer):
            result = lynx_inference_probe.probe("private-test-key", "gpt-5.4-mini")
        self.assertEqual(result["answer"], "Lynx is online.")
        self.assertEqual(len(sent), 1)
        request, timeout = sent[0]
        self.assertEqual(timeout, 30)
        payload = json.loads(request.data)
        self.assertEqual(payload["max_output_tokens"], 64)
        self.assertIs(payload["store"], False)
        self.assertNotIn("private-test-key", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
