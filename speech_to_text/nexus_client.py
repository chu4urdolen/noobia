"""Nexus-first decoding over a restricted persistent SSH connection."""
import base64
import json
import os
from pathlib import Path
import select
import subprocess
import time
import zlib


class Remote:
    def __init__(self, config, model, language):
        self.config, self.model, self.language = config, model, language
        self.name = config.get('name', 'Nexus')
        self.process = None
        self.buffer = b''

    def close(self):
        process, self.process = self.process, None
        self.buffer = b''
        if process:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            process.stdin.close()
            process.stdout.close()

    def exchange(self, request, timeout=5):
        payload = memoryview(json.dumps(request).encode() + b'\n')
        while payload:
            written = self.process.stdin.write(payload)
            if not written:
                raise ConnectionError('Nexus input disconnected')
            payload = payload[written:]
        self.process.stdin.flush()
        deadline = time.monotonic() + timeout
        while b'\n' not in self.buffer:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([self.process.stdout], [], [], remaining)[0]:
                raise TimeoutError('Nexus transcription timed out')
            data = os.read(self.process.stdout.fileno(), 65536)
            if not data:
                raise ConnectionError('Nexus transcription disconnected')
            self.buffer += data
            if len(self.buffer) > 65536:
                raise ValueError('Nexus response exceeds size limit')
        line, self.buffer = self.buffer.split(b'\n', 1)
        response = json.loads(line)
        if not isinstance(response, dict) or not response.get('ok'):
            raise ValueError('Nexus rejected transcription request')
        return response

    def connect(self):
        if self.process is not None and self.process.poll() is None:
            return
        self.close()
        settings = self.config
        self.process = subprocess.Popen(['ssh', '-T', '-o', 'BatchMode=yes',
            '-o', 'ConnectTimeout=1', '-o', 'ConnectionAttempts=1',
            '-o', 'StrictHostKeyChecking=yes', '-o', 'IdentitiesOnly=yes',
            '-o', 'IPQoS=none', '-o', 'Compression=yes',
            '-o', 'ServerAliveInterval=2', '-o', 'ServerAliveCountMax=1',
            '-o', 'UserKnownHostsFile=' + settings['known_hosts'],
            '-i', settings['identity'], settings['target']],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            bufsize=0)
        hello = self.exchange({'type': 'hello'}, timeout=2)
        if hello.get('model') != self.model or hello.get('language') != self.language:
            raise ValueError('Nexus model/language does not match capture settings')

    def decode(self, audio):
        import numpy as np
        self.connect()
        pcm = (np.clip(audio, -1, 1) * 32767).astype('<i2').tobytes()
        result = self.exchange({'type': 'transcribe',
            'pcm_zlib': base64.b64encode(zlib.compress(pcm, 1)).decode('ascii')}, timeout=8)
        if not isinstance(result.get('text'), str) or result.get('language') != self.language:
            raise ValueError('Invalid Nexus transcript')
        result['executor'] = self.name
        return result


class Router:
    def __init__(self, local, remote=None, status=lambda message: None, clock=time.monotonic):
        self.local, self.remote, self.status, self.clock = local, remote, status, clock
        self.retry_after = 0
        self.executor = None

    def decode(self, audio):
        if self.remote is not None and self.clock() >= self.retry_after:
            try:
                result = self.remote.decode(audio)
            except (OSError, ValueError, subprocess.SubprocessError):
                self.remote.close()
                self.retry_after = self.clock() + 10
            else:
                self.route('Nexus')
                return result
        self.route('Syra' if self.remote else 'local')
        result = self.local.decode(audio)
        result['executor'] = self.executor
        return result

    def route(self, executor):
        if executor != self.executor:
            self.executor = executor
            self.status('Transcription worker: ' + executor)

    def close(self):
        if self.remote:
            self.remote.close()


def remote_from_config(path, model, language):
    try:
        settings = json.loads(Path(path).read_text())
    except FileNotFoundError:
        return None
    if not all(isinstance(settings.get(key), str) and settings[key] for key in
               ('target', 'identity', 'known_hosts')):
        raise ValueError('Invalid private Nexus transcription configuration')
    return Remote(settings, model, language)
