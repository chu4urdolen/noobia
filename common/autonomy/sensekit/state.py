"""State management and persistence helpers for Noob senses."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
from typing import Any, Dict, Optional

DEFAULT_STATE_DIR = "/var/lib/noobia/senses"


def clean_field(value: Any) -> str:
    """Sanitize a value into a legal sense-line field value (ASCII, no whitespace/pipes)."""
    text = str(value)
    if not text.isascii():
        text = text.encode("ascii", "replace").decode("ascii")
    text = re.sub(r"[\s\"'|]+", "_", text)
    return text[:32]


def clean_text(value: Any) -> str:
    """Sanitize a value into a legal sense-line text tail."""
    text = str(value)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:300]


def state_path(sense: str, override: Optional[str] = None) -> Path:
    if override:
        return Path(override)
    root = Path(os.environ.get("NOOBIA_SENSES_STATE_DIR", DEFAULT_STATE_DIR))
    return root / sense / "state.json"


def load_state(path: Path) -> Dict[str, Any]:
    try:
        data = path.read_text(encoding="utf-8")
        parsed = json.loads(data)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return {}


def save_state(path: Path, state: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(f".tmp.{os.getpid()}")
    try:
        temp.write_text(json.dumps(state, indent=1) + "\n", encoding="utf-8")
        temp.replace(path)
    finally:
        if temp.exists():
            try:
                temp.unlink()
            except OSError:
                pass
