"""Noob Profile System (Section 3 & NA-80).

Loads host identity and autonomy configuration from /etc/noobia/noob.json:
- name, timezone, paths, senses, tools, brain, window policy.
- Zero host-specific hardcoding: allows any Linux Noob (Lynx, Argus, Syra, NanoPi)
  to run common autonomy infrastructure purely from its profile.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_PROFILE_PATH = Path("/etc/noobia/noob.json")


@dataclass
class WindowConfig:
    window_s: float = 60.0
    max_lines: int = 15
    carry_priority: bool = False
    volume_resets_priority: bool = True
    uniform_priority: int = 0
    priority_mode: str = "sum"
    priority_threshold: int = 20


@dataclass
class Profile:
    name: str
    timezone: str = "Europe/Sofia"
    paths: Dict[str, str] = field(default_factory=dict)
    senses: List[str] = field(default_factory=list)
    tool_dir: str = "/usr/local/share/lynx/agent-tools"
    window: WindowConfig = field(default_factory=WindowConfig)
    brain: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path | str | None = None) -> Profile:
        p = Path(path) if path else DEFAULT_PROFILE_PATH
        if not p.is_file():
            # Fallback to sensible defaults
            host = os.environ.get("NOOB_NAME") or "lynx"
            return cls(name=host)

        data = json.loads(p.read_text(encoding="utf-8"))
        win_data = data.get("window", {})
        window = WindowConfig(
            window_s=float(win_data.get("window_s", 60.0)),
            max_lines=int(win_data.get("max_lines", 15)),
            carry_priority=bool(win_data.get("carry_priority", False)),
            volume_resets_priority=bool(win_data.get("volume_resets_priority", True)),
            uniform_priority=int(win_data.get("uniform_priority", 0)),
            priority_mode=str(win_data.get("priority_mode", "sum")),
            priority_threshold=int(win_data.get("priority_threshold", 20)),
        )

        return cls(
            name=str(data.get("name", "lynx")),
            timezone=str(data.get("timezone", "Europe/Sofia")),
            paths=dict(data.get("paths", {})),
            senses=list(data.get("senses", [])),
            tool_dir=str(data.get("tool_dir", "/usr/local/share/lynx/agent-tools")),
            window=window,
            brain=dict(data.get("brain", {}))
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "timezone": self.timezone,
            "paths": self.paths,
            "senses": self.senses,
            "tool_dir": self.tool_dir,
            "window": {
                "window_s": self.window.window_s,
                "max_lines": self.window.max_lines,
                "carry_priority": self.window.carry_priority,
                "volume_resets_priority": self.window.volume_resets_priority,
                "uniform_priority": self.window.uniform_priority,
                "priority_mode": self.window.priority_mode,
                "priority_threshold": self.window.priority_threshold,
            },
            "brain": self.brain,
        }

    def save(self, path: Path | str | None = None) -> None:
        p = Path(path) if path else DEFAULT_PROFILE_PATH
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")
