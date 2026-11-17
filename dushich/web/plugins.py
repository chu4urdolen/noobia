"""Agent adapters for the local Noobia conversation dashboard."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time

sys.path.insert(0, '/noobia/banshee')
from visible_dialogue import CONVERSATIONS, latest_for_workspace, read as agy_turns

UUID = re.compile(r'^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$')
NEW_CONVERSATION = 'new'
ARIA_ROOT = Path('/home/aria/.codex/sessions')
BANSHEE_WORKSPACE = Path('/noobia/banshee/workspace')
BANSHEE_BRAIN = Path('/home/aria/.gemini/antigravity-cli/brain')
_BANSHEE_QUOTA_CACHE: dict = {'time': 0.0, 'data': None}
HISTORY = Path('/home/aria/.gemini/antigravity-cli/history.jsonl')
CODEX_QUEUE = Path('/home/aria/.codex/queue_1.sqlite')
DIRECT_DIALOGUE = Path('/home/aria/.codex/dushich-bridge/direct-dialogue.jsonl')


def _timestamp(value: str | None) -> float:
    if not value:
        return 0
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
    except ValueError:
        return 0


def _tmux_sessions(prefix: str) -> list[str]:
    process = subprocess.run((['tmux', '-L', 'dushich-clean'] if prefix == 'noobia-dushich-solo-' else ['tmux']) + ['list-sessions', '-F', '#{session_name}'],
                             capture_output=True, text=True, check=False)
    return [s for s in process.stdout.splitlines() if s.startswith(prefix)]


def _aria_pane(session: str) -> str | None:
    process = subprocess.run(['tmux', 'list-panes', '-t', session + ':0',
                              '-F', '#{pane_id} #{pane_current_command}'],
                             capture_output=True, text=True, check=False)
    if process.returncode:
        return None
    for line in process.stdout.splitlines():
        pieces = line.split(' ', 1)
        if len(pieces) == 2 and pieces[1] == 'codex':
            return pieces[0]
    return None


def _aria_pane_conversation(pane: str) -> str | None:
    """Read the rollout actually open in a Codex pane (which may have forked)."""
    result = subprocess.run(['tmux', 'display-message', '-p', '-t', pane, '#{pane_pid}'],
                            capture_output=True, text=True, check=False)
    if result.returncode or not result.stdout.strip().isdigit():
        return None
    try:
        descriptors = Path('/proc') / result.stdout.strip() / 'fd'
        for descriptor in descriptors.iterdir():
            try:
                target = descriptor.readlink().name
            except OSError:
                continue
            match = re.search(r'rollout-.*?([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})\.jsonl$', target)
            if match:
                return match.group(1)
    except OSError:
        pass
    return None


def _job_results(root: Path, key: str, conversation: str) -> list[dict]:
    results = []
    if not root.is_dir():
        return results
    for path in root.glob('*/state.json'):
        try:
            state = json.loads(path.read_text(encoding='utf-8'))
            if state.get(key) != conversation:
                continue
            created = _timestamp(state.get('created'))
            brief = path.parent / 'brief.txt'
            if brief.is_file():
                task = brief.read_text(encoding='utf-8').split('\n\n', 1)[0]
                task = task.removeprefix('Current Dushich task:\n').strip()
                if task:
                    results.append({'role': 'aria' if key == 'aria_session_id' else 'banshee',
                                    'text': 'To Dushich: ' + task, 'time': created,
                                    'id': path.parent.name + ':task'})
            public = path.parent / 'public-dialogue.json'
            visible = []
            if public.is_file():
                items = json.loads(public.read_text(encoding='utf-8'))
                visible = [{'role': 'dushich', 'text': item['text'], 'time': item['time'],
                            'id': f'{path.parent.name}:message:{index}',
                            'final': index == len(items) - 1 and state.get('status') == 'done'}
                           for index, item in enumerate(items)
                           if isinstance(item, dict) and isinstance(item.get('text'), str)]
                results.extend(visible)
            report = path.parent / 'result.txt'
            if report.is_file() and not visible:
                result = report.read_text(encoding='utf-8').strip()
                if result:
                    results.append({'role': 'dushich', 'text': result,
                                    'time': _timestamp(state.get('finished')),
                                    'id': path.parent.name, 'final': state.get('status') == 'done'})
            elif state.get('status') in ('running', 'queued') and not visible:
                results.append({'role': 'dushich',
                                'text': f"Working on handoff {path.parent.name}…",
                                'time': _timestamp(state.get('created')),
                                'id': path.parent.name})
        except (OSError, ValueError, KeyError):
            continue
    return results


def _queued_codex_inputs(conversation: str) -> list[dict]:
    if not CODEX_QUEUE.is_file():
        return []
    results = []
    try:
        with sqlite3.connect(f'file:{CODEX_QUEUE}?mode=ro', uri=True, timeout=2) as db:
            rows = db.execute('SELECT id, payload_json, created_at_ms FROM queued_items '
                              'WHERE thread_id = ? ORDER BY queue_order', (conversation,))
            for ident, raw, created in rows:
                payload = json.loads(raw).get('UserInput') or {}
                message = '\n'.join(part.get('text', '') for part in payload.get('content', [])
                                    if isinstance(part, dict) and part.get('type') == 'text').strip()
                if message:
                    results.append({'role': 'noob', 'text': message, 'time': created / 1000,
                                    'queued': True, 'id': ident})
    except (OSError, sqlite3.Error, ValueError):
        return []
    return results


def _direct_dushich_dialogue(conversation: str) -> list[dict]:
    """Read only explicitly recorded, visible direct helper exchanges."""
    if not DIRECT_DIALOGUE.is_file():
        return []
    results = []
    for line in DIRECT_DIALOGUE.read_text(encoding='utf-8').splitlines():
        try:
            item = json.loads(line)
            if item.get('aria_session_id') != conversation or item.get('role') not in ('aria', 'dushich'):
                continue
            if not isinstance(item.get('text'), str) or not item['text'].strip():
                continue
            results.append({'role': item['role'], 'text': item['text'],
                            'time': _timestamp(item.get('timestamp')), 'id': item.get('id'),
                            'final': item.get('final', item['role'] == 'dushich')})
        except (ValueError, TypeError):
            continue
    return results


class AriaPlugin:
    id = 'aria'
    name = 'Aria + Dushich'
    color = 'blue'

    def _paths(self) -> dict[str, Path]:
        paths = {}
        for path in ARIA_ROOT.glob('**/rollout-*.jsonl'):
            match = re.search(r'([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})\.jsonl$', path.name)
            if match:
                paths[match.group(1)] = path
        return paths

    def conversations(self) -> list[dict]:
        active = {_aria_pane_conversation(pane) or s.removeprefix('noobia-aria-')
                  for s in _tmux_sessions('noobia-aria-') if (pane := _aria_pane(s))}
        known_paths = self._paths()
        paths = sorted(known_paths.items(), key=lambda item: item[1].stat().st_mtime, reverse=True)
        output = [{'id': ident, 'label': 'New Codex conversation', 'active': True}
                  for ident in sorted(active) if ident not in known_paths]
        for ident, path in paths[:40]:
            title = 'Codex conversation'
            try:
                with path.open(encoding='utf-8') as stream:
                    for line in stream:
                        event = json.loads(line)
                        payload = event.get('payload') or {}
                        if event.get('type') != 'response_item' or payload.get('role') != 'user':
                            continue
                        text = ' '.join(part.get('text', '') for part in payload.get('content', [])
                                        if part.get('type') == 'input_text').strip()
                        if text and not text.startswith(('# AGENTS.md instructions', '<environment_context>')):
                            title = text[:72]
                            break
            except (OSError, ValueError, sqlite3.Error):
                continue
            output.append({'id': ident, 'label': title, 'active': ident in active,
                           'updated': path.stat().st_mtime})
        return output

    def timeline(self, ident: str) -> list[dict]:
        if not UUID.fullmatch(ident):
            raise ValueError('Unknown Aria conversation')
        path = self._paths().get(ident)
        if not path:
            if _aria_pane('noobia-aria-' + ident):
                return _queued_codex_inputs(ident)
            raise ValueError('Unknown Aria conversation')
        events = []
        with path.open(encoding='utf-8') as stream:
            for line in stream:
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                payload = item.get('payload') or {}
                if item.get('type') != 'response_item' or payload.get('type') != 'message':
                    continue
                role = payload.get('role')
                if role not in ('user', 'assistant'):
                    continue
                kind = 'input_text' if role == 'user' else 'output_text'
                message = '\n'.join(part.get('text', '') for part in payload.get('content', [])
                                    if part.get('type') == kind).strip()
                if not message or message.startswith(('# AGENTS.md instructions', '<environment_context>')):
                    continue
                events.append({'role': 'noob' if role == 'user' else 'aria',
                               'text': message, 'time': _timestamp(item.get('timestamp')),
                               'final': role == 'assistant' and payload.get('phase') == 'final_answer'})
        events += _job_results(Path('/home/aria/.codex/dushich-bridge'), 'aria_session_id', ident)
        events += _direct_dushich_dialogue(ident)
        events += _queued_codex_inputs(ident)
        return sorted(events, key=lambda event: event['time'])[-300:]

    def send(self, ident: str, message: str) -> str:
        if (ident != NEW_CONVERSATION and ident not in self._paths()
                and not (UUID.fullmatch(ident) and _aria_pane('noobia-aria-' + ident))):
            raise ValueError('Unknown Aria conversation')
        if ident != NEW_CONVERSATION:
            session = 'noobia-aria-' + ident
            pane = _aria_pane(session)
            if not pane:
                pane = next((candidate for name in _tmux_sessions('noobia-aria-')
                             if (candidate := _aria_pane(name))
                             and _aria_pane_conversation(candidate) == ident), None)
            if not pane:
                process = subprocess.run(['/noobia/aria/codex-with-dushich', '--detached',
                                          '--resume', ident], capture_output=True, text=True,
                                         timeout=30, check=False)
                if process.returncode:
                    raise ValueError(process.stderr.strip() or 'Could not reopen Aria conversation')
                pane = _wait_for_aria(session)
            _send_tmux(pane, message)
            actual = _aria_pane_conversation(pane) or ident
            return 'noobia-aria-' + actual
        process = subprocess.run(['/noobia/aria/codex-with-dushich', '--detached'],
                                 capture_output=True, text=True, timeout=30, check=False)
        if process.returncode:
            raise ValueError(process.stderr.strip() or 'Could not start Aria conversation')
        match = re.search(r'noobia-aria-([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})', process.stdout)
        if not match:
            raise ValueError('Aria session started without a known terminal')
        session = match.group(0)
        pane = _aria_pane(session)
        if not pane:
            raise ValueError('New Aria Codex pane is unavailable; message was not sent')
        _send_tmux(pane, message)
        return session

    has_tokens = True

    def tokens(self, ident: str) -> dict | None:
        known_paths = self._paths()
        if ident != NEW_CONVERSATION:
            if ident not in known_paths and not (UUID.fullmatch(ident) and _aria_pane('noobia-aria-' + ident)):
                return None
        candidates = sorted(
            (p for p in known_paths.values() if p.is_file()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        rate_limits = None
        for path in candidates[:15]:
            found = None
            try:
                with path.open(encoding='utf-8') as stream:
                    for line in stream:
                        if 'token_count' in line:
                            try:
                                item = json.loads(line)
                                payload = item.get('payload') or {}
                                if payload.get('type') == 'token_count':
                                    rl = payload.get('rate_limits') or {}
                                    if rl.get('primary') or rl.get('secondary'):
                                        found = rl
                            except ValueError:
                                continue
            except OSError:
                continue
            if found:
                rate_limits = found
                break
        primary = (rate_limits or {}).get('primary') or {}
        secondary = (rate_limits or {}).get('secondary') or {}
        hourly = (round(100.0 - float(primary['used_percent']), 2)
                  if 'used_percent' in primary else None)
        weekly = (round(100.0 - float(secondary['used_percent']), 2)
                  if 'used_percent' in secondary else None)
        known = [v for v in (weekly, hourly) if v is not None]
        pct = min(known) if known else 100.0
        return {
            'weekly_remaining_percent': weekly,
            'hourly_remaining_percent': hourly,
            'percent_remaining': pct,
            'weekly_resets_at': secondary.get('resets_at'),
            'hourly_resets_at': primary.get('resets_at'),
        }


class BansheePlugin:
    id = 'banshee'
    name = 'Banshee + Dushich'
    color = 'blue'

    def _history(self) -> dict[str, list[float]]:
        prompts = {}
        if HISTORY.is_file():
            for line in HISTORY.read_text(encoding='utf-8').splitlines():
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                if item.get('workspace') == str(BANSHEE_WORKSPACE) and not item.get('type'):
                    prompts.setdefault(item.get('display', ''), []).append(item.get('timestamp', 0) / 1000)
        return prompts

    def _paths(self) -> dict[str, Path]:
        prompts = self._history()
        paths = {}
        for path in CONVERSATIONS.glob('*.db'):
            if not UUID.fullmatch(path.stem):
                continue
            try:
                turns = agy_turns(path)
                if any(t['role'] == 'noob' and t['text'] in prompts for t in turns):
                    paths[path.stem] = path
            except (OSError, ValueError, sqlite3.Error):
                continue
        return paths

    def _live(self) -> dict[str, str]:
        live = {}
        latest = latest_for_workspace(BANSHEE_WORKSPACE, HISTORY)
        for session in _tmux_sessions('noobia-banshee-'):
            proc = subprocess.run(['tmux', 'display-message', '-p', '-t', session + ':0.0', '#{pane_pid}'],
                                  capture_output=True, text=True, check=False)
            try:
                pid = int(proc.stdout.strip())
            except ValueError:
                continue
            ident = ''
            for source in ('environ', 'cmdline'):
                try:
                    parts = Path(f'/proc/{pid}/{source}').read_bytes().split(b'\0')
                    value = next((part.split(b'=', 1)[1] for part in parts
                                  if part.startswith(b'NOOBIA_BANSHEE_CONVERSATION_ID=')), b'')
                    if value:
                        ident = value.decode()
                        break
                except OSError:
                    continue
            try:
                if not ident:
                    short = session.removeprefix('noobia-banshee-')
                    jobs = sorted(Path('/noobia/banshee/private/task-runs').glob('*/state.json'),
                                  reverse=True)
                    for job in jobs:
                        state = json.loads(job.read_text(encoding='utf-8'))
                        if state.get('session_id', '').startswith(short) and state.get('conversation_id'):
                            ident = state['conversation_id']
                            break
                if not ident and latest and latest.stem not in live:
                    ident = latest.stem
                if UUID.fullmatch(ident):
                    live[ident] = session
            except (OSError, ValueError, sqlite3.Error):
                continue
        return live

    def conversations(self) -> list[dict]:
        live = self._live()
        paths = sorted(self._paths().items(), key=lambda item: item[1].stat().st_mtime, reverse=True)
        result = []
        for ident, path in paths[:40]:
            turns = agy_turns(path)
            first = next((t['text'] for t in turns if t['role'] == 'noob'), 'Antigravity conversation')
            result.append({'id': ident, 'label': first[:72], 'active': ident in live})
        return result

    def timeline(self, ident: str) -> list[dict]:
        path = self._paths().get(ident)
        if not path or not UUID.fullmatch(ident):
            raise ValueError('Unknown Banshee conversation')
        history = self._history()
        turns = agy_turns(path)
        result = []
        last_user_time = 0
        for turn in turns:
            if turn['role'] == 'noob':
                choices = history.get(turn['text'], [])
                last_user_time = next((t for t in choices if t > last_user_time), path.stat().st_mtime)
                timestamp = last_user_time
            else:
                future = [t for values in history.values() for t in values if t > last_user_time]
                timestamp = (min(future) - 0.001 if future
                             else max(path.stat().st_mtime, last_user_time + 0.001))
            result.append({'role': turn['role'], 'text': turn['text'], 'time': timestamp,
                           'step': turn['index']})
        live_session = self._live().get(ident)
        for job in Path('/noobia/banshee/private/task-runs').glob('*/state.json'):
            try:
                state = json.loads(job.read_text(encoding='utf-8'))
                matching_live = ('noobia-banshee-' + state.get('session_id', '')[:8] == live_session)
                if state.get('conversation_id') != ident and not matching_live:
                    continue
                result += _job_results(job.parent.parent, 'session_id', state['session_id'])
                break
            except (OSError, ValueError, sqlite3.Error):
                continue
        return sorted(result, key=lambda event: event['time'])[-300:]

    def send(self, ident: str, message: str) -> str:
        if ident != NEW_CONVERSATION and ident not in self._paths():
            raise ValueError('Unknown Banshee conversation')
        prior_step = max((turn['index'] for turn in agy_turns(self._paths()[ident])), default=-1) if ident != NEW_CONVERSATION else -1
        session = None if ident == NEW_CONVERSATION else self._live().get(ident)
        if not session:
            command = ['/noobia/banshee/launch', '--detached']
            if ident != NEW_CONVERSATION:
                command += ['--conversation', ident]
            process = subprocess.run(command,
                                     capture_output=True, text=True, timeout=25, check=False)
            if process.returncode:
                raise ValueError(process.stderr.strip() or 'Could not resume Banshee conversation')
            match = re.search(r'noobia-banshee-[0-9a-f]{8}', process.stdout)
            if not match:
                raise ValueError('Banshee session started without a known terminal')
            session = match.group(0)
            _wait_for_banshee(session)
        if not _banshee_pane_alive(session):
            raise ValueError('Banshee terminal exited before the message was sent')
        _send_tmux(session, message)
        if ident != NEW_CONVERSATION:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if any(turn['index'] > prior_step and turn['role'] == 'noob'
                       and turn['text'] == message for turn in agy_turns(self._paths()[ident])):
                    return session
                if not _banshee_pane_alive(session):
                    raise ValueError('Banshee terminal exited without recording the message')
                time.sleep(0.25)
            raise ValueError('Banshee did not record the message; check the conversation before retrying')
        return session

    has_tokens = True

    def tokens(self, ident: str) -> dict | None:
        if ident != NEW_CONVERSATION:
            if not UUID.fullmatch(ident):
                return None
            transcript = BANSHEE_BRAIN / ident / '.system_generated' / 'logs' / 'transcript.jsonl'
            if not transcript.is_file() and ident not in self._paths() and ident not in self._live():
                return None
        return _banshee_quota()


def _parse_banshee_usage(output: str) -> dict | None:
    """Read the Gemini group from agy's own /usage output, without handling tokens."""
    weekly = hourly = weekly_reset = hourly_reset = None
    for line in output.splitlines():
        fields = line.split('\t')
        if len(fields) != 4 or fields[0].strip().lower() != 'gemini models':
            continue
        try:
            remaining = float(fields[2].strip().removesuffix('%'))
        except ValueError:
            continue
        if not 0 <= remaining <= 100:
            continue
        window = fields[1].strip().lower()
        if 'weekly' in window:
            weekly, weekly_reset = remaining, fields[3].strip()
        elif 'five hour' in window or '5 hour' in window:
            hourly, hourly_reset = remaining, fields[3].strip()
    known = [value for value in (weekly, hourly) if value is not None]
    if not known:
        return None
    return {
        'weekly_remaining_percent': weekly,
        'hourly_remaining_percent': hourly,
        'percent_remaining': min(known),
        'weekly_resets_at': weekly_reset,
        'hourly_resets_at': hourly_reset,
    }


