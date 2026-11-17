#!/usr/bin/env python3
"""Local, unprivileged shell and bounded output feed for Lynx's touch console."""

import argparse
from collections import deque
import os
from pathlib import Path
import re
import selectors
import signal
import socket
import subprocess
import sys
import time

ROOT = Path('/run/lynx-console')
SOCK = ROOT / 'control.sock'
SNAPSHOT = ROOT / 'snapshot.txt'
HOME = Path('/var/lib/lynx-console')
ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')
MAX_COMMAND = 160
MAX_LINES = 64
MAX_LINE = 100


def clean(text):
    text = ANSI.sub('', text.replace('\r', ''))
    return ''.join(ch if 32 <= ord(ch) <= 126 else '?' for ch in text)


def category(stream, text):
    low = text.strip().lower()
    if low.startswith('lynx$') or (text.startswith('/') and text.endswith(': ')):
        return 'I'
    if "can't access tty" in low:
        return 'W'
    if low.startswith(('warning:', 'warn:', '[warn]', 'warning ')):
        return 'W'
    return 'E' if stream == 'stderr' else 'O'


class Console:
    def __init__(self, shell='/bin/ash'):
        ROOT.mkdir(mode=0o700, exist_ok=True)
        HOME.mkdir(mode=0o700, exist_ok=True)
        self.lines = deque(maxlen=MAX_LINES)
        self.sequence = 0
        self.partial = {'stdout': '', 'stderr': ''}
        self.sel = selectors.DefaultSelector()
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        if SOCK.exists():
            SOCK.unlink()
        self.server.bind(str(SOCK))
        SOCK.chmod(0o600)
        self.server.listen(4)
        self.server.setblocking(False)
        self.sel.register(self.server, selectors.EVENT_READ, 'server')
        env = {'HOME': str(HOME), 'USER': 'lynx-console', 'LOGNAME': 'lynx-console',
               'PATH': '/usr/local/bin:/usr/bin:/bin', 'TERM': 'dumb',
               'PS1': '${PWD}: '}
        self.shell = subprocess.Popen([shell, '-i'], cwd=HOME, env=env,
                                      stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE, start_new_session=True,
                                      bufsize=0)
        for label, pipe in (('stdout', self.shell.stdout), ('stderr', self.shell.stderr)):
            os.set_blocking(pipe.fileno(), False)
            self.sel.register(pipe, selectors.EVENT_READ, label)
        self.write_snapshot()

    def append(self, kind, text):
        text = clean(text)
        for offset in range(0, max(1, len(text)), MAX_LINE):
            self.lines.append((kind, text[offset:offset + MAX_LINE]))
        self.write_snapshot()

    def write_snapshot(self):
        self.sequence += 1
        temp = SNAPSHOT.with_suffix('.new')
        with temp.open('w', encoding='ascii') as output:
            output.write(f'SEQ {self.sequence}\n')
            for kind, line in self.lines:
                output.write(f'{kind}|{line}\n')
        os.replace(temp, SNAPSHOT)

    def receive_output(self, pipe, label):
        try:
            data = os.read(pipe.fileno(), 4096)
        except BlockingIOError:
            return
        if not data:
            self.sel.unregister(pipe)
            return
        pending = self.partial[label] + data.decode('utf-8', 'replace')
        while '\n' in pending:
            line, pending = pending.split('\n', 1)
            self.append(category(label, line), line)
        self.partial[label] = pending[-MAX_LINE:]

    def accept(self):
        conn, _ = self.server.accept()
        conn.settimeout(2)
        try:
            request = bytearray()
            while b'\n' not in request and len(request) <= MAX_COMMAND * 2 + 16:
                chunk = conn.recv(512)
                if not chunk:
                    break
                request.extend(chunk)
            line = bytes(request).split(b'\n', 1)[0]
            if line == b'STATUS':
                response = f'OK seq={self.sequence} shell={self.shell.pid}\n'.encode()
            elif line.startswith(b'SEND '):
                raw = bytes.fromhex(line[5:].decode('ascii'))
                if (not raw or len(raw) > MAX_COMMAND or
                        any(byte < 32 or byte > 126 for byte in raw)):
                    raise ValueError('invalid command')
                if self.shell.poll() is not None:
                    raise RuntimeError('shell exited')
                self.append('I', raw.decode('ascii'))
                self.shell.stdin.write(raw + b'\n')
                self.shell.stdin.flush()
                response = b'OK\n'
            else:
                raise ValueError('unknown request')
            conn.sendall(response)
        except (ValueError, UnicodeError, OSError, RuntimeError) as exc:
            try:
                conn.sendall(f'ERR {type(exc).__name__}\n'.encode())
            except OSError:
                pass
        finally:
            conn.close()

    def run(self):
        self.append('W', 'CONSOLE RUNS AS LYNX-CONSOLE')
        running = True

        def stop(_signal, _frame):
            nonlocal running
            running = False

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        try:
            while running and self.shell.poll() is None:
                for key, _ in self.sel.select(timeout=0.2):
                    if key.data == 'server':
                        self.accept()
                    else:
                        self.receive_output(key.fileobj, key.data)
                for label in ('stdout', 'stderr'):
                    if self.partial[label]:
                        self.append(category(label, self.partial[label]),
                                    self.partial[label])
                        self.partial[label] = ''
            if self.shell.poll() is not None:
                self.append('E', f'SHELL EXITED {self.shell.returncode}')
        finally:
            if self.shell.poll() is None:
                os.killpg(self.shell.pid, signal.SIGTERM)
            try:
                self.shell.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.shell.kill()
                self.shell.wait(timeout=2)
            self.server.close()
            SOCK.unlink(missing_ok=True)


def send(command):
    if not command or len(command) > MAX_COMMAND or any(ord(ch) < 32 or ord(ch) > 126
                                                       for ch in command):
        raise ValueError('command must be 1-160 printable ASCII characters')
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(3)
        client.connect(str(SOCK))
        client.sendall(b'SEND ' + command.encode().hex().encode() + b'\n')
        response = client.recv(128).decode().strip()
    print(response)
    if response != 'OK':
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serve', action='store_true')
    parser.add_argument('--send')
    args = parser.parse_args()
    if args.serve == bool(args.send):
        parser.error('choose --serve or --send COMMAND')
    if args.serve:
        Console().run()
    else:
        send(args.send)


if __name__ == '__main__':
    main()
