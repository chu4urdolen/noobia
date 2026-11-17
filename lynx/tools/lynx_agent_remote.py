#!/usr/bin/env python3
"""Nexus client for Lynx's authenticated NRP/1 agent job queue."""

import argparse
import base64
import binascii
import json
from pathlib import Path
import re
import subprocess
import sys

CLIENT = Path(__file__).with_name('lynx_noobctl.py')
ID = re.compile(r'[0-9a-f]{32}\Z')
REPLY = re.compile(r'NRP/1 1 OK value=(-?\d+)(?: detail=(.*))?\Z')
HEALTH_ISSUES = {'queue_unavailable', 'queue_not_private', 'entry_unreadable',
                 'unexpected_entry', 'entry_not_private', 'queue_unreadable',
                 'stop_marker_unreadable', 'stop_marker_not_private'}


def call(*words):
    run = subprocess.run([sys.executable, str(CLIENT), *words], capture_output=True,
                         text=True, timeout=15)
    if run.returncode:
        raise RuntimeError(run.stderr.strip() or run.stdout.strip() or 'NRP call failed')
    match = REPLY.fullmatch(run.stdout.strip())
    if not match:
        raise RuntimeError('unexpected NRP response')
    details = {}
    if match.group(2):
        for part in match.group(2).split():
            key, sep, value = part.partition('=')
            if not sep or key in details:
                raise RuntimeError('malformed NRP detail')
            details[key] = value
    return int(match.group(1)), details


def result(job_id):
    chunks = bytearray()
    total = None
    result_ok = None
    for _ in range(85):
        length, detail = call('CALL_MIXED', 'AGENT_RESULT', str(len(chunks)),
                              '"' + job_id + '"')
        if 'data' not in detail or 'more' not in detail or 'ok' not in detail:
            raise RuntimeError('job has not finished or result is unavailable')
        if total is None:
            total = length
            result_ok = detail['ok']
        if length != total or not 0 <= length <= 8000:
            raise RuntimeError('inconsistent result length')
        if detail['ok'] != result_ok or result_ok not in ('0', '1'):
            raise RuntimeError('inconsistent result status')
        data = detail['data']
        try:
            chunk = base64.b64decode(data + '=' * (-len(data) % 4),
                                     altchars=b'-_', validate=True)
        except binascii.Error as exc:
            raise RuntimeError('invalid result page encoding') from exc
        if not chunk and detail['more'] == '1':
            raise RuntimeError('empty result page')
        chunks.extend(chunk)
        if len(chunks) > total:
            raise RuntimeError('result exceeds announced length')
        if detail['more'] == '0':
            if len(chunks) != total:
                raise RuntimeError('result ended early')
            return {'job_id': job_id, 'ok': result_ok == '1',
                    'text': chunks.decode('utf-8')}
        if detail['more'] != '1':
            raise RuntimeError('invalid result continuation')
    raise RuntimeError('result exceeded page limit')


def health():
    value, detail = call('CALL', 'LYNX_QUEUE_HEALTH')
    if value != 1 or detail.get('tool') != 'LYNX_QUEUE_HEALTH':
        raise RuntimeError('invalid queue health response')
    data = detail.get('data', '')
    try:
        raw = base64.b64decode(data + '=' * (-len(data) % 4),
                               altchars=b'-_', validate=True)
        state = json.loads(raw)
    except (binascii.Error, UnicodeError, ValueError) as exc:
        raise RuntimeError('invalid queue health payload') from exc
    if not isinstance(state, dict) or set(state) != {
            'counts', 'oldest_pending_seconds', 'stopped', 'issues'} or \
            not isinstance(state['counts'], dict) or set(state['counts']) != {
                'pending', 'running', 'done'} or any(
                    type(value) is not int or value < 0
                    for value in state['counts'].values()) or \
            (state['oldest_pending_seconds'] is not None and (
                type(state['oldest_pending_seconds']) is not int or
                state['oldest_pending_seconds'] < 0)) or \
            type(state['stopped']) is not bool or \
            not isinstance(state['issues'], list) or \
            any(issue not in HEALTH_ISSUES for issue in state['issues']):
        raise RuntimeError('incomplete queue health payload')
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('submit', 'status', 'result', 'cancel', 'health'))
    parser.add_argument('job_id', nargs='?')
    args = parser.parse_args()
    try:
        if args.command == 'health':
            if args.job_id:
                parser.error('health does not use a job ID')
            answer = health()
        elif args.command == 'submit':
            if args.job_id:
                parser.error('submit reads its prompt from stdin')
            prompt = sys.stdin.read(256).rstrip('\n')
            if not prompt.isascii() or not 1 <= len(prompt) <= 255 or \
                    any(ord(char) < 32 for char in prompt):
                parser.error('NRP prompt must be 1..255 printable ASCII characters')
            value, detail = call('CALL_TEXT', 'AGENT_SUBMIT', prompt)
            if value != 1 or not ID.fullmatch(detail.get('job_id', '')):
                raise RuntimeError('invalid submission receipt')
            answer = {'job_id': detail['job_id'], 'status': 'pending'}
        else:
            if not ID.fullmatch(args.job_id or ''):
                parser.error('a valid 32-character job ID is required')
            if args.command == 'result':
                answer = result(args.job_id)
            else:
                value, detail = call('CALL_TEXT', 'AGENT_' + args.command.upper(),
                                     args.job_id)
                answer = {'job_id': args.job_id, 'value': value, **detail}
        print(json.dumps(answer, ensure_ascii=False))
        return 0
    except (OSError, RuntimeError, ValueError, UnicodeError) as exc:
        print(json.dumps({'error': str(exc)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
