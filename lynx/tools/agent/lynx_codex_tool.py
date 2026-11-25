#!/usr/bin/env python3
"""Run one bounded Codex task as Lynx's unprivileged coding user."""

import json
import os
from pathlib import Path
import pwd
import signal
import subprocess
import sys

CODEX = Path('/usr/local/libexec/lynx/codex')
WORK = Path('/home/lynx-coder/work')
HOME = Path('/home/lynx-coder')
KEY_FILE = Path('/home/lynx-coder/.config/noobia/nexus.key')


def run(request):
    if not isinstance(request, dict) or set(request) - {'prompt', 'model'}:
        raise ValueError('Invalid Codex request')
    prompt = request.get('prompt')
    model = request.get('model', 'qwen3.8-27b')
    if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 2000:
        raise ValueError('Prompt length must be 1..2000 characters')
    if model in ('gpt-oss-20b', 'qwen3.8-27b'):
        model = 'qwen3.8-27b'
    else:
        raise ValueError('Model unavailable on this Codex installation')
    if not CODEX.is_file() or not os.access(CODEX, os.X_OK):
        raise RuntimeError('Persistent Codex binary unavailable')
    user = pwd.getpwnam('lynx-coder')
    if user.pw_uid == 0 or not WORK.is_dir() or WORK.stat().st_uid != user.pw_uid:
        raise RuntimeError('Unprivileged Codex workspace unavailable')

    key = ""
    if KEY_FILE.exists():
        key = KEY_FILE.read_text(encoding="utf-8").strip()

    command = [str(CODEX), 'exec', '--skip-git-repo-check', '-s', 'danger-full-access',
               '-m', model, '-C', str(WORK), prompt]
    env = {
        'HOME': str(HOME),
        'PATH': '/usr/local/bin:/usr/bin:/bin',
        'CODEX_HOME': str(HOME / '.codex'),
        'NEXUS_KEY': key,
    }
    process = subprocess.Popen(
        command,
        cwd=WORK,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
        user=user.pw_uid,
        group=user.pw_gid,
    )
    try:
        out, err = process.communicate(timeout=180)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        raise RuntimeError('Codex task timed out') from None
    if process.returncode:
        raise RuntimeError('Codex task failed: ' + err[-600:])
    return {'ok': True, 'model': model, 'output': out[-4000:],
            'workspace': str(WORK), 'user': 'lynx-coder'}


def main():
    try:
        request = json.load(sys.stdin)
        print(json.dumps(run(request)))
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}))
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
