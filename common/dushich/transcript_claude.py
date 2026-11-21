"""Read only visible Claude Code conversation turns from Gwyn's transcripts.

Claude Code stores each session as JSONL. Thinking blocks, tool calls, tool
results, and bookkeeping entries are working state; only Noob's prompts and
Gwyn's final answer for each turn belong in Dushich's brief.
"""

from __future__ import annotations

from pathlib import Path
import json
import sys

from agents import NOOBIA

# Claude Code names a project's transcript folder after its path, with / as -.
PROJECTS = NOOBIA / 'gwyn-app-nub/private/claude/projects'
WORKSPACE = NOOBIA / 'gwyn-app-nub'  # where Gwyn's launcher starts Claude Code
CONVERSATIONS = PROJECTS / str(WORKSPACE).replace('/', '-')
# Before ea2f497 (2026-11-21) the launcher started in gwyn-app-nub/workspace.
# Sessions begun or resumed from there still write to this folder.
LEGACY_WORKSPACE = NOOBIA / 'gwyn-app-nub/workspace'
LEGACY_CONVERSATIONS = PROJECTS / str(LEGACY_WORKSPACE).replace('/', '-')


def folders() -> tuple[Path, ...]:
    """Transcript folders, current first (read at call time for tests)."""
    return (CONVERSATIONS, LEGACY_CONVERSATIONS)


def find(conversation_id: str) -> Path | None:
    """The transcript for a conversation ID in any known folder, or None."""
    if not conversation_id or not all(c in '0123456789abcdef-' for c in conversation_id):
        return None
    for folder in folders():
        path = folder / f'{conversation_id}.jsonl'
        if path.is_file():
            return path
    return None


def _prompt_text(content) -> str:
    if isinstance(content, str):
        text = content
    elif isinstance(content, list) and not any(b.get('type') == 'tool_result' for b in content):
        text = '\n'.join(b.get('text', '') for b in content if b.get('type') == 'text')
    else:
        return ''
    text = text.strip()
    # Slash-command echoes and local command output are not dialogue.
    if text.startswith(('<command-', '<local-command', '<system-reminder>')):
        return ''
    return text


def read(path: Path) -> list[dict]:
    if not path.is_file() or path.suffix != '.jsonl' or path.parent not in folders():
        raise ValueError('Unknown Gwyn conversation')
    result = []
    answer = None
    for index, line in enumerate(path.read_text(encoding='utf-8').splitlines()):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get('isSidechain') or entry.get('isMeta'):
            continue
        message = entry.get('message') or {}
        if entry.get('type') == 'user':
            text = _prompt_text(message.get('content'))
            if not text:
                continue
            if answer:
                result.append(answer)
                answer = None
            result.append({'index': index, 'role': 'noob', 'text': text})
        elif entry.get('type') == 'assistant':
            # Keep only the last text block before the next prompt: the
            # turn's final answer, not intermediate progress notes.
            for block in message.get('content') or []:
                if block.get('type') == 'text' and block.get('text', '').strip():
                    answer = {'index': index, 'role': 'gwyn', 'text': block['text'].strip()}
    if answer:
        result.append(answer)
    return result


def latest() -> Path | None:
    found = [path for folder in folders() for path in folder.glob('*.jsonl')]
    return max(found, key=lambda p: p.stat().st_mtime) if found else None


def locate(conversation_id: str | None) -> Path | None:
    """The conversation's transcript, or the newest one if it is unknown."""
    return find(conversation_id or '') or latest()


if __name__ == '__main__':
    if len(sys.argv) != 2 or not all(c in '0123456789abcdef-' for c in sys.argv[1]):
        raise SystemExit('Usage: transcript_claude.py SESSION_ID')
    path = find(sys.argv[1])
    if path is None:
        raise SystemExit('Unknown Gwyn conversation')
    print(json.dumps(read(path), ensure_ascii=False))
