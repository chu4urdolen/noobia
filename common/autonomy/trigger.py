"""Trigger and chunker for Noobia autonomy (ARCHITECTURE.md §2).

Deliverable A, task E3. Review fixes T1-T3 and E3b liveness applied.

Chunks close for one of three reasons:
1. PRIORITY: for some n >= 1, chunk holds n lines of Pn (including carried).
2. VOLUME: more than max_lines arrive during this chunk, or max_chunk_lines / max_bytes reached.
3. TIMEOUT: window_s has passed since chunk opened, holds at least one line.
Also reports view.silent after silence_s (E3b).
"""

from __future__ import annotations

import json
from typing import Callable

try:
    from .sense import parse_line, format_line
except (ImportError, ValueError):
    from sense import parse_line, format_line


def _line_bytes(line: dict) -> int:
    """Calculate encoded byte size of line."""
    raw = line.get("raw")
    if raw:
        return len(raw.encode("utf-8"))
    return len(json.dumps(line).encode("utf-8"))


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
        uniform_priority: int = 0,
        carry_priority: bool = True,
        silence_s: float = 900.0,
        heartbeat_s: float = 300.0,
        disabled: Callable[[], bool] = lambda: False,
        is_busy: Callable[[], bool] = lambda: False,
    ):
        self.window_s = float(window_s)
        self.max_lines = int(max_lines)
        self.max_chunk_lines = int(max_chunk_lines)
        self.max_bytes = int(max_bytes)
        self.carry_max_lines = int(carry_max_lines)
        self.carry_max_age_s = float(carry_max_age_s)
        self.volume_resets_priority = bool(volume_resets_priority)
        # Tom 2026-11-23: every reaction at one level (e.g. 5): five such
        # lines of ANY kind close the chunk; fewer wait for window_s.
        self.uniform_priority = int(uniform_priority)
        # False: a timeout sends priority lines too instead of carrying them.
        self.carry_priority = bool(carry_priority)
        self.silence_s = float(silence_s)
        self.heartbeat_s = float(heartbeat_s)
        self.disabled = disabled
        self.is_busy = is_busy

        # Carried lines: list of (arrival_time, parsed_dict)
        self._carried: list[tuple[float, dict]] = []
        # Current chunk lines: list of (arrival_time, parsed_dict)
        self._current: list[tuple[float, dict]] = []
        self._overflow_carried: list[dict] = []
        self._chunk_open_time: float | None = None
        self._last_line_time: float | None = None
        self._silence_reported: bool = False
        self.overflow_count: int = 0

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

    def reset(self) -> None:
        """Forget every pending, open and carried line (used after the kill
        switch is lifted, so nothing from before it can close later)."""
        self._carried = []
        self._current = []
        self._overflow_carried = []
        self._chunk_open_time = None
        self._last_line_time = None
        self._silence_reported = False

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

        self._last_line_time = now
        self._silence_reported = False

        if self._chunk_open_time is None:
            self._chunk_open_time = now

        if self.uniform_priority >= 1 and parsed.get("p", 0) >= 1:
            parsed = dict(parsed, p=self.uniform_priority)
        self._current.append((now, parsed))

        # While busy (e.g. agent queueing on GPU), expand the window and do not close early
        if self.is_busy():
            return []

        # Check PRIORITY trigger
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
            all_lines = (
                list(self._overflow_carried)
                + [l for _, l in self._carried]
                + [l for _, l in self._current]
            )
            self._overflow_carried = []
            self._carried = []
            self._current = []
            self._chunk_open_time = None
            return [{"reason": "priority", "lines": all_lines}]

        # Check VOLUME trigger (T1: max_bytes, T3: total lines bound, and arrival count)
        non_self_caused_count = sum(1 for _, l in self._current if not l.get("self_caused", False))
        total_current_lines = len(self._carried) + len(self._current)
        total_bytes = sum(_line_bytes(l) for _, l in self._carried) + sum(_line_bytes(l) for _, l in self._current)

        volume_triggered = (
            non_self_caused_count > self.max_lines
            or total_current_lines >= self.max_chunk_lines
            or total_bytes >= self.max_bytes
        )

        if volume_triggered:
            if self.volume_resets_priority:
                all_lines = (
                    list(self._overflow_carried)
                    + [l for _, l in self._carried]
                    + [l for _, l in self._current]
                )
                self._overflow_carried = []
                self._carried = []
            else:
                all_lines = list(self._overflow_carried) + [l for _, l in self._current]
                self._overflow_carried = []
            self._current = []
            self._chunk_open_time = None
            return [{"reason": "volume", "lines": all_lines}]

        return []

    def tick(self, now: float) -> list[dict]:
        """Tick the chunker clock to `now` to process timeouts and silence."""
        if self.disabled():
            return []

        # While busy (e.g. agent queueing on GPU), expand the window and do not close early
        if self.is_busy():
            return []

        # E3b: Silence detection
        if (
            self._last_line_time is not None
            and not self._silence_reported
            and now - self._last_line_time >= self.silence_s
        ):
            self._silence_reported = True
            silent_line = parse_line(
                format_line(1, "autonomy", "view.silent", {"silence_s": int(self.silence_s)}, "sense view silent")
            )
            return [{"reason": "silence", "lines": [silent_line]}]

        if self._chunk_open_time is None or not self._current:
            return []

        if now - self._chunk_open_time >= self.window_s:
            # Chunk closes on timeout
            expired = self._purge_expired_carried(now)

            # Strip priority lines (p >= 1 and not self_caused) from current chunk
            to_send = list(self._overflow_carried) + list(expired)
            self._overflow_carried = []
            new_carried = []
            for arr_time, l in self._current:
                if self.carry_priority and l.get("p", 0) >= 1 and not l.get("self_caused", False):
                    new_carried.append((arr_time, l))
                else:
                    to_send.append(l)

            # T2: Carry overflow: excess priority lines released into next sent chunk rather than dropped
            self._carried.extend(new_carried)
            if len(self._carried) > self.carry_max_lines:
                overflow_count = len(self._carried) - self.carry_max_lines
                self.overflow_count += overflow_count
                overflow_items = self._carried[:overflow_count]
                self._carried = self._carried[overflow_count:]
                for _, item in overflow_items:
                    item["carried_overflow"] = True
                    self._overflow_carried.append(item)

            self._current = []
            self._chunk_open_time = None

            if to_send:
                return [{"reason": "timeout", "lines": to_send}]
            else:
                return []

        return []
