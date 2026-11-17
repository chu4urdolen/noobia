#!/usr/bin/env python3
"""An example input adapter: rose-input --source keyboard 'Hello Rose'."""
import argparse
import json
import socket
from server import SOCKET

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', default='keyboard')
parser.add_argument('text')
args = parser.parse_args()
with socket.socket(socket.AF_UNIX) as connection:
    connection.connect(str(SOCKET))
    connection.sendall((json.dumps(dict(type='submit', source=args.source, text=args.text)) + '\n').encode())
