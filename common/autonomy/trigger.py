"""Trigger and chunker for Noobia autonomy (ARCHITECTURE.md §2).

Deliverable A, task E3.

Chunks close for one of three reasons:
1. PRIORITY: for some n >= 1, chunk holds n lines of Pn (including carried).
2. VOLUME: more than max_lines arrive during this chunk.
3. TIMEOUT: window_s has passed since chunk opened, holds at least one line.

Priority lines carry over on TIMEOUT, are stripped, and waiting priority lines
continue to count toward their threshold in the next chunk.
On VOLUME, chunk sends as-is (carried + new lines) and priority counters reset,
unless volume_resets_priority=False.
"""

from __future__ import annotations

from typing import Callable
try:
    from .sense import parse_line
except (ImportError, ValueError):
    from sense import parse_line


class Chunker:
    def __init__(
        self,
        window_s: float = 60.0,
        max_lines: int = 15,
        max_chunk_lines: int = 200,
        max_bytes: int = 32768,
        carry_max_lines: int = 200,
        carry_max_age_s: float = 600.0,
        volume_resets_priority: bool = True,
        disabled: Callable[[], bool] = lambda: False,
    ):
        self.window_s = float(window_s)
        self.max_lines = int(max_lines)
        self.max_chunk_lines = int(max_chunk_lines)
        self.max_bytes = int(max_bytes)
        self.carry_max_lines = int(carry_max_lines)
        self.carry_max_age_s = float(carry_max_age_s)
        self.volume_resets_priority = bool(volume_resets_priority)
        self.disabled = disabled

        # Carried lines: list of (arrival_time, parsed_dict)
        self._carried: list[tuple[float, dict]] = []
        # Current chunk lines: list of (arrival_time, parsed_dict)
        self._current: list[tuple[float, dict]] = []
        self._chunk_open_time: float | None = None

    @property
    def carried(self) -> list[dict]:
        """Priority lines currently carried forward, in order."""
        return [item[1] for item in self._carried]

    def _purge_expired_carried(self, now: float) -> list[dict]:
        """Remove carried lines older than carry_max_age_s and return them marked carried_expired."""
        kept = []
        expired = []
        for arr_time, line in self._carried:
            if now - arr_time > self.carry_max_age_s:
                line["carried_expired"] = True
                expired.append(line)
            else:
                kept.append((arr_time, line))
        self._carried = kept
        return expired

    def feed(self, line: str | dict, now: float) -> list[dict]:
        """Feed a sense line at time `now`. Returns a list of Closed chunks."""
        if self.disabled():
            return []

        if isinstance(line, str):
            parsed = parse_line(line)
            if parsed is None:
                return []
        elif isinstance(line, dict):
            parsed = line
        else:
            return []

        if self._chunk_open_time is None:
            self._chunk_open_time = now

        self._current.append((now, parsed))

        # Check PRIORITY trigger
        # Counts lines of Pn where n >= 1 and not self_caused, across carried + current
        # A line with p >= 1 triggers if total count of lines with that exact priority p >= p
        p_counts: dict[int, int] = {}
        for _, l in self._carried:
            if l.get("p", 0) >= 1 and not l.get("self_caused", False):
                p_val = l["p"]
                p_counts[p_val] = p_counts.get(p_val, 0) + 1

        for _, l in self._current:
            if l.get("p", 0) >= 1 and not l.get("self_caused", False):
                p_val = l["p"]
                p_counts[p_val] = p_counts.get(p_val, 0) + 1

        priority_triggered = any(count >= p_val for p_val, count in p_counts.items())

        if priority_triggered:
            # Whole chunk goes on: carried lines first, then current lines
            all_lines = [l for _, l in self._carried] + [l for _, l in self._current]
            self._carried = []
            self._current = []
            self._chunk_open_time = None
            return [{"reason": "priority", "lines": all_lines}]

        # Check VOLUME trigger: more than max_lines arrived during this chunk (cause=self lines do not count toward trigger rules)
        non_self_caused_count = sum(1 for _, l in self._current if not l.get("self_caused", False))
        if non_self_caused_count > self.max_lines or len(self._current) >= self.max_chunk_lines:
            if self.volume_resets_priority:
                all_lines = [l for _, l in self._carried] + [l for _, l in self._current]
                self._carried = []
            else:
                all_lines = [l for _, l in self._current]
            self._current = []
            self._chunk_open_time = None
            return [{"reason": "volume", "lines": all_lines}]

        return []

    def tick(self, now: float) -> list[dict]:
        """Tick the chunker clock to `now` to process timeouts."""
        if self.disabled():
            return []

        if self._chunk_open_time is None or not self._current:
            return []

        if now - self._chunk_open_time >= self.window_s:
            # Chunk closes on timeout
            # Release expired carried lines
            expired = self._purge_expired_carried(now)

            # Strip priority lines (p >= 1 and not self_caused) from current chunk
            to_send = list(expired)
            new_carried = []
            for arr_time, l in self._current:
                if l.get("p", 0) >= 1 and not l.get("self_caused", False):
                    new_carried.append((arr_time, l))
                else:
                    to_send.append(l)

            # Append new carried to existing carried, respecting carry_max_lines
            self._carried.extend(new_carried)
            if len(self._carried) > self.carry_max_lines:
                self._carried = self._carried[-self.carry_max_lines:]

            self._current = []
            self._chunk_open_time = None

            if to_send:
                return [{"reason": "timeout", "lines": to_send}]
            else:
                return []

        return []
