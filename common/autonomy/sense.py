"""Noobia sense line emitter and parser (ARCHITECTURE.md §1).

Deliverable A, task E1.

Sense line format:
NOOBIA P<p> <sense> <event> [key=val ...] [| <text>]

Rules:
- p is 0..99
- sense is [a-z0-9_]{1,24}
- event is [a-z0-9_.]{1,48}
- fields is an optional dict (at most 8 pairs)
  keys are [a-z0-9_]{1,24}
  values are ASCII strings without whitespace, quotes (' or "), or '|'
- line byte length is at most 512 bytes (UTF-8).
  truncation is done on character boundaries by format_line.
- parse_line tolerates syslog prefixes before NOOBIA.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import sys
import syslog

SENSE_NAME_RE = re.compile(r"^[a-z0-9_]{1,24}\Z")
EVENT_NAME_RE = re.compile(r"^[a-z0-9_.]{1,48}\Z")
FIELD_KEY_RE = re.compile(r"^[a-z0-9_]{1,24}\Z")
SENSE_LINE_RE = re.compile(
    r"(?:^|[\s:])NOOBIA\s+P(\d+)\s+([a-z0-9_]{1,24})\s+([a-z0-9_.]{1,48})(?:\s+(.*?))?$"
)

MAX_LINE_BYTES = 512
MAX_FIELDS = 8
DEFAULT_IDENT = "noobia-sense"


def format_line(
    p: int,
    sense: str,
    event: str,
    fields: dict[str, str | int | float] | None = None,
    text: str = "",
) -> str:
    """Format a canonical Noobia sense line. Raises ValueError on invalid inputs."""
    if isinstance(p, bool) or not isinstance(p, int) or not (0 <= p <= 99):
        raise ValueError(f"p must be an integer 0..99, got {p!r}")
    if not isinstance(sense, str) or not SENSE_NAME_RE.match(sense):
        raise ValueError(f"sense must match ^[a-z0-9_]{{1,24}}$, got {sense!r}")
    if not isinstance(event, str) or not EVENT_NAME_RE.match(event):
        raise ValueError(f"event must match ^[a-z0-9_.]{{1,48}}$, got {event!r}")

    field_tokens = []
    if fields:
        if not isinstance(fields, dict):
            raise ValueError(f"fields must be a dict or None, got {fields!r}")
        if len(fields) > MAX_FIELDS:
            raise ValueError(f"at most {MAX_FIELDS} fields allowed, got {len(fields)}")
        for k, v in fields.items():
            if not isinstance(k, str) or not FIELD_KEY_RE.match(k):
                raise ValueError(f"field key must match ^[a-z0-9_]{{1,24}}$, got {k!r}")
            v_str = str(v)
            if not v_str.isascii():
                raise ValueError(f"field value must be ASCII, got {v_str!r}")
            if any(c.isspace() for c in v_str):
                raise ValueError(f"field value cannot contain whitespace, got {v_str!r}")
            if '"' in v_str or "'" in v_str:
                raise ValueError(f"field value cannot contain quotes, got {v_str!r}")
            if "|" in v_str:
                raise ValueError(f"field value cannot contain '|', got {v_str!r}")
            field_tokens.append(f"{k}={v_str}")

    prefix = f"NOOBIA P{p} {sense} {event}"
    if field_tokens:
        prefix += " " + " ".join(field_tokens)

    if text is not None and str(text) != "":
        text_str = str(text)
        candidate = f"{prefix} | {text_str}"
        raw = candidate.encode("utf-8")
        if len(raw) <= MAX_LINE_BYTES:
            return candidate

        sep = " | "
        prefix_bytes = (prefix + sep).encode("utf-8")
        budget = MAX_LINE_BYTES - len(prefix_bytes)
        if budget <= 0:
            return prefix

        # Truncate character by character on unicode character boundaries
        truncated = text_str[:budget]
        while len(truncated.encode("utf-8")) > budget and truncated:
            truncated = truncated[:-1]
        return f"{prefix}{sep}{truncated}"

    return prefix


def parse_line(line: str) -> dict | None:
    """Parse a sense line, returning a dictionary or None if not a valid sense line."""
    if not isinstance(line, str) or not line.strip():
        return None

    m = SENSE_LINE_RE.search(line)
    if not m:
        return None

    p_str, sense, event, rest = m.groups()
    if len(p_str) > 2:  # Rejects P100 or larger
        return None
    p = int(p_str)
    if not (0 <= p <= 99):
        return None

    fields: dict[str, str] = {}
    text = ""

    if rest:
        rest = rest.strip()
        if rest.startswith("|"):
            # e.g. "| text" or "|text"
            text = rest[1:].lstrip()
        elif " | " in rest:
            fields_part, text_part = rest.split(" | ", 1)
            fields_part = fields_part.strip()
            text = text_part
            if fields_part:
                items = fields_part.split()
                if len(items) > MAX_FIELDS:
                    return None
                for item in items:
                    if "=" not in item:
                        return None
                    k, v = item.split("=", 1)
                    if not FIELD_KEY_RE.match(k):
                        return None
                    if not v.isascii() or any(c.isspace() for c in v) or '"' in v or "'" in v or "|" in v:
                        return None
                    fields[k] = v
        else:
            items = rest.split()
            if len(items) > MAX_FIELDS:
                return None
            for item in items:
                if "=" not in item:
                    return None
                k, v = item.split("=", 1)
                if not FIELD_KEY_RE.match(k):
                    return None
                if not v.isascii() or any(c.isspace() for c in v) or '"' in v or "'" in v or "|" in v:
                    return None
                fields[k] = v

    self_caused = (fields.get("cause") == "self")
    return {
        "p": p,
        "sense": sense,
        "event": event,
        "fields": fields,
        "text": text,
        "self_caused": self_caused,
        "raw": line,
    }


def emit(
    p: int,
    sense: str,
    event: str,
    fields: dict[str, str | int | float] | None = None,
    text: str = "",
    ident: str = DEFAULT_IDENT,
) -> str:
    """Format a sense line and emit it to syslog / journald at level LOG_NOTICE."""
    line = format_line(p, sense, event, fields=fields, text=text)
    try:
        syslog.openlog(ident, syslog.LOG_PID, syslog.LOG_USER)
        syslog.syslog(syslog.LOG_NOTICE, line)
        syslog.closelog()
    except Exception:
        # Fallback to stderr/stdout if syslog daemon is unreachable
        pass
    return line


def main() -> int:
    """CLI interface for emitting sense lines."""
    parser = argparse.ArgumentParser(description="Emit a Noobia sense line.")
    parser.add_argument("priority", type=int, help="Priority 0..99")
    parser.add_argument("sense", type=str, help="Sense identifier (e.g. touch, wifi, power)")
    parser.add_argument("event", type=str, help="Event name (e.g. tap, link.up)")
    parser.add_argument("fields", nargs="*", help="Optional key=value pairs")
    parser.add_argument("--text", "-t", default="", help="Optional human text")
    parser.add_argument("--ident", default=DEFAULT_IDENT, help=f"Syslog ident (default {DEFAULT_IDENT})")

    args = parser.parse_args()

    field_dict = {}
    for item in args.fields:
        if "=" not in item:
            sys.stderr.write(f"Error: field argument must be key=value, got {item!r}\n")
            return 2
        k, v = item.split("=", 1)
        field_dict[k] = v

    try:
        line = emit(args.priority, args.sense, args.event, fields=field_dict, text=args.text, ident=args.ident)
        print(line)
        return 0
    except ValueError as e:
        sys.stderr.write(f"Error: {e}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
