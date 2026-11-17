#!/usr/bin/env python3
"""Forced SSH command: forward only stdin/stdout to the private STT worker."""
import os
from pathlib import Path
import select
import socket
import sys

path = Path(os.environ.get('XDG_RUNTIME_DIR', '/run/user/' + str(os.getuid()))) / 'noobia-transcribe.sock'
with socket.socket(socket.AF_UNIX) as worker:
    worker.connect(str(path))
    while True:
        ready, _, _ = select.select([sys.stdin.buffer, worker], [], [], 90)
        if not ready:
            break
        for source in ready:
            data = os.read(source.fileno(), 65536)
            if not data:
                sys.exit(0)
            if source is worker:
                sys.stdout.buffer.write(data)
                sys.stdout.buffer.flush()
            else:
                worker.sendall(data)
