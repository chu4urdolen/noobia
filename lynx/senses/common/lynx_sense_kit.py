#!/usr/bin/env python3
"""A tiny frame for Lynx's newer senses (Gwyn, 2026-11-25, Rose's backlog).

A sense is two pure functions:

    observe() -> dict                       read the world (bounded, read-only)
    detect(prev, obs, now) -> (events, state)

``events`` is a list of ``Event(event, fields, text, cooldown_s=0)``. The kit
loads the previous state, applies per-event cooldowns, emits canonical lines
(``lynx_senses_lib.emit_line``), saves the new state, and returns the usual
one-shot result. Conventions are the senses README's: the first sample only
baselines (``prev`` is ``{}``), a read failure emits nothing, ``--dry-run``
writes nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lynx_senses_lib import (  # noqa: E402
    SenseUnavailable,
    base_result,
    emit_line,
    failure,
    import_sense,
    load_state,
    save_state,
    state_path,
)

JOURNAL = Path("/var/log/lynx/security.jsonl")


@dataclass
class Event:
    event: str
    fields: dict = field(default_factory=dict)
    text: str = ""
    cooldown_s: float = 0.0
    priority: int = 3          # the event's meaning; Lynx emits every line at P20 anyway
    journal: bool = False      # security events also go to the incident journal (LNX-74)
    key: str = ""              # cooldown key; defaults to the event name


def journal(event: Event, sense: str, now: float, path: Path | None = None) -> None:
    """Append one security incident to Banshee's journal (LNX-74). Never raises."""
    path = path or JOURNAL
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {"t": round(now, 3), "sense": sense, "event": event.event,
                  "fields": event.fields, "text": event.text[:300],
                  "note": "observation, not proof of an attack"}
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True) + "\n")
    except OSError:
        pass


def run_sense(name: str, observe, detect, dry_run: bool = False,
              state_file: str | None = None, now: float | None = None,
              sense_mod=None, journal_path: Path | None = None,
              state_name: str | None = None) -> tuple[dict, int]:
    """NAME is the sense on the line; STATE_NAME (default NAME) names its state
    directory, so two modules can share a line name (security) without sharing state."""
    now = float(now if now is not None else time.time())
    try:
        sense = sense_mod or import_sense()
    except SenseUnavailable as exc:
        return failure(name, exc)
    try:
        obs = observe()
    except Exception as exc:  # noqa: BLE001 - a read failure emits nothing
        return failure(name, exc)
    path = state_path(state_name or name, state_file)
    prev = load_state(path)
    cool = dict(prev.get("_cooldown", {}))
    try:
        events, state = detect({k: v for k, v in prev.items() if k != "_cooldown"}, obs, now)
    except Exception as exc:  # noqa: BLE001
        return failure(name, exc)
    emitted = []
    for ev in events:
        key = ev.key or ev.event
        if ev.cooldown_s and key in cool and now - float(cool[key]) < ev.cooldown_s:
            continue
        line = emit_line(sense, ev.priority, name, ev.event, fields=ev.fields,
                         text=ev.text, dry_run=dry_run)
        emitted.append(line)
        if ev.cooldown_s:
            cool[key] = now
        if ev.journal and not dry_run:
            journal(ev, name, now, journal_path)
    state = dict(state)
    state["_cooldown"] = {k: v for k, v in cool.items() if now - float(v) < 86400}
    if not dry_run:
        save_state(path, state)
    result = base_result(state_name or name, emitted=emitted, dry_run=dry_run)
    return result, 0


def band(value, levels, previous=None, hysteresis=0.0):
    """Name the band VALUE falls in. LEVELS is [(name, upper_bound), ...] in rising
    order, the last bound may be None. With HYSTERESIS, stay in PREVIOUS while the
    value is within that margin of its edge, so a value sitting on a line does not
    flap between two bands."""
    names = [n for n, _ in levels]
    bounds = [b for _, b in levels]

    def plain(v):
        for n, b in levels:
            if b is None or v <= b:
                return n
        return names[-1]

    cur = plain(value)
    if previous in names and cur != previous and hysteresis:
        i = names.index(previous)
        lo = bounds[i - 1] if i > 0 else None
        hi = bounds[i]
        if (lo is None or value > lo - hysteresis) and (hi is None or value <= hi + hysteresis):
            return previous
    return cur
