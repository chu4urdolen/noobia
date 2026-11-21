"""Aigel HTTP client for host autonomy harness (ARCHITECTURE.md §5).

Deliverable A, task E6. Review fixes C1-C4 applied.

Sends unexplained chunks to Aigel over authenticated HTTP.
Receives decision ('quiet' or 'message'), patterns, and note.
Includes HTTP error classification, 64 KiB size capping, HMAC signatures,
and strict rate limiting (1 chunk/s, max 30 chunks/hour).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MAX_RESPONSE_BYTES = 65536  # C2: 64 KiB cap
MAX_CHUNKS_PER_HOUR = 30
MIN_INTERVAL_S = 1.0


class AigelClientError(Exception):
    pass


class AigelUnreachableError(AigelClientError):
    pass


class AigelResponseError(AigelClientError):
    pass


class RateLimitError(AigelClientError):
    pass


class AigelClient:
    def __init__(
        self,
        endpoint_url: str = "http://192.168.100.106:112/api/v1/chunk",
        auth_token: str | None = None,
        hmac_secret: str | None = None,
        host_id: str = "lynx",
        timeout_s: float = 15.0,
        max_retries: int = 3,
        backoff_base_s: float = 0.5,
    ):
        self.endpoint_url = endpoint_url
        self.auth_token = auth_token
        self.hmac_secret = hmac_secret
        self.host_id = host_id
        self.timeout_s = float(timeout_s)
        self.max_retries = int(max_retries)
        self.backoff_base_s = float(backoff_base_s)

        # C3: Rate limiting timestamps
        self._sent_timestamps: list[float] = []

    def _check_rate_limit(self, now: float) -> None:
        """Enforce at most 1 chunk per second and 30 chunks per hour (C3)."""
        # Purge timestamps older than 1 hour (3600s)
        self._sent_timestamps = [t for t in self._sent_timestamps if now - t < 3600.0]

        if self._sent_timestamps:
            if now - self._sent_timestamps[-1] < MIN_INTERVAL_S:
                raise RateLimitError(f"rate limit exceeded: min interval is {MIN_INTERVAL_S}s")

        if len(self._sent_timestamps) >= MAX_CHUNKS_PER_HOUR:
            raise RateLimitError(f"rate limit exceeded: max {MAX_CHUNKS_PER_HOUR} chunks per hour")

    def send_chunk(self, chunk: dict, now: float | None = None) -> dict:
        """Send chunk to Aigel and return validated decision dictionary."""
        if not isinstance(chunk, dict) or "lines" not in chunk:
            raise AigelClientError("chunk must be a dictionary with 'lines'")

        current_time = time.time() if now is None else now
        self._check_rate_limit(current_time)

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

        # C4: Optional HMAC signature
        if self.hmac_secret:
            sig = hmac.new(self.hmac_secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
            headers["X-Noobia-Signature"] = sig

        last_err = None
        for attempt in range(self.max_retries):
            req = Request(self.endpoint_url, data=body_bytes, headers=headers, method="POST")
            try:
                with urlopen(req, timeout=self.timeout_s) as resp:
                    # C2: Read at most MAX_RESPONSE_BYTES and verify no overflow
                    resp_bytes = resp.read(MAX_RESPONSE_BYTES)
                    if resp.read(1):
                        raise AigelResponseError("Aigel response exceeds 64 KiB cap")

                    try:
                        data = json.loads(resp_bytes.decode("utf-8"))
                    except Exception as e:
                        raise AigelResponseError(f"invalid JSON from Aigel: {e}") from e

                    self._sent_timestamps.append(current_time)
                    return self._validate_response(data)

            except HTTPError as e:
                # C1: Classify HTTP errors separately; 4xx errors are client errors and must NOT be retried
                if 400 <= e.code < 500:
                    raise AigelClientError(f"HTTP {e.code} client error from Aigel: {e.reason}") from e
                # 5xx errors can be retried
                last_err = e
                if attempt < self.max_retries - 1:
                    time.sleep(self.backoff_base_s * (2 ** attempt))

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
