#!/usr/bin/env python3
"""Display transcripts from the local speech service; Ctrl+C unsubscribes."""
import argparse
import json
import os
from pathlib import Path
import socket

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--socket', default=str(Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')) / 'noobia-speech.sock'))
parser.add_argument('--json', action='store_true', help='Print raw events for another program')
args = parser.parse_args()
try:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(args.socket)
        with client.makefile() as stream:
            for line in stream:
                event = json.loads(line)
                if args.json:
                    print(line.rstrip(), flush=True)
                elif event['type'] == 'transcript':
                    print(event['text'], flush=True)
                    print(f"  decode {event['decode_seconds']:.2f}s | end→text ≈{event['end_to_text_seconds']:.2f}s", flush=True)
                elif event['type'] != 'audio':
                    print(f"[{event.get('message', event['type'])}]", flush=True)
except KeyboardInterrupt:
    print('\nUnsubscribed.')
except FileNotFoundError:
    parser.exit(1, 'Speech service is not running. Start noobia-speech.service first.\n')
