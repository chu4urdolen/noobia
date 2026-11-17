"""One explicit live test: status lookup, Responses continuation, speech and lights."""
import json
import socket
import time
import sys
from server import SOCKET

with socket.socket(socket.AF_UNIX) as connection:
    connection.settimeout(180)
    deadline = time.monotonic() + 10
    while True:
        try:
            connection.connect(str(SOCKET))
            break
        except (FileNotFoundError, ConnectionRefusedError):
            if time.monotonic() >= deadline:
                raise
            time.sleep(.1)
    use_shell = '--shell' in sys.argv
    use_camera = '--camera' in sys.argv
    expected_tool = 'rose_camera' if use_camera else ('rose_shell' if use_shell else 'rose_hue_strip')
    prompt = ('Please use rose_shell to run uname -s and hostname, then greet Noob in one short sentence mentioning the host name.' if use_shell else
              'Please use rose_hue_strip to check the light strip status without changing it, then greet Noob in one short sentence and say whether the strip is reachable.')
    if use_camera:
        prompt = 'Please use rose_camera exactly once, then briefly say what objects it detected.'
    for command in [dict(type='subscribe'), dict(type='submit', source='setup-test', text=prompt)]:
        connection.sendall((json.dumps(command) + '\n').encode())
    with connection.makefile('r') as stream:
        reply = False
        lookup = False
        started = False
        for line in stream:
            event = json.loads(line)
            kind = event.get('type')
            if kind == 'input' and event.get('source') == 'setup-test':
                started = True
            if not started:
                continue
            if kind in {'reply', 'tool', 'usage', 'error'}:
                print(json.dumps(event), flush=True)
            if kind == 'error':
                raise SystemExit(1)
            if kind == 'tool' and event.get('name') == expected_tool:
                lookup = event.get('result', {}).get('ok', False) or lookup
            if kind == 'reply':
                reply = True
            if kind == 'tool' and event.get('name') == 'rose_speech':
                raise SystemExit(0 if reply and lookup and event['result']['ok'] else 1)
