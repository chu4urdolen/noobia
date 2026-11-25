#!/usr/bin/env python3
"""Single supervised worker for private Lynx agent jobs."""

import hashlib
import hmac
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import unicodedata
import urllib.error
import urllib.request

from lynx_agent_queue import JobQueue, QueueError


def sanitize_text(text: str) -> str:
    """Sanitize text: remove emojis and replace em-dashes/en-dashes with comma."""
    import re
    text = text.replace("—", ",").replace("–", ",")
    text = re.sub(r'\s*,\s*', ', ', text)
    out = []
    for ch in text:
        cat = unicodedata.category(ch)
        if cat.startswith("S") or cat in ("So", "Sk", "Sm", "Sc"):
            continue
        out.append(ch)
    return "".join(out).strip()

ROOT = Path('/var/lib/lynx-agent/jobs')
STOP = Path('/var/lib/lynx-agent/stop')
THOUGHT_PATH = Path('/var/lib/noobia/lynx_thought.txt')
AGENT = '/usr/local/bin/lynx-agent'
# LNX-73: run the agent as this unprivileged user (all capabilities gone,
# no_new_privs); its tools then go through lynx-tool-broker. Empty = as today
# (root). BusyBox setpriv has no --reuid, so Python drops the privileges itself.
AGENT_USER = os.environ.get('LYNX_AGENT_USER', '')
PR_SET_NO_NEW_PRIVS = 38


def agent_command(user=None):
    return ['/usr/bin/python3', AGENT, '--stdin']


def _no_new_privs():
    import ctypes
    if ctypes.CDLL(None, use_errno=True).prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), 'prctl(NO_NEW_PRIVS) failed')


def agent_privileges(user=None):
    """Popen arguments that run the agent as USER: setgroups([]), setgid, setuid.
    A root process that switches to a non-zero uid loses every capability."""
    import pwd
    user = AGENT_USER if user is None else user
    if not user:
        return {}
    pw = pwd.getpwnam(user)
    if pw.pw_uid == 0:
        raise ValueError('LYNX_AGENT_USER must not be root')
    return {'user': pw.pw_uid, 'group': pw.pw_gid, 'extra_groups': [],
            'preexec_fn': _no_new_privs}
LOCAL = 'http://192.168.100.106:8080'
LOCAL_KEY = Path('/etc/lynx/nexus-inference.key')
CLOUD_KEY = Path('/etc/lynx/openai.key')
AIGEL_KEY = Path('/etc/noobia/aigel-lynx.secret')


def agent_response_headers(payload: bytes, key_path: Path = AIGEL_KEY) -> dict:
    """Sign the exact response body with Lynx's existing Aigel host key."""
    secret = key_path.read_text(encoding='utf-8').strip()
    if not secret:
        raise ValueError('Aigel host key is empty')
    signature = hmac.new(secret.encode('utf-8'), payload, hashlib.sha256).hexdigest()
    return {'Content-Type': 'application/json', 'X-Noobia-Signature': signature}


current = None
stopping = False


def key_from(path):
    key = path.read_text().strip()
    if not key or len(key) > 512 or '\n' in key or '\r' in key:
        raise RuntimeError('Invalid inference credential')
    return key


