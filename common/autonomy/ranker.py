"""Structured pattern store and ranker (ARCHITECTURE.md §4).

Deliverable A, task E4.

Used only for PRIORITY chunks. Explains lines using active structured patterns
compiled with exact literal matches and validated against examples.
Unexplained lines are routed to Aigel.
"""

from __future__ import annotations

import re
from typing import Any
try:
    from .sense import parse_line
except (ImportError, ValueError):
    from sense import parse_line

BACKREF_RE = re.compile(r"\\[1-9]|\(\?P=[a-zA-Z0-9_]+\)")
NESTED_QUANT_RE = re.compile(r"\([^)]*[\*\+\?][^)]*\)[\*\+\?]")


def _pattern_matches(pattern: dict, line: dict) -> bool:
    """Check if pattern matches parsed line dictionary."""
    match = pattern.get("match", {})
    if match.get("sense") and match["sense"] != line.get("sense"):
        return False
    if match.get("event") and match["event"] != line.get("event"):
        return False

    expected_fields = match.get("fields")
    if expected_fields:
        line_fields = line.get("fields", {})
        for k, v in expected_fields.items():
            if line_fields.get(k) != str(v):
                return False

    text_contains = match.get("text_contains")
    if text_contains:
        if text_contains not in line.get("text", ""):
            return False

    regex = pattern.get("regex")
    if regex:
        raw = line.get("raw", "")
        if not re.search(regex, raw):
            return False

    return True


def validate_pattern(pattern: dict, corpus: list[str]) -> None:
    """Validate structured pattern and its regex/examples against corpus. Raises ValueError on failure."""
    if not isinstance(pattern, dict):
        raise ValueError("pattern must be a dictionary")

    for req in ("id", "match", "message", "to_noob", "cooldown_s", "examples", "hits", "origin"):
        if req not in pattern:
            raise ValueError(f"missing required pattern field: {req}")

    examples = pattern.get("examples")
    if not isinstance(examples, dict) or "must" not in examples or "must_not" not in examples:
        raise ValueError("examples must contain 'must' and 'must_not' lists")

    must = examples.get("must", [])
    must_not = examples.get("must_not", [])
    if not isinstance(must, list) or not isinstance(must_not, list):
        raise ValueError("must and must_not must be lists of strings")

    regex = pattern.get("regex")
    if regex is not None:
        if not isinstance(regex, str):
            raise ValueError("regex must be a string")
        if len(regex) > 200:
            raise ValueError(f"regex exceeds 200 characters: {len(regex)}")
        if not must_not:
            raise ValueError("advanced regex requires at least one must_not example")
        if BACKREF_RE.search(regex):
            raise ValueError(f"back-references are not permitted in pattern regex: {regex}")
        if NESTED_QUANT_RE.search(regex):
            raise ValueError(f"nested quantifiers are not permitted in pattern regex: {regex}")

        try:
            compiled = re.compile(regex)
        except re.error as e:
            raise ValueError(f"invalid regex: {e}") from e

        for c_line in corpus:
            if compiled.search(c_line):
                raise ValueError(f"regex matches baseline corpus line: {c_line}")

    # Verify against must examples
    for line_str in must:
        parsed = parse_line(line_str)
        if not parsed or not _pattern_matches(pattern, parsed):
            raise ValueError(f"pattern failed to match 'must' example: {line_str}")

    # Verify against must_not examples
    for line_str in must_not:
        parsed = parse_line(line_str)
        if parsed and _pattern_matches(pattern, parsed):
            raise ValueError(f"pattern erroneously matched 'must_not' example: {line_str}")


class Ranker:
    def __init__(
        self,
        patterns: list[dict],
        store_capacity: int = 200,
        active_capacity: int = 100,
    ):
        self.store_capacity = int(store_capacity)
        self.active_capacity = int(active_capacity)

        # Sort input patterns stably by hits descending
        sorted_pats = sorted(patterns, key=lambda p: p.get("hits", 0), reverse=True)
        self._store = sorted_pats[:self.store_capacity]
        self._archive = sorted_pats[self.store_capacity:]
        self._last_delivery: dict[str, float] = {}

    @property
    def store(self) -> list[dict]:
        return self._store

    @property
    def active(self) -> list[dict]:
        return self._store[:self.active_capacity]

    @property
    def archive(self) -> list[dict]:
        return self._archive

    def process(self, lines: list[dict], now: float) -> dict[str, Any]:
        """Match lines against active patterns.

        Returns dict(explained=[(line, pattern_id)], unexplained=[line], messages=[str]).
        """
        explained = []
        unexplained = []
        messages = []
        delivered_this_batch = set()

        for line in lines:
            matched_pid = None
            for pat in self.active:
                if _pattern_matches(pat, line):
                    pid = pat["id"]
                    matched_pid = pid
                    pat["hits"] = pat.get("hits", 0) + 1
                    pat["last_hit"] = now

                    if pat.get("to_noob"):
                        cooldown = float(pat.get("cooldown_s", 0))
                        last_deliv = self._last_delivery.get(pid)
                        if pid not in delivered_this_batch:
                            if last_deliv is None or (now - last_deliv >= cooldown):
                                messages.append(pat["message"])
                                self._last_delivery[pid] = now
                                delivered_this_batch.add(pid)
                    break

            if matched_pid is not None:
                explained.append((line, matched_pid))
            else:
                unexplained.append(line)

        # Re-sort store by hits descending
        self._store.sort(key=lambda p: p.get("hits", 0), reverse=True)

        return {
            "explained": explained,
            "unexplained": unexplained,
            "messages": messages,
        }
