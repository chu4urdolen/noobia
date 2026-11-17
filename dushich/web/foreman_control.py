"""Local, opt-in Foreman control and project routing for the dashboard."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import threading
import time
from uuid import UUID

DB = Path('/noobia/dushich/workspace/forge.db')
FLAGS = Path('/noobia/dushich/workspace/human-help-flags')
PRIVATE = Path('/noobia/dushich/web/private')
STATE = PRIVATE / 'foreman.json'
CODEX = '/opt/noobia/dushich-codex/node_modules/.bin/codex'
CODEX_HOME = '/noobia/dushich/foreman/private/codex'
EXECUTORS = {'aria': 'aria', 'banshee': 'banshee', 'dushich': 'dushich_solo',
             'dushich_solo': 'dushich_solo'}
UUID_PATTERN = re.compile(r'^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$')
NEW_PROJECT = '__new__'
LOCK = threading.RLock()


def _load() -> dict:
    try:
        state = json.loads(STATE.read_text(encoding='utf-8'))
    except (FileNotFoundError, ValueError):
        state = {}
    state.setdefault('selected', {})
    state.setdefault('sessions', {})
    state.setdefault('chat', [])
    state.setdefault('seen', {})
    state.setdefault('help_seen', [])
    state.setdefault('pending_links', {})
    state.setdefault('error', '')
    return state


def _save(state: dict) -> None:
    PRIVATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = STATE.with_suffix('.tmp')
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.chmod(tmp, 0o600)
    tmp.replace(STATE)


STATE_DATA = _load()
ENABLED = False  # Each server start requires a fresh, explicit click by Noob.
BUSY = False


def projects() -> list[dict]:
    if not DB.is_file():
        return []
    with sqlite3.connect(f'file:{DB}?mode=ro', uri=True, timeout=2) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute('SELECT project_name, executor, receiver, description, '
                          'hardware_ready, conversation_id FROM projects ORDER BY project_name')
        result = []
        for row in rows:
            item = dict(row)
            item['agent'] = EXECUTORS.get((item['executor'] or '').strip().lower())
            result.append(item)
        return result


def flags() -> list[dict]:
    found = []
    for path in sorted(FLAGS.glob('*.json')):
        if path.name.endswith('.response.json'):
            continue
        try:
            UUID(path.stem)
            item = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(item, dict):
                continue
            response = path.with_name(path.stem + '.response.json')
            item = {k: item.get(k, '') for k in ('project_name', 'conversation_id', 'request', 'created_at')}
            item['id'] = path.stem
            item['response'] = json.loads(response.read_text(encoding='utf-8')).get('text', '') if response.exists() else ''
            found.append(item)
        except (OSError, ValueError, TypeError):
            continue
    return found[-100:]


def snapshot() -> dict:
    with LOCK:
        all_projects = projects()
        changed = False
        for agent in ('aria', 'banshee', 'dushich_solo'):
            available = [p['project_name'] for p in all_projects if p['agent'] == agent]
            if available and STATE_DATA['selected'].get(agent) not in available + [NEW_PROJECT]:
                STATE_DATA['selected'][agent] = available[0]
                changed = True
        if changed:
            _save(STATE_DATA)
        return {'enabled': ENABLED, 'busy': BUSY, 'selected': dict(STATE_DATA['selected']),
                'chat': list(STATE_DATA['chat'][-100:]), 'error': STATE_DATA['error'],
                'projects': all_projects, 'flags': flags(),
                'pending_links': dict(STATE_DATA['pending_links'])}


def select_project(agent: str, project_name: str) -> None:
    if agent not in ('aria', 'banshee', 'dushich_solo'):
        raise ValueError('Unknown coding agent')
    matching = next((p for p in projects() if p['project_name'] == project_name and p['agent'] == agent), None)
    if project_name != NEW_PROJECT and matching is None:
        raise ValueError('Project does not belong to this coding agent')
    with LOCK:
        STATE_DATA['selected'][agent] = project_name
        STATE_DATA['seen'].pop(agent, None)
        _save(STATE_DATA)


def respond_to_flag(ident: str, response: str) -> None:
    if not UUID_PATTERN.fullmatch(ident):
        raise ValueError('Invalid help request')
    if not response.strip() or len(response) > 4000:
        raise ValueError('Enter a response up to 4000 characters')
    path = FLAGS / (ident + '.json')
    if not path.is_file():
        raise ValueError('Help request no longer exists')
    output = FLAGS / (ident + '.response.json')
    if output.exists():
        raise ValueError('This request already has a response')
    tmp = FLAGS / (ident + '.response.tmp')
    tmp.write_text(json.dumps({'text': response, 'time': datetime.now(timezone.utc).isoformat()}) + '\n', encoding='utf-8')
    tmp.replace(output)


def _run_foreman(key: str, prompt: str) -> str:
    with LOCK:
        session = STATE_DATA['sessions'].get(key)
    command = [CODEX, '--oss', '--local-provider', 'ollama', '--model', 'gpt-oss:20b',
               '--sandbox', 'workspace-write', '--ask-for-approval', 'never', 'exec', '--json']
    if session:
        command += ['resume', session, prompt]
    else:
        command += [prompt]
    env = {'HOME': '/home/aria', 'USER': 'aria', 'LOGNAME': 'aria', 'CODEX_HOME': CODEX_HOME,
           'GIT_DIR': '/noobia/dushich/workspace/.dushich-git',
           'GIT_WORK_TREE': '/noobia/dushich/workspace', 'OLLAMA_HOST': 'http://127.0.0.1:11434',
           'PATH': '/opt/noobia/dushich-codex/node_modules/.bin:/usr/local/bin:/usr/bin:/bin',
           'LANG': 'C.UTF-8'}
    process = subprocess.run(command, cwd='/noobia/dushich/workspace', env=env,
                             capture_output=True, text=True, timeout=300, check=False)
    messages = []
    for line in process.stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get('type') == 'thread.started' and UUID_PATTERN.fullmatch(event.get('thread_id', '')):
            with LOCK:
                STATE_DATA['sessions'][key] = event['thread_id']
                _save(STATE_DATA)
        item = event.get('item') or {}
        if event.get('type') == 'item.completed' and item.get('type') == 'agent_message':
            messages.append(item.get('text', ''))
    if process.returncode:
        raise RuntimeError((process.stderr or 'Foreman run failed').strip()[-1000:])
    return '\n'.join(messages).strip() or '(Foreman finished without a visible reply.)'


def _job(key: str, prompt: str, agent: str | None = None, conversation: str | None = None) -> None:
    global BUSY
    try:
        reply = _run_foreman(key, prompt)
        with LOCK:
            STATE_DATA['chat'].append({'role': 'foreman', 'text': reply, 'time': time.time(),
                                       'project': key if agent else ''})
            STATE_DATA['error'] = ''
            _save(STATE_DATA)
        if agent and conversation and ENABLED:
            from plugins import PLUGINS
            PLUGINS[agent].send(conversation, '[Foreman Dushich] ' + reply.replace('\n', ' '))
    except Exception as exc:
        with LOCK:
            STATE_DATA['error'] = f'{type(exc).__name__}: {exc}'
            _save(STATE_DATA)
    finally:
        with LOCK:
            BUSY = False


def _start(key: str, prompt: str, agent: str | None = None, conversation: str | None = None) -> None:
    global BUSY
    with LOCK:
        if not ENABLED:
            raise ValueError('Enable Foreman first')
        if BUSY:
            raise ValueError('Foreman is finishing another turn')
        BUSY = True
    threading.Thread(target=_job, args=(key, prompt, agent, conversation), daemon=True).start()


def set_enabled(value: bool) -> None:
    global ENABLED
    with LOCK:
        if ENABLED == value:
            return
        ENABLED = value
        STATE_DATA['error'] = ''
    if value:
        _start('_front', 'You have just been enabled by Noob. First inspect forge.db. '
               'Assign every project with no executor according to your AGENTS.md ranking; '
               'preserve existing assignments. Verify database changes, then report what you did. '
               'If no project is unassigned, say so. Do not perform physical actions.')


def send_chat(message: str) -> None:
    if not message.strip() or len(message) > 16000:
        raise ValueError('Enter a message up to 16000 characters')
    _start('_front', message)
    with LOCK:
        STATE_DATA['chat'].append({'role': 'noob', 'text': message, 'time': time.time()})
        _save(STATE_DATA)


def active_conversations() -> dict[str, str]:
    chosen = snapshot()['selected']
    result = {p['agent']: p['conversation_id'] for p in projects()
            if p['agent'] and chosen.get(p['agent']) == p['project_name'] and p['conversation_id']}
    if 'aria' in result:
        from plugins import _aria_pane, _aria_pane_conversation
        pane = _aria_pane('noobia-aria-' + result['aria'])
        if pane:
            result['aria'] = _aria_pane_conversation(pane) or result['aria']
    result.update({agent: 'new' for agent, project in chosen.items() if project == NEW_PROJECT})
    return result


def wants_new_project(agent: str) -> bool:
    with LOCK:
        return STATE_DATA['selected'].get(agent) == NEW_PROJECT


def _bind_project(agent: str, conversation: str, description: str) -> None:
    if agent not in ('aria', 'banshee', 'dushich_solo') or not UUID_PATTERN.fullmatch(conversation):
        raise ValueError('Invalid new project conversation')
    title = f'{agent}-{conversation[:8]}'
    with sqlite3.connect(DB, timeout=10) as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS projects_conversation_id_unique ON projects(conversation_id) WHERE conversation_id IS NOT NULL AND conversation_id <> ''")
        existing = db.execute('SELECT project_name FROM projects WHERE conversation_id=?',
                              (conversation,)).fetchone()
        if existing:
            title = existing[0]
        else:
            db.execute('''INSERT INTO projects
                          (project_name, executor, receiver, description, hardware_ready,
                           agentic_tools, conversation_id) VALUES (?, ?, ?, ?, 0, '[]', ?)''',
                       (title, agent, 'noob', description[:1000], conversation))
        db.commit()
    with LOCK:
        if STATE_DATA['selected'].get(agent) == NEW_PROJECT:
            STATE_DATA['selected'][agent] = title
            STATE_DATA['seen'][agent] = f'new:{conversation}'
        STATE_DATA['pending_links'].pop(agent, None)
        _save(STATE_DATA)


def _link_worker(agent: str) -> None:
    from plugins import PLUGINS
    with LOCK:
        pending = dict(STATE_DATA['pending_links'][agent])
    session = pending['session']
    match = re.search(r'([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})$', session)
    conversation = match.group(1) if match else None
    deadline = time.monotonic() + 1800
    while not conversation and time.monotonic() < deadline:
        try:
            live = PLUGINS[agent]._live() if agent == 'banshee' else {}
            conversation = next((ident for ident, name in live.items()
                                 if name == session and ident not in pending['before']), None)
            if not conversation:
                candidates = [item['id'] for item in PLUGINS[agent].conversations()
                              if item['id'] not in pending['before']]
                if len(candidates) == 1:
                    conversation = candidates[0]
        except (OSError, ValueError, sqlite3.Error):
            pass
        if not conversation:
            time.sleep(1)
    if not conversation:
        with LOCK:
            STATE_DATA['error'] = f'New {agent} conversation started, but its ID was not found; project link is pending.'
            _save(STATE_DATA)
        return
    try:
        _bind_project(agent, conversation, pending['description'])
    except Exception as exc:
        with LOCK:
            STATE_DATA['error'] = f'Conversation started, but project link failed: {exc}'
            _save(STATE_DATA)


def link_new_project(agent: str, session: str, description: str, before: list[str]) -> None:
    with LOCK:
        STATE_DATA['pending_links'][agent] = {'session': session, 'description': description,
                                              'before': before}
        _save(STATE_DATA)
    threading.Thread(target=_link_worker, args=(agent,), daemon=True).start()


def watch_conversations() -> None:
    """Route new coding-agent replies to Foreman while enabled and a project is selected."""
    from plugins import PLUGINS
    while True:
        time.sleep(4)
        if not ENABLED or BUSY:
            continue
        answered = next((flag for flag in flags() if flag['response'] and
                         flag['id'] not in STATE_DATA['help_seen']), None)
        if answered:
            project = next((p for p in projects() if p['project_name'] == answered['project_name']), None)
            agent = project['agent'] if project else None
            conversation = project['conversation_id'] if project else None
            try:
                _start(project['project_name'] if project else '_front',
                       f"Noob responded to human-help request {answered['id']} for project "
                       f"{answered['project_name']}: {answered['response']}. "
                       'Read the flag and continue the project conversation. Do not claim '
                       'the physical step is complete beyond what Noob reported.', agent, conversation)
                with LOCK:
                    STATE_DATA['help_seen'].append(answered['id'])
                    _save(STATE_DATA)
                continue
            except ValueError:
                pass
        for agent, conversation in active_conversations().items():
            try:
                events = PLUGINS[agent].timeline(conversation)
                own_role = 'dushich' if agent == 'dushich_solo' else agent
                latest = next((e for e in reversed(events) if e.get('role') == own_role), None)
                if not latest:
                    continue
                signature = f"{conversation}:{latest.get('time')}:{latest.get('text')}"
                with LOCK:
                    previous = STATE_DATA['seen'].get(agent)
                    STATE_DATA['seen'][agent] = signature
                    _save(STATE_DATA)
                if previous is None or previous == signature:
                    continue
                project = STATE_DATA['selected'][agent]
                _start(project, f'Project {project}; coding agent {agent}; conversation {conversation}. '
                       'The agent just said:\n' + latest['text'] + '\nRespond as Foreman Dushich. '
                       'If Noob must perform a physical step, create a human-help flag and say what is needed.',
                       agent, conversation)
                break
            except (ValueError, KeyError, OSError):
                continue


threading.Thread(target=watch_conversations, daemon=True).start()
for _agent in tuple(STATE_DATA['pending_links']):
    threading.Thread(target=_link_worker, args=(_agent,), daemon=True).start()