def stop(_signum, _frame):
    global stopping
    stopping = True
    if current is not None and current.poll() is None:
        try:
            os.killpg(current.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


def ready():
    if Path('/etc/lynx/power-thermal-guard.disable').exists():
        return True
    try:
        result = subprocess.run(['/usr/local/bin/lynx-status', '--assert-ready'],
                                capture_output=True, timeout=8, check=True)
        state = json.loads(result.stdout)
        battery = state['battery']
        return (not state['issues'] and battery['capacity_percent'] >= 25 and
                battery['temperature_mC'] < 35_000 and
                state['thermal']['max_mC'] < 50_000 and
                (battery['current_mA_signed'] >= 100 or
                 battery['capacity_percent'] >= 40))
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        return False


def inference_ready():
    """Keep a queued job pending until its selected inference path can start."""
    try:
        with urllib.request.urlopen(LOCAL + '/health', timeout=2) as response:
            if response.status != 200:
                return False
        key_from(LOCAL_KEY)
        return True
    except urllib.error.HTTPError:
        # Nexus answered but its proxy is unhealthy; never spend cloud credits.
        return False
    except (OSError, urllib.error.URLError):
        try:
            key_from(CLOUD_KEY)
            return True
        except (OSError, RuntimeError):
            return False
    except RuntimeError:
        return False


def run_job(queue, job_id, prompt):
    global current
    print(json.dumps({'event': 'job_started', 'job_id': job_id}), flush=True)
    try:
        if stopping:
            queue.finish(job_id, False, 'Agent stopped')
            return
        try:
            current = subprocess.Popen(agent_command(),
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, start_new_session=True,
                                       **agent_privileges())
        except (OSError, KeyError, ValueError, subprocess.SubprocessError):
            queue.finish(job_id, False, 'Agent executable unavailable')
            print(json.dumps({'event': 'job_finished', 'job_id': job_id,
                              'ok': False, 'reason': 'executable_unavailable'}), flush=True)
            return
        if stopping and current.poll() is None:
            try:
                os.killpg(current.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        thought_path = THOUGHT_PATH
        thought_mtime_before = thought_path.stat().st_mtime_ns if thought_path.is_file() else 0
        thought_size_before = thought_path.stat().st_size if thought_path.is_file() else 0
        try:
            output, errors = current.communicate(input=prompt.encode('utf-8'), timeout=180)
        except subprocess.TimeoutExpired:
            os.killpg(current.pid, signal.SIGKILL)
            output, errors = current.communicate()
            queue.finish(job_id, False, 'Agent job timed out')
            print(json.dumps({'event': 'job_finished', 'job_id': job_id,
                              'ok': False, 'reason': 'timeout'}), flush=True)
            return
        thought_mtime_after = thought_path.stat().st_mtime_ns if thought_path.is_file() else 0
        thought_size_after = thought_path.stat().st_size if thought_path.is_file() else 0
        thought_written_by_tool = (thought_mtime_after > thought_mtime_before or
                                  thought_size_after > thought_size_before)
        ok = current.returncode == 0 and not stopping
        text = (output if ok else errors or output).decode(errors='replace')[-8000:]
        queue.finish(job_id, ok, text or ('Agent stopped' if stopping else 'No response'),
                     reply_pending=bool(ok and text))
        print(json.dumps({'event': 'job_finished', 'job_id': job_id, 'ok': ok}), flush=True)
        if ok and text:
            clean_text = text.strip()
            # If a tool (like lynx_speech) already recorded Lynx's spoken thought during this
            # turn, do not append clean_text (which is just the final assistant summary/duplicate).
            # Only append if no tool wrote to thought_path (i.e. silent thought).
            if not thought_written_by_tool and clean_text:
                clean_thought = sanitize_text(clean_text)
                if clean_thought:
                    try:
                        existing = thought_path.read_text(encoding='utf-8', errors='replace') if thought_path.is_file() else ''
                        existing_stripped = existing.strip()
                        if not existing_stripped.endswith(clean_thought):
                            with thought_path.open('a', encoding='utf-8') as f:
                                if existing and not existing.endswith('\n'):
                                    f.write('\n')
                                f.write(clean_thought + '\n')
                    except Exception:
                        pass
    finally:
        current = None


def deliver_replies(queue):
    """Retry durable results; server deduplicates by job ID after ambiguous sends."""
    try:
        pending = queue.pending_replies(limit=2)
    except (OSError, ValueError, QueueError) as exc:
        print(json.dumps({"event": "reply_queue_error",
                          "reason": type(exc).__name__}), flush=True)
        return
    for job_id, text in pending:
        try:
            payload = json.dumps({"host": "lynx", "job_id": job_id,
                                  "text": text.strip(), "t": time.time()}).encode("utf-8")
            req = urllib.request.Request(
                "http://192.168.100.106:112/api/v1/agent_response",
                data=payload, headers=agent_response_headers(payload))
            with urllib.request.urlopen(req, timeout=3) as response:
                if response.status != 200:
                    raise RuntimeError("Aigel reply rejected")
            queue.mark_reply_sent(job_id)
        except (OSError, ValueError, RuntimeError, urllib.error.URLError,
                QueueError) as exc:
            print(json.dumps({"event": "reply_retry_pending", "job_id": job_id,
                              "reason": type(exc).__name__}), flush=True)
            break


def main():
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    queue = JobQueue(ROOT)
    for orphan in sorted(ROOT.glob('*.running')):
        try:
            queue.finish(orphan.stem, False, 'Worker restarted before completion')
        except QueueError:
            print(json.dumps({'event': 'orphan_recovery_failed',
                              'job_id': orphan.stem}), flush=True)
    next_reply_attempt = 0.0
    while not stopping:
        if time.monotonic() >= next_reply_attempt:
            deliver_replies(queue)
            next_reply_attempt = time.monotonic() + 30
        if STOP.exists() or not any(ROOT.glob('*.pending')):
            time.sleep(2)
            continue
        if not ready():
            time.sleep(5)
            continue
        if not inference_ready():
            time.sleep(10)
            continue
        job = queue.claim_next()
        if job is None:
            time.sleep(2)
            continue
        run_job(queue, *job)


if __name__ == '__main__':
    main()
