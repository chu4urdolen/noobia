"""Read only visible Antigravity conversation turns from local history.

The CLI stores protobuf steps in SQLite. Intermediate agent steps contain
working text and tool calls; only user prompts and final agent answers belong
in a shared conversation view or Dushich's delegated brief.
"""

from __future__ import annotations

from pathlib import Path
from contextlib import closing
import json
import sqlite3
import sys

CONVERSATIONS = Path('/home/aria/.gemini/antigravity-cli/conversations')


def _varint(data: bytes, offset: int) -> tuple[int, int]:
    value = shift = 0
    while offset < len(data):
        byte = data[offset]
        offset += 1
        value |= (byte & 127) << shift
        if byte < 128:
            return value, offset
        shift += 7
        if shift > 63:
            break
    raise ValueError('Invalid protobuf varint')


def fields(data: bytes) -> list[tuple[int, int, bytes | int]]:
    result = []
    offset = 0
    while offset < len(data):
        tag, offset = _varint(data, offset)
        number, wire = tag >> 3, tag & 7
        if wire == 0:
            value, offset = _varint(data, offset)
        elif wire == 2:
            length, offset = _varint(data, offset)
            if length > len(data) - offset:
                raise ValueError('Invalid protobuf length')
            value = data[offset:offset + length]
            offset += length
        elif wire in (1, 5):
            length = 8 if wire == 1 else 4
            value = data[offset:offset + length]
            offset += length
        else:
            raise ValueError('Unsupported protobuf wire type')
        result.append((number, wire, value))
    return result


def read(path: Path) -> list[dict]:
    if not path.is_file() or path.suffix != '.db' or path.parent != CONVERSATIONS:
        raise ValueError('Unknown Antigravity conversation')
    result = []
    try:
        # sqlite3's connection context manager commits/rolls back, but does not
        # close the connection. The dashboard polls many conversations often.
        with closing(sqlite3.connect(f'file:{path}?mode=ro', uri=True, timeout=2)) as db:
            rows = db.execute('SELECT idx, step_type, step_payload FROM steps ORDER BY idx')
            for index, kind, payload in rows:
                if kind not in (14, 15) or not payload:
                    continue
                try:
                    section = 19 if kind == 14 else 20
                    nested = next(value for field, wire, value in fields(payload)
                                  if field == section and wire == 2)
                    nested_fields = fields(nested)
                    if kind == 14:
                        value = next(value for field, wire, value in nested_fields
                                     if field == 2 and wire == 2)
                        role = 'noob'
                    else:
                        # Field 1 is the final answer. Field 3 is intermediate
                        # working text and must never be shown here.
                        value = next(value for field, wire, value in nested_fields
                                     if field == 1 and wire == 2)
                        role = 'banshee'
                    text = value.decode('utf-8').strip()
                except (StopIteration, ValueError, UnicodeDecodeError):
                    continue
                if text:
                    result.append({'index': index, 'role': role, 'text': text})
    except sqlite3.OperationalError as exc:
        raise ValueError('Banshee conversation is unreadable') from exc
    return result


def latest_for_workspace(workspace: Path, history: Path) -> Path | None:
    """Match a Banshee DB to prompts recorded for its workspace."""
    import json
    prompts = set()
    if history.is_file():
        for line in history.read_text(encoding='utf-8').splitlines():
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get('workspace') == str(workspace) and not entry.get('type'):
                prompts.add(entry.get('display'))
    matching = []
    for path in CONVERSATIONS.glob('*.db'):
        try:
            turns = read(path)
            if any(turn['role'] == 'noob' and turn['text'] in prompts for turn in turns):
                matching.append(path)
        except (OSError, sqlite3.Error, ValueError):
            continue
    return max(matching, key=lambda p: p.stat().st_mtime) if matching else None


if __name__ == '__main__':
    if len(sys.argv) != 2 or not all(c in '0123456789abcdef-' for c in sys.argv[1]):
        raise SystemExit('Usage: visible_dialogue.py CONVERSATION_ID')
    print(json.dumps(read(CONVERSATIONS / (sys.argv[1] + '.db')), ensure_ascii=False))