def _banshee_quota() -> dict | None:
    now = time.monotonic()
    if now - _BANSHEE_QUOTA_CACHE.get('time', 0.0) < 30.0:
        return _BANSHEE_QUOTA_CACHE.get('data')
    try:
        process = subprocess.run(
            ['/home/aria/.local/bin/agy', '--print', '/usage', '--print-timeout', '15s'],
            cwd=BANSHEE_WORKSPACE, capture_output=True, text=True, timeout=18,
            check=False,
        )
        result = _parse_banshee_usage(process.stdout) if process.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        result = None
    _BANSHEE_QUOTA_CACHE.update(time=now, data=result)
    return result


class DushichSoloPlugin:
    id = 'dushich_solo'
    name = 'Dushich · Solo'
    color = 'green'
    prefix = 'noobia-dushich-solo-'
    registry = Path('/noobia/dushich/solo/private/conversations.json')
    solo_sessions = Path('/noobia/dushich/solo/private/codex/sessions')

    def _registered(self) -> list[str]:
        try:
            value = json.loads(self.registry.read_text(encoding='utf-8'))
        except FileNotFoundError:
            return []
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, str) and UUID.fullmatch(item)]

    def _paths(self) -> dict[str, Path]:
        known = set(self._registered())
        if not known:
            return {}
        paths = {}
        for root in (Path('/noobia/dushich/coding/private/codex/sessions'), self.solo_sessions):
            for path in root.glob('**/rollout-*.jsonl'):
                match = re.search(r'([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})\.jsonl$', path.name)
                if match and match.group(1) in known:
                    paths[match.group(1)] = path
        return paths

    def conversations(self) -> list[dict]:
        active = {name.removeprefix(self.prefix) for name in _tmux_sessions(self.prefix)}
        paths = self._paths()
        return [{'id': ident, 'label': 'Solo Dushich · ' + ident[:8],
                 'active': ident in active}
                for ident in reversed(self._registered()) if ident in paths or ident in active]

    def timeline(self, ident: str) -> list[dict]:
        if ident not in self._registered():
            raise ValueError('Unknown solo Dushich conversation')
        path = self._paths().get(ident)
        if not path:
            return []
        try:
            raw = path.read_text(encoding='utf-8')
        except OSError as exc:
            raise ValueError('Solo Dushich transcript is unavailable') from exc
        events = []
        for line in raw.splitlines():
            try:
                item = json.loads(line)
            except ValueError:
                continue
            payload = item.get('payload') or {}
            if item.get('type') != 'response_item' or payload.get('type') != 'message':
                continue
            role = payload.get('role')
            if role not in ('user', 'assistant'):
                continue
            kind = 'input_text' if role == 'user' else 'output_text'
            message = '\n'.join(part.get('text', '') for part in payload.get('content', [])
                                if isinstance(part, dict) and part.get('type') == kind).strip()
            if not message or message.startswith(('# AGENTS.md instructions', '<environment_context>')):
                continue
            events.append({'role': 'noob' if role == 'user' else 'dushich',
                           'text': message, 'time': _timestamp(item.get('timestamp'))})
        return events[-300:]

    def send(self, ident: str, message: str) -> str:
        if ident != NEW_CONVERSATION and ident not in self._registered():
            raise ValueError('Unknown solo Dushich conversation')
        prior_count = sum(turn['role'] == 'noob' and turn['text'] == message
                          for turn in self.timeline(ident)) if ident != NEW_CONVERSATION else 0
        if ident == NEW_CONVERSATION:
            command = ['/noobia/dushich/solo/launch', '--detached']
            session = None
        else:
            command = ['/noobia/dushich/solo/launch', '--detached', '--resume', ident]
            session = self.prefix + ident if self.prefix + ident in _tmux_sessions(self.prefix) else None
        if not session:
            process = subprocess.run(command, capture_output=True, text=True,
                                     timeout=30, check=False)
            if process.returncode:
                raise ValueError(process.stderr.strip() or 'Could not start solo Dushich')
            match = re.search(self.prefix + r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',
                              process.stdout)
            if not match:
                raise ValueError('Solo Dushich started without a known terminal')
            session = match.group(0)
            _wait_for_codex(session)
        if session not in _tmux_sessions(self.prefix):
            raise ValueError('Solo Dushich terminal exited before the message was sent')
        _send_tmux(session, message)
        conversation = session.removeprefix(self.prefix)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            seen = sum(turn['role'] == 'noob' and turn['text'] == message
                       for turn in self.timeline(conversation))
            if seen > prior_count:
                return session
            if session not in _tmux_sessions(self.prefix):
                raise ValueError('Solo Dushich terminal exited without recording the message')
            time.sleep(0.25)
        raise ValueError('Solo Dushich did not record the message; check the conversation before retrying')

    has_tokens = False

    def tokens(self, ident: str) -> dict | None:
        return None


