"""Universal Sense Kit execution frame (NA-83)."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from common.autonomy.sensekit.state import (
    clean_field,
    clean_text,
    load_state,
    save_state,
    state_path,
)

DEFAULT_JOURNAL = Path("/var/log/noobia/security.jsonl")


@dataclass
class Event:
    event: str
    fields: Dict[str, Any] = field(default_factory=dict)
    text: str = ""
    cooldown_s: float = 0.0
    priority: int = 3
    journal: bool = False
    key: str = ""


class Sense:
    """Base class for autonomous Noob senses."""

    name: str = "generic_sense"
    state_name: Optional[str] = None

    def observe(self) -> Dict[str, Any]:
        """Pure read of device or system metrics."""
        raise NotImplementedError

    def detect(
        self, prev: Dict[str, Any], obs: Dict[str, Any], now: float
    ) -> Tuple[List[Event], Dict[str, Any]]:
        """Pure transition/threshold detector."""
        raise NotImplementedError

    def run(
        self,
        dry_run: bool = False,
        state_file: Optional[str] = None,
        now: Optional[float] = None,
        sense_mod: Any = None,
        journal_path: Optional[Path] = None,
    ) -> Tuple[Dict[str, Any], int]:
        return run_sense(
            self.name,
            self.observe,
            self.detect,
            dry_run=dry_run,
            state_file=state_file,
            now=now,
            sense_mod=sense_mod,
            journal_path=journal_path,
            state_name=self.state_name,
        )


def journal(
    event: Event,
    sense: str,
    now: float,
    path: Optional[Path] = None,
) -> None:
    """Append one security incident to the host's journal."""
    target = path or DEFAULT_JOURNAL
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "t": round(now, 3),
            "sense": sense,
            "event": event.event,
            "fields": event.fields,
            "text": event.text[:300],
            "note": "observation, not proof of an attack",
        }
        fd = os.open(target, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True) + "\n")
    except OSError:
        pass


def band(
    value: float,
    levels: List[Tuple[str, Optional[float]]],
    previous: Optional[str] = None,
    hysteresis: float = 0.0,
) -> str:
    """Classify value into a named band with optional hysteresis."""
    names = [n for n, _ in levels]
    bounds = [b for _, b in levels]

    def plain(v: float) -> str:
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


def run_sense(
    name: str,
    observe: Callable[[], Dict[str, Any]],
    detect: Callable[[Dict[str, Any], Dict[str, Any], float], Tuple[List[Event], Dict[str, Any]]],
    dry_run: bool = False,
    state_file: Optional[str] = None,
    now: Optional[float] = None,
    sense_mod: Any = None,
    journal_path: Optional[Path] = None,
    state_name: Optional[str] = None,
) -> Tuple[Dict[str, Any], int]:
    now = float(now if now is not None else time.time())
    try:
        obs = observe()
    except Exception as exc:
        return {"ok": False, "sense": name, "error": str(exc)}, 1

    path = state_path(state_name or name, state_file)
    prev = load_state(path)
    cool = dict(prev.get("_cooldown", {}))

    try:
        events, state = detect({k: v for k, v in prev.items() if k != "_cooldown"}, obs, now)
    except Exception as exc:
        return {"ok": False, "sense": name, "error": str(exc)}, 1

    emitted = []
    for ev in events:
        key = ev.key or ev.event
        if ev.cooldown_s and key in cool and now - float(cool[key]) < ev.cooldown_s:
            continue

        fields = {clean_field(k): clean_field(v) for k, v in ev.fields.items()}
        # Format line
        line = f"NOOBIA P{ev.priority} {name} {ev.event}"
        if fields:
            line += " " + " ".join(f"{k}={v}" for k, v in sorted(fields.items()))
        if ev.text:
            line += f" | {clean_text(ev.text)}"

        if sense_mod and hasattr(sense_mod, "emit"):
            try:
                sense_mod.emit(ev.priority, name, ev.event, fields=fields or None, text=clean_text(ev.text))
            except Exception:
                pass

        emitted.append(line)
        if ev.cooldown_s:
            cool[key] = now
        if ev.journal and not dry_run:
            journal(ev, name, now, journal_path)

    state = dict(state)
    state["_cooldown"] = {k: v for k, v in cool.items() if now - float(v) < 86400}
    if not dry_run:
        save_state(path, state)

    return {"ok": True, "sense": state_name or name, "emitted": emitted, "dry_run": dry_run}, 0
