#!/usr/bin/python3
import os
from pathlib import Path
import shlex
import socket
import sys

arguments = sys.argv[1:]
if socket.gethostname().lower() == 'syra':
    os.execv('/usr/bin/python3', ['/usr/bin/python3', str(Path(__file__).with_name('test_hue_strip.py')), *arguments])
command = shlex.join(['/usr/bin/python3', '/noobia/aria/test_hue_strip.py', *arguments])
os.execvp('ssh', ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', 'rose', command])
