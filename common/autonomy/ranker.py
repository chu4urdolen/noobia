"""Structured pattern store and ranker (ARCHITECTURE.md §4).

Deliverable A, task E4. Review fixes R1-R5 applied.

Used only for PRIORITY chunks. Explains lines using active structured patterns
compiled with exact literal matches and validated against examples.
Unexplained lines are routed to Aigel.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any

try:
    from .sense import parse_line
except (ImportError, ValueError):
    from sense import parse_line

BACKREF_RE = re.compile(r"\\[1-9]|\(\?P=[a-zA-Z0-9_]+\)")
# Catches nested quantifiers including {n,}, e.g. (a+)+, (a+){2,}
NESTED_QUANT_RE = re.compile(r"\([^)]*[\*\+\?][^)]*\)(?:[\*\+\?]|\{[0-9,]+\})")


def _pattern_matches(pattern: dict, line: dict) -> bool:
    """Check if pattern matches parsed line dictionary."""
    match = pattern.get("match", {})
    # R1: sense and event must match
    if match.get("sense") != line.get("sense"):
        return False
    if match.get("event") != line.get("event"):
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


# --------------------------------------------------------------------------
# Templated messages (Tom, 2026-11-22)
#
# A pattern may carry a ``template`` instead of a fixed ``message`` text.
# Placeholders are filled from what the line says:
#   {name}   a named group of the pattern's ``regex``, or a key=value field
#   {name*}  every value the ``each`` item-regex captured for group ``name``,
#            de-duplicated in order and joined with ", " (or each["join"])
#
# ``each`` handles "an unknown number of things" without the dangerous
# nested quantifier ``((\w+)\(...\)/?)+`` (which Python could not capture
# repeatedly anyway: a repeated group keeps only its last match). Instead
# the item regex is applied in a bounded while() loop over one region:
#   "each": {"regex": "(?P<label>[a-z_]+)\\((?P<conf>[0-9.]+)\\)",
#            "group": "items"}        # optional: a named group of ``regex``;
#                                     # omitted -> the line's free text
#
# Line:     NOOBIA P1 camera objects.seen n=3 | laptop(0.7534)/person(0.873)/cat(0.45)
# Template: You see {label*}.
# Message:  You see laptop, person, cat.
# --------------------------------------------------------------------------
TEMPLATE_RE = re.compile(r"\{([a-z_][a-z0-9_]*)(\*?)\}")
MAX_EACH_ITEMS = 32
MAX_VALUE_CHARS = 220   # camera captions (Florence-2) are up to ~200 chars
MAX_MESSAGE_CHARS = 400


def _clean_value(value: str) -> str:
    """A captured value as safe, short, printable ASCII for a sentence."""
    text = "".join(ch for ch in str(value) if 32 <= ord(ch) < 127)
    return text.replace("_", " ").strip()[:MAX_VALUE_CHARS]


def extract_captures(pattern: dict, line: dict) -> tuple[dict[str, str], dict[str, list[str]]]:
    """Return (single values, repeated item lists) captured from one line."""
    values: dict[str, str] = {k: str(v) for k, v in (line.get("fields") or {}).items()}
    lists: dict[str, list[str]] = {}
    regex = pattern.get("regex")
    if regex:
        m = re.search(regex, line.get("raw", ""))
        if m:
            values.update({k: v for k, v in m.groupdict().items() if v is not None})
    each = pattern.get("each")
    if isinstance(each, dict) and each.get("regex"):
        group = each.get("group")
        region = values.get(group, "") if group else line.get("text", "")
        item_re = re.compile(each["regex"])
        pos, count = 0, 0
        while pos <= len(region) and count < MAX_EACH_ITEMS:
            im = item_re.search(region, pos)
            if im is None:
                break
            for k, v in im.groupdict().items():
                if v is not None:
                    lists.setdefault(k, []).append(v)
            # Always advance, even on an (invalid) zero-width match.
            pos = im.end() if im.end() > im.start() else im.end() + 1
            count += 1
    return values, lists


def render_message(pattern: dict, line: dict) -> str:
    """The sentence for a matched line: the filled template, or the fixed message.

    A template whose placeholders cannot all be filled falls back to the
    pattern's fixed ``message`` so a strange line never yields a broken
    sentence like "You see ."."""
    text, complete = fill_template(pattern, line)
    return text if complete else pattern.get("message", "")


def fill_template(pattern: dict, line: dict) -> tuple[str, bool]:
    """(filled template, every placeholder was filled). No template -> (message, True)."""
    template = pattern.get("template")
    if not template:
        return pattern.get("message", ""), True
    values, lists = extract_captures(pattern, line)
    joiner = (pattern.get("each") or {}).get("join", ", ")
    missing = False

    def fill(m: re.Match) -> str:
        nonlocal missing
        name, star = m.group(1), m.group(2)
        if star:
            seen: list[str] = []
            for v in lists.get(name, []):
                cv = _clean_value(v)
                if cv and cv not in seen:
                    seen.append(cv)
            if not seen:
                missing = True
                return ""
            return joiner.join(seen)
        if name in values and _clean_value(values[name]):
            return _clean_value(values[name])
        if lists.get(name):
            return _clean_value(lists[name][0])
        missing = True
        return ""

    text = TEMPLATE_RE.sub(fill, template)
    return text[:MAX_MESSAGE_CHARS], not missing


def _check_regex(regex: Any, what: str) -> re.Pattern:
    if not isinstance(regex, str):
        raise ValueError(f"{what} must be a string")
    if len(regex) > 200:
        raise ValueError(f"{what} exceeds 200 characters: {len(regex)}")
    if BACKREF_RE.search(regex):
        raise ValueError(f"back-references are not permitted in {what}: {regex}")
    if NESTED_QUANT_RE.search(regex):
        raise ValueError(f"nested quantifiers are not permitted in {what}: {regex}")
    try:
        return re.compile(regex)
    except re.error as e:
        raise ValueError(f"invalid {what}: {e}") from e


def validate_pattern(pattern: dict, corpus: list[str]) -> None:
    """Validate structured pattern and its regex/examples against corpus. Raises ValueError on failure."""
    if not isinstance(pattern, dict):
        raise ValueError("pattern must be a dictionary")

    for req in ("id", "match", "message", "to_noob", "cooldown_s", "examples", "hits", "origin"):
        if req not in pattern:
            raise ValueError(f"missing required pattern field: {req}")

    match = pattern.get("match")
    if not isinstance(match, dict):
        raise ValueError("pattern match must be a dictionary")

    # R1: Require non-empty sense and event in pattern match
    sense = match.get("sense")
    event = match.get("event")
    if not sense or not isinstance(sense, str) or not event or not isinstance(event, str):
        raise ValueError("pattern match must include non-empty 'sense' and 'event'")

    examples = pattern.get("examples")
    if not isinstance(examples, dict) or "must" not in examples or "must_not" not in examples:
        raise ValueError("examples must contain 'must' and 'must_not' lists")

    must = examples.get("must", [])
    must_not = examples.get("must_not", [])
    if not isinstance(must, list) or not isinstance(must_not, list):
        raise ValueError("must and must_not must be lists of strings")

    # R2: Require at least one must example
    if len(must) < 1:
        raise ValueError("pattern requires at least one 'must' example")

    regex = pattern.get("regex")
    if regex is not None:
        if not must_not:
            raise ValueError("advanced regex requires at least one must_not example")
        compiled = _check_regex(regex, "pattern regex")
        for c_line in corpus:
            if compiled.search(c_line):
                raise ValueError(f"regex matches baseline corpus line: {c_line}")

    each = pattern.get("each")
    if each is not None:
        if not isinstance(each, dict) or not each.get("regex"):
            raise ValueError("each must be an object with a 'regex'")
        item_re = _check_regex(each["regex"], "each regex")
        if item_re.search("") is not None:
            raise ValueError("each regex must not match the empty string")
        if not item_re.groupindex:
            raise ValueError("each regex needs at least one named group (?P<name>...)")
        group = each.get("group")
        if group is not None and (not regex or group not in re.compile(regex).groupindex):
            raise ValueError(f"each group '{group}' is not a named group of the pattern regex")

    template = pattern.get("template")
    if template is not None:
        if not isinstance(template, str) or not template.strip() or len(template) > 300:
            raise ValueError("template must be a non-empty string of at most 300 characters")
        # Every must example must fill the template completely.
        for line_str in must:
            parsed = parse_line(line_str)
            if parsed and not fill_template(pattern, parsed)[1]:
                raise ValueError(f"template could not be filled from 'must' example: {line_str}")

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
        corpus: list[str] = (),
    ):
        self.store_capacity = int(store_capacity)
        self.active_capacity = int(active_capacity)
        self.corpus = list(corpus)
        self._history: list[dict] = []

        valid_patterns = []
        invalid_patterns = []

        # R3: Validate patterns on load; invalid -> archive
        for p in patterns:
            try:
                validate_pattern(p, self.corpus)
                valid_patterns.append(p)
            except Exception:
                invalid_patterns.append(p)

        sorted_pats = sorted(valid_patterns, key=lambda p: p.get("hits", 0), reverse=True)
        self._store = sorted_pats[:self.store_capacity]
        self._archive = sorted_pats[self.store_capacity:] + invalid_patterns
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

    def add_pattern(
        self,
        pattern: dict,
        corpus: list[str] | None = None,
        origin: str = "aigel",
        revertible: bool = True,
    ) -> None:
        """Add new validated pattern, recording history for revertibility (R4)."""
        check_corpus = self.corpus if corpus is None else corpus
        validate_pattern(pattern, check_corpus)
        pattern["origin"] = origin

        # Record prior state if replacing existing ID
        existing = next((p for p in self._store if p.get("id") == pattern.get("id")), None)
        if revertible:
            self._history.append({"action": "add", "id": pattern["id"], "prev": existing})

        if existing:
            self._store.remove(existing)

        self._store.insert(0, pattern)
        if len(self._store) > self.store_capacity:
            overflow = self._store.pop()
            self._archive.append(overflow)

    def revert_pattern(self, pattern_id: str) -> bool:
        """Revert pattern to prior version from history (R4)."""
        for i in range(len(self._history) - 1, -1, -1):
            entry = self._history[i]
            if entry.get("id") == pattern_id:
                prev = entry.get("prev")
                # Remove current
                self._store = [p for p in self._store if p.get("id") != pattern_id]
                if prev:
                    self._store.insert(0, prev)
                del self._history[i]
                return True
        return False

    def save_patterns(self, path: Path | str) -> None:
        """Atomic persistence to JSON file (R4)."""
        target = Path(path)
        data = {
            "version": 1,
            "store_capacity": self.store_capacity,
            "active_capacity": self.active_capacity,
            "store": self._store,
            "archive": self._archive,
        }
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", dir=target.parent, delete=False, encoding="utf-8") as tf:
            json.dump(data, tf, indent=2, ensure_ascii=False)
            temp_name = tf.name
        os.replace(temp_name, target)

    @classmethod
    def load_patterns(cls, path: Path | str, corpus: list[str] = ()) -> Ranker:
        """Load patterns from atomic JSON file (R4)."""
        target = Path(path)
        if not target.exists():
            return cls([], corpus=corpus)
        with open(target, "r", encoding="utf-8") as f:
            data = json.load(f)
        pats = data.get("store", []) + data.get("archive", [])
        return cls(
            pats,
            store_capacity=data.get("store_capacity", 200),
            active_capacity=data.get("active_capacity", 100),
            corpus=corpus,
        )

    def is_ignored(self, line: dict) -> bool:
        """Return True if line matches any active ignore pattern."""
        for pat in self.active:
            if (pat.get("ignore") or pat.get("is_ignore")) and _pattern_matches(pat, line):
                return True
        return False

    def process(self, lines: list[dict], now: float) -> dict[str, Any]:
        """Match lines against active patterns."""
        explained = []
        unexplained = []
        messages = []
        deliveries = []  # (rendered text, pattern id), in delivery order
        delivered_this_batch = set()

        for line in lines:
            matched_pid = None
            for pat in self.active:
                if _pattern_matches(pat, line):
                    pid = pat["id"]
                    matched_pid = pid
                    pat["hits"] = pat.get("hits", 0) + 1
                    pat["last_hit"] = now

                    if not pat.get("ignore", False) and not pat.get("is_ignore", False):
                        if pat.get("to_noob"):
                            cooldown = float(pat.get("cooldown_s", 0))
                            last_deliv = self._last_delivery.get(pid)
                            if pid not in delivered_this_batch:
                                if last_deliv is None or (now - last_deliv >= cooldown):
                                    text = render_message(pat, line)
                                    messages.append(text)
                                    deliveries.append((text, pid))
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
            "deliveries": deliveries,
        }
