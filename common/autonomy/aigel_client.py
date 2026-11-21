"""Aigel HTTP client for host autonomy harness (ARCHITECTURE.md §5).

Deliverable A, task E6.

Sends unexplained chunks to Aigel over authenticated HTTP.
Receives decision ('quiet' or 'message'), patterns, and note.
Includes bounded retries with exponential backoff.
"""

from __future__ import annotations

import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class AigelClientError(Exception):
    pass


class AigelUnreachableError(AigelClientError):
    pass


class AigelResponseError(AigelClientError):
    pass


class AigelClient:
    def __init__(
        self,
        endpoint_url: str = "http://192.168.100.106:112/api/v1/chunk",
        auth_token: str | None = None,
        host_id: str = "lynx",
        timeout_s: float = 15.0,
        max_retries: int = 3,
        backoff_base_s: float = 0.5,
    ):
        self.endpoint_url = endpoint_url
        self.auth_token = auth_token
        self.host_id = host_id
        self.timeout_s = float(timeout_s)
        self.max_retries = int(max_retries)
        self.backoff_base_s = float(backoff_base_s)

    def send_chunk(self, chunk: dict) -> dict:
        """Send chunk to Aigel and return validated decision dictionary."""
        if not isinstance(chunk, dict) or "lines" not in chunk:
            raise AigelClientError("chunk must be a dictionary with 'lines'")

        payload = {
            "host": self.host_id,
            "chunk_reason": chunk.get("reason", "unknown"),
            "lines": chunk["lines"],
        }
        body_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "User-Agent": f"NoobiaAutonomy/0.2 ({self.host_id})",
        }
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"

        last_err = None
        for attempt in range(self.max_retries):
            req = Request(self.endpoint_url, data=body_bytes, headers=headers, method="POST")
            try:
                with urlopen(req, timeout=self.timeout_s) as resp:
                    resp_bytes = resp.read()
                    try:
                        data = json.loads(resp_bytes.decode("utf-8"))
                    except Exception as e:
                        raise AigelResponseError(f"invalid JSON from Aigel: {e}") from e
                    return self._validate_response(data)
            except (URLError, TimeoutError, OSError) as e:
                last_err = e
                if attempt < self.max_retries - 1:
                    time.sleep(self.backoff_base_s * (2 ** attempt))

        raise AigelUnreachableError(f"Aigel endpoint {self.endpoint_url} unreachable: {last_err}") from last_err

    def _validate_response(self, data: dict) -> dict:
        if not isinstance(data, dict):
            raise AigelResponseError("Aigel response must be a JSON object")

        decision = data.get("decision")
        if decision not in ("quiet", "message"):
            raise AigelResponseError(f"decision must be 'quiet' or 'message', got {decision!r}")

        if decision == "message" and not data.get("message"):
            raise AigelResponseError("message decision requires non-empty 'message' field")

        patterns = data.get("patterns", [])
        if not isinstance(patterns, list):
            raise AigelResponseError("patterns must be a list")

        return {
            "decision": decision,
            "message": data.get("message"),
            "patterns": patterns,
            "note": str(data.get("note", "")),
        }
