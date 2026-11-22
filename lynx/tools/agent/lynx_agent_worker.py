#!/usr/bin/env python3
"""Single supervised worker for private Lynx agent jobs."""

import json
import os
from pathlib import Path
import signal
import subprocess
import time
import urllib.error
import urllib.request

from lynx_agent_queue import JobQueue, QueueError

ROOT = Path('/var/lib/lynx-agent/jobs')
STOP = Path('/var/lib/lynx-agent/stop')
AGENT = '/usr/local/bin/lynx-agent'
LOCAL = 'http://192.168.100.106:8080'
LOCAL_KEY = Path('/etc/lynx/nexus-inference.key')
CLOUD_KEY = Path('/etc/lynx/openai.key')
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
            current = subprocess.Popen(['/usr/bin/python3', AGENT, '--stdin'],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, start_new_session=True)
        except OSError:
            queue.finish(job_id, False, 'Agent executable unavailable')
            print(json.dumps({'event': 'job_finished', 'job_id': job_id,
                              'ok': False, 'reason': 'executable_unavailable'}), flush=True)
            return
        if stopping and current.poll() is None:
            try:
                os.killpg(current.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        try:
            output, errors = current.communicate(input=prompt.encode('utf-8'), timeout=180)
        except subprocess.TimeoutExpired:
            os.killpg(current.pid, signal.SIGKILL)
            output, errors = current.communicate()
            queue.finish(job_id, False, 'Agent job timed out')
            print(json.dumps({'event': 'job_finished', 'job_id': job_id,
                              'ok': False, 'reason': 'timeout'}), flush=True)
            return
        ok = current.returncode == 0 and not stopping
        text = (output if ok else errors or output).decode(errors='replace')[-8000:]
        queue.finish(job_id, ok, text or ('Agent stopped' if stopping else 'No response'))
        print(json.dumps({'event': 'job_finished', 'job_id': job_id, 'ok': ok}), flush=True)
        if ok and text:
            clean_text = text.strip()
            try:
                thought_path = Path('/var/lib/noobia/lynx_thought.txt')
                existing = thought_path.read_text(encoding='utf-8', errors='replace') if thought_path.is_file() else ''
                existing_stripped = existing.strip()
                if not existing_stripped.endswith(clean_text):
                    with thought_path.open('a', encoding='utf-8') as f:
                        if existing and not existing.endswith('\n'):
                            f.write('\n')
                        f.write(clean_text + '\n')
            except Exception:
                pass
            try:
                payload = json.dumps({
                    "host": "lynx",
                    "job_id": job_id,
                    "text": clean_text,
                    "t": time.time(),
                }).encode("utf-8")
                req = urllib.request.Request(
                    "http://192.168.100.106:112/api/v1/agent_response",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=3):
                    pass
            except Exception:
                pass
    finally:
        current = None


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
    while not stopping:
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
