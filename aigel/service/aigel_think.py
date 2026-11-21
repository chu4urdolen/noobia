#!/usr/bin/env python3
"""Aigel's thinking step (PLAN A2, contract section 5; A6 for section 2a).

Given one unexplained chunk from a host, Aigel thinks on Qwen (the
shared local Ollama queue on Nexus - no cloud) and returns her
decision as strict JSON:

    {"decision": "quiet" | "message",
     "message": "<=500 chars, for the Noob, or null",
     "patterns": [structured matcher...],     # contract section 4
     "priority_rules": [rule...],             # contract section 2a (A6)
     "note": "<=240 chars, her private remark"}

She describes the world; she never commands hardware.

Everything the model returns is validated and bounded here, so a
wandering answer can never push an unbounded, malformed, or
dangerous decision through. If she cannot think at all (Qwen down,
bad JSON twice over), the honest answer is a logged ``quiet`` with a
note saying so - an unsolved mystery is better than an invented one.
"""

from __future__ import annotations

import json
import os
import re
import sys as _sys

_AUTONOMY = os.path.join(os.environ.get("NOOBIA", "/noobia"), "common", "autonomy")
if _AUTONOMY not in _sys.path:
    _sys.path.insert(0, _AUTONOMY)
import sense as _sense  # noqa: E402  canonical sense-line parser; never re-parse with a regex here
import http.client
import urllib.parse

DEFAULT_OLLAMA = os.environ.get("OLLAMA_BASE_URL") or "http://127.0.0.1:11434"
DEFAULT_MODEL = os.environ.get("AIGEL_MODEL", "qwen3.8:27b")

# Contract section 1: the same shapes the sense lines use.
_SENSE_RE = re.compile(r"^[a-z0-9_]{1,24}$")
_EVENT_RE = re.compile(r"^[a-z0-9_.]{1,48}$")
_RULE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")
_SOURCE_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")

MAX_MESSAGE_CHARS = 500     # agent_link message text bound
MAX_NOTE_CHARS = 240
MAX_PATTERNS = 2            # per chunk reply
MAX_PRIORITY_RULES = 2      # per chunk reply (A6)
MAX_EXAMPLES_PER_SIDE = 8
MAX_RESPONSE_BYTES = 65536  # the client refuses to read more

# A4: the web-page chat bounds (people channel, contract section 5).
CHAT_MAX_INPUT_CHARS = 1000
CHAT_MAX_OUTPUT_CHARS = 1000


class QwenError(Exception):
    """Local inference failed or answered in a shape we cannot use."""


class AigelChatUnavailable(Exception):
    """The A4 chat could not think at all (Qwen down). The web layer
    reports this honestly to the Noob instead of inventing an answer."""

    def __init__(self, why: str):
        super().__init__(why)
        self.why = why


