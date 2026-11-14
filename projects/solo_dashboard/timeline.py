"""Utilities for extracting visible conversation turns from a Codex JSONL log.

The web dashboard for the solo ``Dushich`` panel needs a lightweight parser
that can read a Codex JSONL file and expose only the *public* messages that
should appear in a conversation timeline.  Codex logs contain many internal
records – tool calls, reasoning steps, and other system events – that must
not be leaked to the end‑user.

The :func:`visible_messages` function returns a list of dictionaries, each
containing the timestamp, the speaker role (``"user"`` or ``"assistant"``),
and the plain text of the message.  It ignores all other record types and
skips messages whose content type is not ``input_text`` or ``output_text``.

The implementation is intentionally straightforward: it streams the file
line‑by‑line to avoid loading huge logs into memory.  It does not depend on
any external libraries beyond the standard library.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, List, Dict

__all__ = ["visible_messages"]


def _is_visible_message(record: dict) -> bool:
    """Return ``True`` if *record* represents a public user or assistant message.

    A record is considered visible when:
    * ``type`` is ``"response_item"``;
    * it contains an ``item`` whose ``type`` is ``"message"``;
    * ``item`` has a ``role`` of ``"user"`` or ``"assistant"``;
    * ``item`` has a ``content`` with a ``type`` of ``"input_text"`` or
      ``"output_text"``.
    """

    if record.get("type") != "response_item":
        return False
    item = record.get("item")
    if not isinstance(item, dict):
        return False
    if item.get("type") != "message":
        return False
    role = item.get("role")
    if role not in ("user", "assistant"):
        return False
    content = item.get("content")
    if not isinstance(content, dict):
        return False
    if content.get("type") not in ("input_text", "output_text"):
        return False
    return True


def visible_messages(jsonl_path: str | Path) -> List[Dict[str, object]]:
    """Yield visible conversation turns from *jsonl_path*.

    Parameters
    ----------
    jsonl_path:
        Path to a Codex JSONL log file.

    Returns
    -------
    list[dict]
        A list of dictionaries, each containing ``timestamp``, ``role`` and
        ``text`` keys.  The list preserves the order of appearance in the
        file.
    """

    path = Path(jsonl_path)
    results: List[Dict[str, object]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                # Skip malformed lines – they are not part of the visible
                # conversation.
                continue
            if not _is_visible_message(record):
                continue
            timestamp = record.get("timestamp")
            item = record["item"]
            role = item["role"]
            text = item["content"]["text"]
            # Skip assistant reasoning steps that start with common markers.
            if role == "assistant" and text.lstrip().startswith("Thinking"):
                continue
            results.append({"timestamp": timestamp, "role": role, "text": text})
    return results

