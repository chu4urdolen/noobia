#!/usr/bin/env python3
"""Single supervised worker for private Lynx agent jobs.

This is a copy of the production worker used on Lynx.  It is included in
the Dushich workspace so that the test suite can exercise the logic
without importing from the shared repository.
"""

import json
import os
from pathlib import Path
import signal
import subprocess
import time

from lynx_agent_queue import JobQueue, QueueError

ROOT = Path('/var/lib/lynx-agent/jobs')
STOP = Path('/var/lib/lynx-agent/stop')
AGENT = '/usr/local/bin/lynx-agent'
current = None
stopping = False


def stop(_signum, _frame):
    global stopping
    stopping = True
    if current is not None and current.poll() is None:
        os.killpg(current.pid, signal.SIGTERM)


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


def run_job(queue, job_id, prompt):
    global current
    print(json.dumps({'event': 'job_started', 'job_id': job_id}), flush=True)
    try:
        current = subprocess.Popen(['/usr/bin/python3', AGENT, '--stdin'],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, start_new_session=True)
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
        if STOP.exists() or not ready():
            time.sleep(5)
            continue
        job = queue.claim_next()
        if job is None:
            time.sleep(2)
            continue
        run_job(queue, *job)


if __name__ == '__main__':
    main()