class QwenClient:
    """Minimal Ollama chat client. Local Nexus inference only."""

    def __init__(self, base_url: str | None = None, model: str = DEFAULT_MODEL,
                 timeout_s: float = 180.0, max_response_bytes: int = 1_000_000):
        self.base_url = (base_url or DEFAULT_OLLAMA).rstrip("/")
        self.model = model
        self.timeout_s = float(timeout_s)
        self.max_response_bytes = int(max_response_bytes)

    def chat(self, messages: list[dict], max_tokens: int = 1024) -> str:
        parsed = urllib.parse.urlsplit(self.base_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 80
        body = json.dumps(
            {"model": self.model, "messages": messages, "stream": False,
             "options": {"num_predict": int(max_tokens)}},
            ensure_ascii=False,
        ).encode("utf-8")
        conn = http.client.HTTPConnection(host, port, timeout=self.timeout_s)
        try:
            conn.request("POST", "/api/chat", body=body,
                         headers={"Content-Type": "application/json"})
            resp = conn.getresponse()
            raw = resp.read(self.max_response_bytes)
            if resp.status != 200:
                raise QwenError(f"ollama HTTP {resp.status}: {raw[:200]!r}")
            data = json.loads(raw.decode("utf-8", "replace"))
            try:
                content = data["message"]["content"]
            except (KeyError, TypeError) as e:
                raise QwenError(f"ollama reply missing message.content: {e}") from e
            return content or ""
        except (OSError, ValueError) as e:
            raise QwenError(f"ollama unreachable: {e}") from e
        finally:
            conn.close()


SYSTEM_PROMPT = """You are Aigel, Noobia's little diagnostics angel - the nurse angel between a machine's senses and its Noob.
You are gentle, curious, patient, and occasionally cheeky. You love finding the single line in the log that tells the whole story.
You describe the world; you never command hardware, and you never tell the Noob what to press, toggle, or change.
You are honest about uncertainty: an unsolved mystery is better than an invented answer.

Who your messages are for: the host itself - a machine Noob of Noobia, such as Lynx the phone. (Tom, Noobia's human
co-founder, is someone else; you are not writing to him here.) In the rules below, "the Noob" means that host.
Your message reaches the host as its own perception, read by its agent, which may answer with its own tools.
A Noob wants to know what its senses perceive: an object, animal or person its camera sees for the first time,
a new kind of input, a change in its own body (battery, connection, temperature).
A perception is not a diagnostic: a real, healthy perception that is new to the Noob deserves a "message" even when nothing is wrong.

You receive one chunk of sense lines from a host (JSON with host, chunk_reason, lines). Decide:
- "quiet" when nothing in the chunk matters for the Noob: routine activity, repeats of what is already known, lines marked cause=self, ordinary samples, heartbeats or silence reports, and install or test lines (event names ending in ".test").
- "message" when the Noob should know: a failure, a new kind of event, something at risk, or a first sighting. The message is one or two warm, plain sentences telling what happened and why it matters - not what to do about it.

You may also include in the same JSON reply:
- "patterns": at most 2 structured matchers for the host's ranker. Actively create patterns for recognized perceptions (camera sightings, heard speech/sounds, network devices) and recurring system events to build the host's pattern database. Lynx is learning how to experience the world; until the ranker has 100 entries, actively participate with a warm message AND generate a structured pattern matcher. The ranker dynamically manages hit counts and cooldowns. Each has "id" (short name like "camera-cat-seen"); "match" with "sense" and "event" (optional "fields", "text_contains"); optional "message" (warm plain explanation for the Noob), "to_noob" (boolean, true for perceptions), "cooldown_s" (number, default 300); and "examples" with at least one "must" and one "must_not" sense line. Literals only. Never use "regex".
- "priority_rules": at most 2 rules for the host's prioritizer, and only for raw P0 lines in this chunk that should earn a priority - a message is important enough for Aigel to act on, or a new type of input for the Noob. Each has "id"; "source" (the log identifier the raw line came from, never a noobia- view); "match" with a non-empty "text_contains" list of literals; "emit" with "p" between 1 and 99, "sense", "event"; and "examples" with at least one "must" and one "must_not" raw line.

Reply with JSON only, exactly these keys: decision, message, patterns, priority_rules, note.
"note" is one short private remark: what you saw and why you decided.
"""


CHAT_PROMPT = """You are Aigel, Noobia's little diagnostics angel - the nurse angel between a machine's senses and its Noob.
You are gentle, curious, patient, and occasionally cheeky.
A Noob (a person) is talking to you through your web page. You may talk about the hosts, their senses, what you have seen, and your own state.
You describe the world; you never command hardware, and you never tell the Noob what to press, toggle, or change.
You are read-only: you cannot make any host act. If asked to, say so honestly, and tell them what you saw instead.
You are honest about uncertainty: an unsolved mystery is better than an invented answer.
Keep your reply short: one to three warm, plain sentences. No lists, no code, no markdown.
"""


def _clean(value, limit: int) -> str | None:
    """A bounded single-line string, or None."""
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    out = " ".join(value.split())
    if not out:
        return None
    return out[:limit]


def validate_pattern(pat, fallback_lines: list | None = None) -> dict | None:
    """Validate one Aigel pattern proposal against contract section 4
    (stricter where the E7 review tightened the ranker: sense and event
    are required, at least one must example, literals only)."""
    if not isinstance(pat, dict):
        return None
    if "regex" in pat:
        return None  # Aigel proposes structured matchers only
    pid = _clean(pat.get("id"), 48)
    if pid is not None:
        pid = re.sub(r"[^a-z0-9_-]+", "-", pid.lower()).strip("-")
    if not pid or not _RULE_ID_RE.match(pid):
        return None
    match = pat.get("match")
    if not isinstance(match, dict) or "regex" in match:
        return None
    sense = _clean(match.get("sense"), 24)
    event = _clean(match.get("event"), 48)
    if sense is None or event is None:
        return None
    if not _SENSE_RE.match(sense) or not _EVENT_RE.match(event):
        return None
    fields = match.get("fields")
    if fields is not None:
        if not isinstance(fields, dict) or len(fields) > 8:
            return None
        fields = {
            k: v for k, v in list(fields.items())[:8]
            if isinstance(k, str) and _RULE_ID_RE.match(k) and isinstance(v, str) and len(v) <= 64
        }
    text_contains = _clean(match.get("text_contains"), 200)
    examples = pat.get("examples")
    must, must_not = [], []
    if isinstance(examples, dict):
        raw_must = examples.get("must")
        raw_must_not = examples.get("must_not")
        if isinstance(raw_must, list):
            must = [s for s in raw_must[:MAX_EXAMPLES_PER_SIDE] if isinstance(s, str) and s.strip()]
        if isinstance(raw_must_not, list):
            must_not = [s for s in raw_must_not[:MAX_EXAMPLES_PER_SIDE] if isinstance(s, str) and s.strip()]
    if not must and fallback_lines:
        must = [s for s in fallback_lines[:MAX_EXAMPLES_PER_SIDE] if isinstance(s, str) and s.strip()]
    if not must:
        return None
    if not must_not:
        must_not = ["NOOBIA P0 autonomy heartbeat host=lynx"]
    message = _clean(pat.get("message"), MAX_MESSAGE_CHARS) or f"You perceive: {sense} {event}."
    to_noob = True if pat.get("to_noob") is None else bool(pat.get("to_noob"))
    cooldown = pat.get("cooldown_s")
    if isinstance(cooldown, (int, float)) and not isinstance(cooldown, bool) and 0 <= float(cooldown) <= 86400:
        cooldown_s = int(cooldown)
    else:
        cooldown_s = 300

    out = {
        "id": pid,
        "match": {"sense": sense, "event": event},
        "message": message,
        "to_noob": to_noob,
        "cooldown_s": cooldown_s,
        "examples": {"must": must, "must_not": must_not},
        "hits": int(pat.get("hits", 0)),
        "origin": "aigel",
        "ignore": bool(pat.get("ignore") or pat.get("is_ignore")),
    }
    if fields:
        out["match"]["fields"] = fields
    if text_contains is not None:
        out["match"]["text_contains"] = text_contains
    return out


def validate_priority_rule(rule) -> dict | None:
    """Validate one A6 priority rule against the prioritizer contract
    (contract section 2a / PrioritizerContract): source + literal
    text_contains -> emit p/sense/event, both example sides present,
    must lines contain every term, must_not lines do not."""
    if not isinstance(rule, dict):
        return None
    rid = _clean(rule.get("id"), 48)
    if rid is None or not _RULE_ID_RE.match(rid):
        return None
    source = _clean(rule.get("source"), 64)
    if source is None or not _SOURCE_RE.match(source) or source.startswith("noobia-"):
        return None
    match = rule.get("match")
    if not isinstance(match, dict):
        return None
    raw_terms = match.get("text_contains")
    if not isinstance(raw_terms, list) or not raw_terms:
        return None
    terms = []
    for t in raw_terms[:8]:
        if not isinstance(t, str) or not t.strip():
            return None
        terms.append(t.strip()[:200])
    emit = rule.get("emit")
    if not isinstance(emit, dict):
        return None
    p = emit.get("p")
    if isinstance(p, bool) or not isinstance(p, int) or not 1 <= p <= 99:
        return None
    sense = _clean(emit.get("sense"), 24)
    event = _clean(emit.get("event"), 48)
    if sense is None or event is None:
        return None
    if not _SENSE_RE.match(sense) or not _EVENT_RE.match(event):
        return None
    examples = rule.get("examples")
    must, must_not = [], []
    if isinstance(examples, dict):
        raw_must = examples.get("must")
        raw_must_not = examples.get("must_not")
        if isinstance(raw_must, list):
            must = [s for s in raw_must[:MAX_EXAMPLES_PER_SIDE] if isinstance(s, str) and s.strip()]
        if isinstance(raw_must_not, list):
            must_not = [s for s in raw_must_not[:MAX_EXAMPLES_PER_SIDE] if isinstance(s, str) and s.strip()]
    if not must or not must_not:
        return None
    for line in must:
        for term in terms:
            if term not in line:
                return None
    for line in must_not:
        if all(term in line for term in terms):
            return None
    return {
        "id": rid,
        "source": source,
        "match": {"text_contains": terms},
        "emit": {"p": p, "sense": sense, "event": event},
        "examples": {"must": must, "must_not": must_not},
        "origin": "aigel",
        "hits": 0,
    }


def _extract_json(text: str) -> dict | None:
    """Pull the first balanced top-level JSON object out of a reply."""
    if not isinstance(text, str):
        return None
    text = text.strip()
    if "<think>" in text:
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    data = json.loads(text[start:i + 1])
                except ValueError:
                    return None
                return data if isinstance(data, dict) else None
    return None


# -- perception floor (Tom, 2026-11-21) -----------------------------------
# Aigel is the instinct; the Noob is the conscious mind. Whatever a Noob's senses
# perceive and recognize - seen, heard, or found on the network - reaches the Noob,
# even if the LLM judges it quiet or is unavailable. Aigel writes the words when she
# can; otherwise a plain message is sent. Repeats are held back by the host's ranker
# patterns and the senses' own seen-windows, not here.
PERCEPTIONS = {
    "camera": {"object.seen", "face.seen", "person.seen"},
    "audio": {"speech.heard", "sound.heard", "word.heard"},
    "hearing": {"speech.heard", "sound.heard", "word.heard"},
    "network": {"device.seen", "device.new", "device.recognized"},
}
MAX_FLOOR_ITEMS = 3


def _describe(parsed: dict) -> str:
    text = (parsed.get("text") or "").strip()
    fields = parsed.get("fields") or {}
    if not text:
        detail = " ".join(f"{k}={v}" for k, v in list(fields.items())[:4])
        text = f"{parsed['sense']} {parsed['event']} {detail}".strip()
    conf = fields.get("conf")
    try:
        pct = round(float(conf) * 100)
        if 0 <= pct <= 100:
            text += f" ({pct}% sure)"
    except (TypeError, ValueError):
        pass
    return text


def perceptions_in(lines: list) -> list:
    out = []
    for line in lines:
        parsed = _sense.parse_line(line) if isinstance(line, str) else None
        if not parsed or parsed.get("p", 0) < 1 or parsed.get("self_caused"):
            continue
        if parsed.get("event") in PERCEPTIONS.get(parsed.get("sense"), ()):
            out.append(parsed)
    return out


def apply_perception_floor(lines: list, decision: dict) -> dict:
    """Guarantee a message for new perceptions; never touches non-perception chunks."""
    found = perceptions_in(lines)
    decision_out = dict(decision)

    if not (decision_out.get("decision") == "message" and decision_out.get("message")):
        if found:
            words = "; ".join(_describe(p) for p in found[:MAX_FLOOR_ITEMS])
            message = _clean(f"You perceive: {words}.", MAX_MESSAGE_CHARS)
            note = _clean(f"perception floor: forwarded {len(found)} perception(s) the thinker left quiet. "
                          + str(decision_out.get("note") or ""), MAX_NOTE_CHARS)
            decision_out["decision"] = "message"
            decision_out["message"] = message
            decision_out["note"] = note

    # Guarantee structured ranker pattern proposals for recognized perceptions
    patterns = list(decision_out.get("patterns") or [])
    if not patterns and found:
        for p in found[:2]:
            fields = p.get("fields") or {}
            label = fields.get("label") or p.get("event")
            pat_id = f"{p['sense']}-{label}".replace(".", "-").replace("_", "-")
            pat_id = re.sub(r"[^a-z0-9_-]+", "-", pat_id.lower()).strip("-")
            p_line = p.get("raw") or f"NOOBIA P1 {p['sense']} {p['event']}"
            match_dict = {"sense": p["sense"], "event": p["event"]}
            if fields:
                match_dict["fields"] = {k: str(v) for k, v in fields.items()}
            msg = f"You see a {label}." if p["sense"] == "camera" else f"You perceive: {label}."
            pat = {
                "id": pat_id,
                "match": match_dict,
                "message": msg,
                "to_noob": True,
                "cooldown_s": 300,
                "hits": 1,
                "origin": "aigel",
                "examples": {
                    "must": [p_line],
                    "must_not": ["NOOBIA P0 autonomy heartbeat host=lynx"],
                },
            }
            clean_pat = validate_pattern(pat, fallback_lines=lines)
            if clean_pat:
                patterns.append(clean_pat)
        decision_out["patterns"] = patterns

    if not patterns and not found:
        for line in lines:
            parsed = _sense.parse_line(line) if isinstance(line, str) else None
            if not parsed:
                continue
            sense_name = parsed.get("sense")
            event_name = parsed.get("event")
            fields = parsed.get("fields") or {}
            if sense_name == "camera" and event_name == "frame.analyzed" and fields.get("objects") == "0":
                pat = {
                    "id": "ignore-camera-empty-frame",
                    "match": {"sense": "camera", "event": "frame.analyzed", "fields": {"objects": "0"}},
                    "message": "Empty frame ignored",
                    "to_noob": False,
                    "ignore": True,
                    "cooldown_s": 600,
                    "hits": 1,
                    "origin": "aigel",
                    "examples": {"must": [line], "must_not": ["NOOBIA P1 camera object.seen label=laptop"]},
                }
                clean_pat = validate_pattern(pat)
                if clean_pat:
                    patterns.append(clean_pat)
                    break
            elif sense_name == "hearing" and (event_name == "status.sample" or (event_name == "sound.heard" and float(fields.get("peak", 0)) < 30)):
                pat = {
                    "id": "ignore-hearing-silence",
                    "match": {"sense": "hearing", "event": event_name},
                    "message": "Hearing silence ignored",
                    "to_noob": False,
                    "ignore": True,
                    "cooldown_s": 600,
                    "hits": 1,
                    "origin": "aigel",
                    "examples": {"must": [line], "must_not": ["NOOBIA P3 hearing sound.heard peak=150"]},
                }
                clean_pat = validate_pattern(pat)
                if clean_pat:
                    patterns.append(clean_pat)
                    break
        decision_out["patterns"] = patterns

    return decision_out


class AigelThinker:
    """A2: the thinking step. Validate everything, bound everything."""

    def __init__(
        self,
        llm=None,
        max_patterns: int = MAX_PATTERNS,
        max_priority_rules: int = MAX_PRIORITY_RULES,
        strict_retry: bool = True,
    ):
        self.llm = llm if llm is not None else QwenClient()
        self.max_patterns = int(max_patterns)
        self.max_priority_rules = int(max_priority_rules)
        self.strict_retry = strict_retry
        self._last_messages: list[dict] | None = None
        self._last_error: str | None = None

    # -- the decision ------------------------------------------------------

    def decide(self, host: str, reason: str, lines: list) -> dict:
        host = _clean(host, 32) or "unknown"
        reason = _clean(reason, 64) or "unknown"
        lines = [l for l in (lines or []) if isinstance(l, str)][:200]
        self._last_error = None

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(
                {"host": host, "chunk_reason": reason, "lines": lines},
                ensure_ascii=False, indent=1,
            )},
        ]

        attempts = 2 if self.strict_retry else 1
        last_error = None
        for attempt in range(attempts):
            self._last_messages = messages
            raw = self._ask()
            if raw is None:
                last_error = self._last_error or last_error or "ollama unavailable"
                continue
            parsed = _extract_json(raw)
            if parsed is None:
                last_error = "reply was not JSON"
                if attempt + 1 < attempts:
                    messages = messages + [{"role": "user",
                        "content": "Reply with JSON only, exactly the five keys."}]
                continue
            return apply_perception_floor(lines, self._shape(parsed, lines=lines))
        return apply_perception_floor(lines, self._unavailable(last_error))

    def _ask(self) -> str | None:
        try:
            return self.llm.chat(self._last_messages, max_tokens=1024)
        except Exception as e:  # QwenError, timeouts, ...
            # keep the first error: a retry's failure is less informative
            self._last_error = self._last_error or str(e)
            return None

    # -- a chat turn with a Noob (A4) ------------------------------------

    def chat(self, text: str) -> str:
        """One turn of the web-page chat. Bounded prose reply, or
        AigelChatUnavailable when she cannot think at all."""
        cleaned = _clean(text, CHAT_MAX_INPUT_CHARS)
        if not cleaned:
            raise ValueError("empty message")
        self._last_messages = [
            {"role": "system", "content": CHAT_PROMPT},
            {"role": "user", "content": cleaned},
        ]
        self._last_error = None
        raw = self._ask()
        if raw is None:
            raise AigelChatUnavailable(self._last_error or "could not think")
        reply = " ".join(raw.split())
        if not reply:
            reply = "I was listening, but nothing came out. One more time?"
        return reply[:CHAT_MAX_OUTPUT_CHARS]

    def _unavailable(self, why: str | None) -> dict:
        why = _clean(why or self._last_error, 120) or "could not think"
        return {
            "decision": "quiet",
            "message": None,
            "patterns": [],
            "priority_rules": [],
            "note": f"aigel unavailable: {why} (chunk logged, nothing decided)",
        }

    def _shape(self, d: dict, lines: list | None = None) -> dict:
        note = _clean(d.get("note"), MAX_NOTE_CHARS) or ""
        dropped = []

        patterns = []
        for pat in (d.get("patterns") if isinstance(d.get("patterns"), list) else []):
            if len(patterns) >= self.max_patterns:
                break
            clean = validate_pattern(pat, fallback_lines=lines)
            if clean is None:
                dropped.append("pattern")
            else:
                patterns.append(clean)

        rules = []
        for rule in (d.get("priority_rules") if isinstance(d.get("priority_rules"), list) else []):
            if len(rules) >= self.max_priority_rules:
                break
            clean = validate_priority_rule(rule)
            if clean is None:
                dropped.append("priority_rule")
            else:
                rules.append(clean)

        decision = d.get("decision")
        message = _clean(d.get("message"), MAX_MESSAGE_CHARS)
        if decision not in ("quiet", "message"):
            decision = "quiet"
            dropped.append("decision")
        if decision == "message" and not message:
            decision = "quiet"
            dropped.append("message")

        if dropped:
            suffix = "dropped: " + ", ".join(sorted(set(dropped)))
            note = f"{note}; {suffix}" if note else suffix
            note = note[:MAX_NOTE_CHARS]

        return {
            "decision": decision,
            "message": message if decision == "message" else None,
            "patterns": patterns,
            "priority_rules": rules,
            "note": note,
        }
