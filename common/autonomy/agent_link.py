"""The Aigel <-> agent interface (ARCHITECTURE.md §6), deliverable B.

One message schema and one adapter base class. The regex ranker and Aigel
both deliver through an adapter. Each Noob implements one small subclass
whose ``_send`` hands the message to her own agent: Lynx uses her agent
queue, and later Iris and Rose use theirs.

Guarantees of ``Adapter.deliver``:
- **validated**: malformed messages are rejected, never sent;
- **kill switch**: while the disable file exists, nothing is sent;
- **idempotent**: a message id is sent at most once, even across restarts
  (a bounded persisted id list);
- **rate-limited**: at most ``max_per_minute`` sends in any 60 s window;
- **retry-safe**: if ``_send`` fails, the id is not recorded, so a retry can
  succeed;
- **inspectable**: every outcome is logged to the ``noobia-autonomy`` view.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile
import time
import uuid

SCHEMA_VERSION = 1
MAX_MESSAGE_BYTES = 2048
MAX_TEXT_CHARS = 500
MAX_EVIDENCE = 10
MAX_EVIDENCE_BYTES = 512
SOURCES = ("ranker", "aigel")
KINDS = ("observation", "alert", "speech")
FIELDS = {"v", "id", "host", "time", "source", "kind", "text", "evidence", "pattern_id"}
HOST = re.compile(r"[a-z0-9][a-z0-9_-]{0,31}\Z")
MSG_ID = re.compile(r"[0-9a-f]{32}\Z")
TIME = "%Y-%m-%dT%H:%M:%SZ"
DEFAULT_KILL_SWITCH = Path("/etc/noobia/autonomy.disable")
LOG_IDENT = "noobia-autonomy"


class MessageError(ValueError):
    pass


def make_message(host, source, kind, text, evidence=(), pattern_id=None, now=None):
    """Build and validate a message. ``now`` is a UTC datetime (tests)."""
    message = {
        "v": SCHEMA_VERSION,
        "id": uuid.uuid4().hex,
        "host": host,
        "time": (now or datetime.now(timezone.utc)).strftime(TIME),
        "source": source,
        "kind": kind,
        "text": text,
        "evidence": list(evidence),
        "pattern_id": pattern_id,
    }
    validate(message)
    return message


def validate(message):
    """Raise MessageError unless ``message`` follows schema v1 exactly."""
    if not isinstance(message, dict) or set(message) != FIELDS:
        raise MessageError(f"message needs exactly the fields {sorted(FIELDS)}")
    if message["v"] != SCHEMA_VERSION:
        raise MessageError("unsupported schema version")
    if not isinstance(message["id"], str) or not MSG_ID.match(message["id"]):
        raise MessageError("id must be 32 lowercase hex characters")
    if not isinstance(message["host"], str) or not HOST.match(message["host"]):
        raise MessageError("bad host name")
    try:
        datetime.strptime(message["time"], TIME)
    except (TypeError, ValueError):
        raise MessageError("time must be UTC like 2026-11-21T14:00:00Z") from None
    if message["source"] not in SOURCES:
        raise MessageError(f"source must be one of {SOURCES}")
    if message["kind"] not in KINDS:
        raise MessageError(f"kind must be one of {KINDS}")
    text = message["text"]
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_CHARS:
        raise MessageError(f"text must be 1..{MAX_TEXT_CHARS} characters")
    if any(ord(c) < 32 and c not in "\t" for c in text):
        raise MessageError("text must be a single line without control characters")
    evidence = message["evidence"]
    if not isinstance(evidence, list) or len(evidence) > MAX_EVIDENCE or not all(
            isinstance(e, str) and len(e.encode("utf-8")) <= MAX_EVIDENCE_BYTES for e in evidence):
        raise MessageError(f"evidence must be at most {MAX_EVIDENCE} lines of "
                           f"{MAX_EVIDENCE_BYTES} bytes")
    pid = message["pattern_id"]
    if pid is not None and (not isinstance(pid, str) or not 1 <= len(pid) <= 64):
        raise MessageError("pattern_id must be null or a short string")
    if pid is not None and message["source"] != "ranker":
        raise MessageError("only ranker messages carry a pattern_id")
    if len(json.dumps(message, ensure_ascii=False).encode("utf-8")) > MAX_MESSAGE_BYTES:
        raise MessageError(f"message exceeds {MAX_MESSAGE_BYTES} bytes")
    return message


def syslog_logger(ident=LOG_IDENT):
    """Default logger: one line per outcome in the noobia-autonomy view."""
    try:
        from . import viewlog
    except ImportError:
        import viewlog

    def log(line):
        viewlog.write(ident, line, option=0)
    return log


class Adapter:
    """Base class: subclasses implement ``_send(message)`` and raise on failure."""

    def __init__(self, state_dir, *, kill_switch=DEFAULT_KILL_SWITCH, max_per_minute=6,
                 remember=1000, log=None, clock=time.monotonic):
        self.state = Path(state_dir)
        self.state.mkdir(parents=True, exist_ok=True)
        self.kill_switch = Path(kill_switch)
        self.max_per_minute = max_per_minute
        self.remember = remember
        self.log = log or syslog_logger()
        self.clock = clock
        self.recent = deque()
        self._ids_path = self.state / "delivered_ids.json"
        self._ids = self._load_ids()

    def _load_ids(self):
        try:
            ids = json.loads(self._ids_path.read_text(encoding="utf-8"))
            if isinstance(ids, list) and all(isinstance(i, str) for i in ids):
                return ids[-self.remember:]
        except (OSError, ValueError):
            pass
        return []

    def _save_ids(self):
        fd, tmp = tempfile.mkstemp(prefix=".ids-", dir=self.state)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self._ids[-self.remember:], handle)
            os.replace(tmp, self._ids_path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def _receipt(self, status, message_id, detail=""):
        self.log(f"agent_link deliver status={status} id={message_id or '-'}"
                 + (f" | {detail[:200]}" if detail else ""))
        return {"status": status, "id": message_id, "detail": detail}

    def deliver(self, message):
        message_id = message.get("id") if isinstance(message, dict) else None
        try:
            validate(message)
        except MessageError as exc:
            return self._receipt("rejected", message_id if isinstance(message_id, str) else None,
                                 str(exc))
        if self.kill_switch.exists():
            return self._receipt("disabled", message_id, str(self.kill_switch))
        if message_id in self._ids:
            return self._receipt("duplicate", message_id)
        now = self.clock()
        while self.recent and now - self.recent[0] >= 60:
            self.recent.popleft()
        if len(self.recent) >= self.max_per_minute:
            return self._receipt("rate_limited", message_id)
        try:
            self._send(message)
        except Exception as exc:  # the subclass's own failure; never lose the id
            return self._receipt("failed", message_id, f"{type(exc).__name__}: {exc}")
        self.recent.append(now)
        self._ids.append(message_id)
        self._save_ids()
        return self._receipt("delivered", message_id, message["text"][:80])

    def _send(self, message):
        raise NotImplementedError("an adapter must implement _send")
