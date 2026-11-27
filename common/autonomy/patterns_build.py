#!/usr/bin/env python3
"""Generic helper library for building autonomy pattern sets (NA-84).

Provides pattern construction, schema validation against ranker examples,
and JSON compilation.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from common.autonomy.ranker import validate_pattern
except ImportError:
    from ranker import validate_pattern


def make_pattern(
    pid: str,
    sense: str,
    event: str,
    template: str,
    message: str,
    must: List[str],
    must_not: List[str],
    cooldown: float = 0.0,
    to_noob: bool = True,
    origin: str = "autonomy",
    **extra: Any,
) -> Dict[str, Any]:
    """Construct one validated pattern dictionary."""
    d: Dict[str, Any] = {
        "id": pid,
        "match": {"sense": sense, "event": event},
        "template": template,
        "message": message,
        "to_noob": to_noob,
        "cooldown_s": cooldown,
        "examples": {"must": must, "must_not": must_not},
        "hits": 0,
        "origin": origin,
    }
    d.update(extra)
    return d


# Alias for backward compatibility
P = make_pattern


def build_patterns(
    patterns: List[Dict[str, Any]],
    output_path: Optional[Path | str] = None,
    validate: bool = True,
) -> Dict[str, Any]:
    """Validate a list of patterns and optionally write them to a JSON file."""
    ids = set()
    for p in patterns:
        pid = p["id"]
        if pid in ids:
            raise ValueError(f"Duplicate pattern ID: {pid}")
        ids.add(pid)
        if validate:
            validate_pattern(p, [])

    payload = {"store": patterns, "archive": []}
    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
        return {"ok": True, "written": str(out), "patterns": len(patterns)}
    return {"ok": True, "patterns": len(patterns), "store": payload}
