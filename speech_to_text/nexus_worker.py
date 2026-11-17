#!/usr/bin/env python3
"""Warm, private Nexus English transcription worker. No audio files or text logs."""
import argparse
import base64
import json
import os
from pathlib import Path
import socketserver
import threading
import zlib
import numpy as np
from decode_engine import Decoder

SOCKET = Path(os.environ.get('XDG_RUNTIME_DIR', '/run/user/' + str(os.getuid()))) / 'noobia-transcribe.sock'


def decode_request(request, decoder):
    if request.get('type') == 'hello':
        return {'ok': True, 'model': decoder.model_name, 'language': decoder.language, 'executor': 'Nexus'}
    encoded = request.get('pcm_zlib', request.get('pcm'))
    if request.get('type') != 'transcribe' or not isinstance(encoded, str):
        raise ValueError('Invalid request')
    pcm = base64.b64decode(encoded, validate=True)
    if 'pcm_zlib' in request:
        inflater = zlib.decompressobj()
        pcm = inflater.decompress(pcm, 960001)
        if not inflater.eof or inflater.unconsumed_tail or inflater.unused_data:
            raise ValueError('Invalid or oversized compressed audio')
    if not pcm or len(pcm) % 2 or len(pcm) > 16000 * 2 * 30:
        raise ValueError('Audio must be 16 kHz mono PCM, at most 30 seconds')
    audio = np.frombuffer(pcm, dtype='<i2').astype(np.float32) / 32768
    return {'ok': True, **decoder.decode(audio)}


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.request.settimeout(120)
        while True:
            line = self.rfile.readline(1400001)
            if not line:
                return
            if len(line) > 1400000 or not line.endswith(b'\n'):
                return
            try:
                request = json.loads(line)
                if not isinstance(request, dict):
                    raise ValueError('Invalid request')
                with self.server.decode_lock:
                    result = decode_request(request, self.server.decoder)
            except (ValueError, TypeError, zlib.error):
                result = {'ok': False, 'error': 'Invalid transcription request'}
            self.wfile.write(json.dumps(result).encode() + b'\n')
            self.wfile.flush()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', default='base')
    args = parser.parse_args()
    os.umask(0o077)
    decoder = Decoder(args.model, 'en', threads=8)
    decoder.prepare()
    SOCKET.unlink(missing_ok=True)
    with socketserver.ThreadingUnixStreamServer(str(SOCKET), Handler) as server:
        server.daemon_threads = True
        server.decoder, server.decode_lock = decoder, threading.Lock()
        SOCKET.chmod(0o600)
        print('Nexus English transcription worker ready', flush=True)
        try:
            server.serve_forever()
        finally:
            SOCKET.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
