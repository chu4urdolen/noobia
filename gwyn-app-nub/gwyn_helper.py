#!/usr/bin/env python3
"""Ask local Helper Dushich about a Gwyn conversation, one Codex thread each.

Unlike Banshee's mirror there is no watcher service: each question brings the
thread up to date with an incremental summary of the visible Noob/Gwyn
dialogue, then asks on the same persistent thread so Dushich keeps context.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, '/noobia/dushich/coding')
sys.path.insert(0, '/noobia/aria')
import dushich_summarizer
import helper_mirror as shared
from visible_dialogue import CONVERSATIONS, read as visible_turns

ROOT = Path('/home/aria/.codex/dushich-bridge/helper-mirror/gwyn')
SUMMARIZER_CONTEXT_SIZE = 24_000
SUMMARIZER_DESIRED_SIZE = 6_000


def folder(conversation_id: str) -> Path:
    if not shared.UUID.fullmatch(conversation_id):
        raise ValueError('Invalid Gwyn conversation ID')
    result = ROOT / conversation_id
    result.mkdir(mode=0o700, parents=True, exist_ok=True)
    return result


def log_activity(conversation_id: str, entry: dict) -> None:
    try:
        path = folder(conversation_id) / 'activity.jsonl'
        with path.open('a', encoding='utf-8') as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(json.dumps(entry, ensure_ascii=False) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        pass


@contextmanager
def locked(conversation_id: str):
    with (folder(conversation_id) / 'lock').open('a+') as stream:
        os.fchmod(stream.fileno(), 0o600)
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def state_for(conversation_id: str) -> dict:
    path = folder(conversation_id) / 'state.json'
    return json.loads(path.read_text()) if path.exists() else {'thread_id': None, 'asked': 0}


def save_state(conversation_id: str, state: dict) -> None:
    path = folder(conversation_id) / 'state.json'
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(state, indent=2) + '\n')
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def ask(conversation_id: str, question: str) -> str:
    if not question.strip() or len(question.encode('utf-8')) > 8000:
        raise ValueError('Provide a question up to 8 KB')
    path = CONVERSATIONS / (conversation_id + '.jsonl')
    if not path.is_file():
        raise ValueError('Gwyn conversation transcript is unavailable')
    now_str = datetime.now(timezone.utc).strftime('%H:%M:%S')
    log_activity(conversation_id, {'time': now_str, 'type': 'question', 'question': question.strip()})
    with locked(conversation_id):
        state = state_for(conversation_id)
        lines = [f"{'Noob' if turn['role'] == 'noob' else 'Gwyn'}: {shared.redact(turn['text'])}"
                 for turn in visible_turns(path)]
        summary = dushich_summarizer.incremental_summarize(
            conversation_id,
            lines,
            context_size=SUMMARIZER_CONTEXT_SIZE,
            desired_size=SUMMARIZER_DESIRED_SIZE,
        )
        prompt = ('You are Helper Dushich. Gwyn, the Claude Code Noob, asks you directly about '
                  'the conversation below. Do not use tools or edit files. Answer from your '
                  'thread context and the cumulative summary; say when you are unsure.\n\n'
                  + (f'Cumulative Noob/Gwyn conversation summary ({conversation_id}):\n{summary}\n\n'
                     if summary else '')
                  + 'Question:\n' + question)
        thread_id, events = shared.run_turn(prompt, state.get('thread_id'))
        state.update(thread_id=thread_id, asked=state.get('asked', 0) + 1)
        save_state(conversation_id, state)
    replies = [event.get('item', {}).get('text', '').strip() for event in events
               if event.get('type') == 'item.completed'
               and event.get('item', {}).get('type') == 'agent_message']
    if not replies or not replies[-1]:
        raise RuntimeError('Helper Dushich did not send a visible answer')
    answer = replies[-1]
    now_str = datetime.now(timezone.utc).strftime('%H:%M:%S')
    log_activity(conversation_id, {'time': now_str, 'type': 'answer', 'answer': answer})
    return answer


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Ask Helper Dushich about a Gwyn conversation")
    parser.add_argument('action', choices=['ask', 'status'])
    parser.add_argument('--conversation-id', required=True)
    parser.add_argument('--question')
    args = parser.parse_args()
    try:
        if args.action == 'ask':
            if not args.question:
                parser.error('--question is required')
            print(ask(args.conversation_id, args.question))
        else:
            print(json.dumps(state_for(args.conversation_id)))
    except (OSError, ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)
