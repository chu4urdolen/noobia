"""The prioritizer for Noobia autonomy (ARCHITECTURE.md §2a).

Deliverable A, task E8.

Translates ordinary log messages from allowlisted sources into sense lines:
- Mapped lines receive configured priority Pn and sense/event.
- Unmapped lines from allowlisted sources become P0 raw line.
- Repeat collapse: identical (source, text) within repeat_window_s is emitted once.
- Loop guard: sources starting with 'noobia-' are strictly rejected.
- Rules are validated, versioned, atomic-persisted, and reversible.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any

try:
    from .sense import format_line, SENSE_NAME_RE, EVENT_NAME_RE
except (ImportError, ValueError):
    from sense import format_line, SENSE_NAME_RE, EVENT_NAME_RE

DEFAULT_RULES_CAPACITY = 200
DEFAULT_REPEAT_WINDOW_S = 60.0


class PrioritizerError(Exception):
    pass


def _rule_matches(rule: dict, source: str, text: str) -> bool:
    """Check if rule matches raw log line text from source."""
    if rule.get("source") != source:
        return False

    match = rule.get("match", {})
    text_contains = match.get("text_contains", [])
    if not isinstance(text_contains, list):
        return False

    for item in text_contains:
        if item not in text:
            return False

    return True


def validate_rule(rule: dict) -> None:
    """Validate a priority map rule against schema and examples."""
    if not isinstance(rule, dict):
        raise PrioritizerError("rule must be a dictionary")

    for req in ("id", "source", "match", "emit", "examples", "hits", "origin"):
        if req not in rule:
            raise PrioritizerError(f"missing required rule field: {req}")

    source = rule.get("source")
    if not isinstance(source, str) or not source.strip():
        raise PrioritizerError("source must be a non-empty string")
    if source.startswith("noobia-"):
        raise PrioritizerError(f"loop guard: source cannot start with 'noobia-': {source}")

    match = rule.get("match")
    if not isinstance(match, dict) or "text_contains" not in match:
        raise PrioritizerError("match must be a dict containing 'text_contains' list")
    text_contains = match.get("text_contains")
    if not isinstance(text_contains, list) or not text_contains:
        raise PrioritizerError("text_contains must be a non-empty list of strings")

    emit = rule.get("emit")
    if not isinstance(emit, dict):
        raise PrioritizerError("emit must be a dictionary")
    p = emit.get("p")
    if not isinstance(p, int) or isinstance(p, bool) or not (0 <= p <= 99):
        raise PrioritizerError(f"emit priority must be 0..99, got {p!r}")
    sense = emit.get("sense")
    if not isinstance(sense, str) or not SENSE_NAME_RE.match(sense):
        raise PrioritizerError(f"emit sense must match ^[a-z0-9_]{{1,24}}$, got {sense!r}")
    event = emit.get("event")
    if not isinstance(event, str) or not EVENT_NAME_RE.match(event):
        raise PrioritizerError(f"emit event must match ^[a-z0-9_.]{{1,48}}$, got {event!r}")

    examples = rule.get("examples")
    if not isinstance(examples, dict) or "must" not in examples or "must_not" not in examples:
        raise PrioritizerError("examples must contain 'must' and 'must_not' lists")

    must = examples.get("must")
    must_not = examples.get("must_not")
    if not isinstance(must, list) or not must:
        raise PrioritizerError("examples['must'] requires at least one example string")
    if not isinstance(must_not, list) or not must_not:
        raise PrioritizerError("examples['must_not'] requires at least one example string")

    # Verify against examples
    for line in must:
        if not _rule_matches(rule, source, line):
            raise PrioritizerError(f"rule {rule['id']} failed to match 'must' example: {line}")

    for line in must_not:
        if _rule_matches(rule, source, line):
            raise PrioritizerError(f"rule {rule['id']} erroneously matched 'must_not' example: {line}")


class Prioritizer:
    def __init__(
        self,
        rules: list[dict] | None = None,
        allowlist: set[str] | list[str] | None = None,
        rules_capacity: int = DEFAULT_RULES_CAPACITY,
        repeat_window_s: float = DEFAULT_REPEAT_WINDOW_S,
    ):
        self.rules_capacity = int(rules_capacity)
        self.repeat_window_s = float(repeat_window_s)
        self.allowlist = set(allowlist) if allowlist else {"wpa_supplicant", "kernel", "lynx-bluetoothd"}

        # Validate incoming rules
        self._rules: list[dict] = []
        if rules:
            for r in rules:
                try:
                    validate_rule(r)
                    self._rules.append(r)
                except Exception:
                    pass

        self._history: list[dict] = []
        self._recent_lines: dict[tuple[str, str], float] = {}

    @property
    def rules(self) -> list[dict]:
        return list(self._rules)

    def add_rule(self, rule: dict, origin: str = "aigel", revertible: bool = True) -> None:
        """Validate, add or update a rule with history tracking."""
        validate_rule(rule)
        rule["origin"] = origin
        rule_id = rule["id"]

        existing = next((r for r in self._rules if r.get("id") == rule_id), None)
        if revertible:
            self._history.append({"id": rule_id, "prev": existing})

        if existing:
            self._rules.remove(existing)

        self._rules.insert(0, rule)
        if len(self._rules) > self.rules_capacity:
            self._rules.pop()

    def revert_rule(self, rule_id: str) -> bool:
        """Revert rule to previous version from history."""
        for i in range(len(self._history) - 1, -1, -1):
            entry = self._history[i]
            if entry.get("id") == rule_id:
                prev = entry.get("prev")
                self._rules = [r for r in self._rules if r.get("id") != rule_id]
                if prev:
                    self._rules.insert(0, prev)
                del self._history[i]
                return True
        return False

    def process_line(self, source: str, text: str, now: float) -> str | None:
        """Process one raw log line into a formatted sense line, or None if filtered."""
        # Loop guard: reject any source starting with noobia-
        if not source or source.startswith("noobia-"):
            return None

        # Allowlist filter
        if source not in self.allowlist:
            return None

        # Repeat collapse
        key = (source, text)
        last_seen = self._recent_lines.get(key)
        if last_seen is not None and now - last_seen < self.repeat_window_s:
            return None
        self._recent_lines[key] = now

        # Prune old repeat cache entries
        if len(self._recent_lines) > 500:
            self._recent_lines = {k: v for k, v in self._recent_lines.items() if now - v < self.repeat_window_s}

        # Apply matching rules
        for r in self._rules:
            if _rule_matches(r, source, text):
                r["hits"] = r.get("hits", 0) + 1
                emit_spec = r["emit"]
                return format_line(
                    p=emit_spec["p"],
                    sense=emit_spec["sense"],
                    event=emit_spec["event"],
                    fields={"src": source, "rule": r["id"]},
                    text=text,
                )

        # Unmapped line from allowlisted source -> P0 raw line
        return format_line(
            p=0,
            sense="raw",
            event="line",
            fields={"src": source},
            text=text,
        )

    def save_map(self, path: Path | str) -> None:
        """Save rules atomically to JSON file."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": 1,
            "rules": self._rules,
        }
        with tempfile.NamedTemporaryFile("w", dir=target.parent, delete=False, encoding="utf-8") as tf:
            json.dump(data, tf, indent=2, ensure_ascii=False)
            temp_name = tf.name
        os.replace(temp_name, target)

    @classmethod
    def load_map(cls, path: Path | str, allowlist: set[str] | None = None) -> Prioritizer:
        """Load prioritizer from JSON map file."""
        target = Path(path)
        if not target.exists():
            return cls([], allowlist=allowlist)
        with open(target, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(data.get("rules", []), allowlist=allowlist)
