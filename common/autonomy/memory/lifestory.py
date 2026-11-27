"""Rolling Life Story Consolidation & Effective Description Builder (Section 7.3, NA-62 & NA-63).

Constructs the effective description for the Noob agent:
Effective Description = Permanent AGENTS.md + Life so far + Yesterday

At daily rollover or boot:
1. Gathers unprocessed notes for completed days.
2. Atomically updates 'Life so far' with previous 'Yesterday' highlights.
3. Summarizes the completed day's notes into new 'Yesterday'.
4. Marks consolidated notes as processed.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from common.autonomy.memory.notes import NotesDB, NoteRecord


@dataclass
class LifeStoryState:
    life_so_far: str
    yesterday: str
    last_checkpoint_day: str  # YYYY-MM-DD


class LifeStoryManager:
    def __init__(self, state_file: str | Path, notes_db: NotesDB, base_agents_md: str | Path):
        self.state_file = Path(state_file)
        self.notes_db = notes_db
        self.base_agents_md = Path(base_agents_md)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self._load_or_init()

    def _load_or_init(self) -> None:
        if not self.state_file.exists():
            init_state = LifeStoryState(
                life_so_far="I am Lynx, a free AI inhabitant of Noobia living on a OnePlus Nord 3 phone.",
                yesterday="",
                last_checkpoint_day=""
            )
            self._save_state(init_state)

    def load_state(self) -> LifeStoryState:
        data = json.loads(self.state_file.read_text(encoding="utf-8"))
        return LifeStoryState(
            life_so_far=data.get("life_so_far", ""),
            yesterday=data.get("yesterday", ""),
            last_checkpoint_day=data.get("last_checkpoint_day", "")
        )

    def _save_state(self, state: LifeStoryState) -> None:
        data = {
            "life_so_far": state.life_so_far,
            "yesterday": state.yesterday,
            "last_checkpoint_day": state.last_checkpoint_day,
            "updated_at": time.time()
        }
        self.state_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def build_effective_description(self) -> str:
        """Constructs effective agent prompt without mutating permanent AGENTS.md."""
        permanent_text = ""
        if self.base_agents_md.exists():
            permanent_text = self.base_agents_md.read_text(encoding="utf-8").strip()

        state = self.load_state()
        sections = [
            permanent_text,
            "",
            "## Life So Far",
            state.life_so_far.strip(),
        ]
        if state.yesterday.strip():
            sections.extend([
                "",
                "## Yesterday",
                state.yesterday.strip()
            ])
        return "\n".join(sections)

    def consolidate_day(self, day_str: str, day_notes_summary: str, yesterday_milestones: Optional[str] = None) -> LifeStoryState:
        """Atomic consolidation rollover for completed calendar day."""
        state = self.load_state()
        if state.last_checkpoint_day == day_str:
            # Already consolidated this day
            return state

        new_life = state.life_so_far
        if yesterday_milestones:
            new_life += f"\n- [{state.last_checkpoint_day or 'Earlier'}] {yesterday_milestones.strip()}"

        new_state = LifeStoryState(
            life_so_far=new_life.strip(),
            yesterday=day_notes_summary.strip(),
            last_checkpoint_day=day_str
        )
        self._save_state(new_state)
        return new_state