def _send_tmux(session: str, message: str) -> None:
    # -l passes the user's text literally; no shell interpolation or tmux key names.
    target = session if session.startswith('%') else session + ':0.0'
    tmux = ['tmux', '-L', 'dushich-clean'] if session.startswith('noobia-dushich-solo-') else ['tmux']
    subprocess.run(tmux + ['send-keys', '-l', '-t', target, '--', message],
                   check=True, timeout=5)
    time.sleep(0.2)
    subprocess.run(tmux + ['send-keys', '-t', target, 'Enter'],
                   check=True, timeout=5)


def _wait_for_banshee(session: str) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if not _banshee_pane_alive(session):
            raise ValueError('Banshee terminal exited before it became ready')
        pane = subprocess.run(['tmux', 'capture-pane', '-pt', session + ':0.0', '-S', '-10'],
                              capture_output=True, text=True, check=False)
        if pane.returncode == 0 and '? for shortcuts' in pane.stdout:
            return
        time.sleep(0.25)
    raise ValueError('Banshee terminal did not become ready; the session remains available')


def _banshee_pane_alive(session: str) -> bool:
    process = subprocess.run(['tmux', 'display-message', '-p', '-t', session + ':0.0',
                              '#{pane_current_command}'], capture_output=True, text=True,
                             check=False)
    return process.returncode == 0 and process.stdout.strip() in ('sudo', 'agy')


def _wait_for_codex(session: str) -> None:
    tmux = ['tmux', '-L', 'dushich-clean']
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        pane = subprocess.run(tmux + ['capture-pane', '-pt', session + ':0.0', '-S', '-10'],
                              capture_output=True, text=True, check=False)
        if pane.returncode == 0 and 'Ask Codex to do anything' in pane.stdout:
            return
        time.sleep(0.25)
    raise ValueError('Dushich terminal did not become ready; the session remains available')


def _wait_for_aria(session: str) -> str:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        pane = _aria_pane(session)
        if pane:
            screen = subprocess.run(['tmux', 'capture-pane', '-pt', pane, '-S', '-10'],
                                    capture_output=True, text=True, check=False)
            if screen.returncode == 0 and 'Ask Codex to do anything' in screen.stdout:
                return pane
        time.sleep(0.25)
    raise ValueError('Aria terminal did not become ready; the conversation remains available')


PLUGINS = {item.id: item for item in (AriaPlugin(), BansheePlugin(), DushichSoloPlugin())}
