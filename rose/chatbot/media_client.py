"""Private, fast control API for Rose's asynchronous HDMI browser player."""
import json
import os
from pathlib import Path
import socket
import time

SOCKET = Path(os.environ.get('XDG_RUNTIME_DIR', '/run/user/' + str(os.getuid()))) / 'rose-display.sock'


def request(command):
    with socket.socket(socket.AF_UNIX) as connection:
        connection.settimeout(3)
        deadline = time.monotonic() + 3
        while True:
            try:
                connection.connect(str(SOCKET))
                break
            except (FileNotFoundError, ConnectionRefusedError):
                if time.monotonic() >= deadline:
                    raise
                time.sleep(.05)
        connection.sendall((json.dumps(command) + '\n').encode())
        if command.get('action') == 'play':
            connection.settimeout(25)
        with connection.makefile('r') as stream:
            return json.loads(stream.readline(16384))
