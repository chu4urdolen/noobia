#!/usr/bin/env python3
"""Private local NDJSON input/event socket, serialized turns, microphone adapter."""
import json
import os
from pathlib import Path
import queue
import re
import signal
import socket
import socketserver
import threading
import time
from core import Conversation, settings, save_settings

SOCKET = Path(os.environ.get('XDG_RUNTIME_DIR', '/run/user/' + str(os.getuid()))) / 'rose-chat.sock'


class SpeechBuffer:
    """Gather all finalized phrases; 'love' in the latest phrase sends the batch."""
    def __init__(self):
        self.phrases = []

    def add(self, text):
        if len('\n'.join(self.phrases + [text])) > 8000:
            raise ValueError('Speech buffer is full. Stop microphone and start a new batch.')
        self.phrases.append(text)
        if re.search(r'\blove\b', text, re.IGNORECASE):
            result = '\n'.join(self.phrases)
            self.phrases.clear()
            return result
        return None


class App:
    def __init__(self):
        self.clients = set()
        self.lock = threading.Lock()
        self.queue = queue.Queue(maxsize=8)
        self.busy = False
        self.mic = settings().get('mic_enabled', True)
        self.speech_buffer = SpeechBuffer()
        self.mic_connection = None
        self.mic_phase = 'connecting' if self.mic else 'off'
        self.speaking_started = None
        self.spoken_intervals = []
        self.conversation = Conversation(emit=self.emit)
        threading.Thread(target=self.worker, daemon=True).start()
        threading.Thread(target=self.microphone, daemon=True).start()
        threading.Thread(target=self.hardware, daemon=True).start()

    def hardware(self):
        path = SOCKET.with_name('rose-hardware.json')
        previous = None
        while True:
            try:
                value = json.loads(path.read_text())
                value.pop('checked_at', None)
                if value != previous:
                    self.emit({'type': 'hardware', **value})
                    previous = value
            except (OSError, ValueError):
                pass
            time.sleep(3)

    def emit(self, event):
        # Keep hearing during model/tool work. Reject recognition overlapping our
        # own audio using capture-time estimates, including delayed transcripts.
        starts_audio = (event.get('type') == 'state' and event.get('text') == 'Speaking with lights…') or (
            event.get('type') == 'tool' and event.get('name') in {'speech', 'rose_speech'} and event.get('state') == 'running')
        ends_audio = event.get('type') == 'tool' and event.get('name') in {'speech', 'rose_speech'} and event.get('state') == 'finished'
        if starts_audio and self.speaking_started is None:
            self.speaking_started = time.time()
        if ends_audio and self.speaking_started is not None:
            self.spoken_intervals.append((self.speaking_started, time.time() + .5))
            self.spoken_intervals = self.spoken_intervals[-32:]
            self.speaking_started = None
        event = dict(event, timestamp=time.time())
        packet = (json.dumps(event) + '\n').encode()
        with self.lock:
            for client in list(self.clients):
                try:
                    client.sendall(packet, socket.MSG_DONTWAIT)
                except OSError:
                    self.clients.discard(client)
                    try:
                        client.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass

    def submit(self, text, source):
        if not isinstance(text, str) or not text.strip() or len(text) > 8000:
            raise ValueError('Input must be 1–8000 characters')
        if not isinstance(source, str) or len(source) > 40:
            raise ValueError('Source name must be at most 40 characters')
        self.queue.put_nowait((text, source))

    def close_microphone(self):
        if self.mic_connection:
            try:
                self.mic_connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def accept_transcript(self, event):
        ended = event.get('timestamp', time.time()) - event.get('end_to_text_seconds', 0)
        began = ended - event.get('audio_seconds', 0)
        intervals = list(self.spoken_intervals)
        if self.speaking_started is not None:
            intervals.append((self.speaking_started, time.time() + .5))
        if any(began <= stop and ended >= start for start, stop in intervals):
            return False
        text = event['text'].strip()
        if not text:
            return False
        self.emit({'type': 'heard', 'text': text})
        batch = self.speech_buffer.add(text)
        if batch is not None:
            self.submit(batch, 'microphone')
        else:
            self.emit({'type': 'state', 'text': 'Gathering speech · ' + str(len(self.speech_buffer.phrases)) + ' phrases · say “love” to send', 'mic': True})
        return True

    def worker(self):
        while True:
            text, source = self.queue.get()
            self.busy = True
            try:
                self.conversation.respond(text, source)
            except Exception as exc:
                # Only our controlled error strings reach subscribers.
                message = str(exc) if isinstance(exc, (RuntimeError, ValueError)) else type(exc).__name__
                self.emit({'type': 'error', 'text': message})
            finally:
                if self.speaking_started is not None:
                    self.spoken_intervals.append((self.speaking_started, time.time() + .5))
                    self.speaking_started = None
                self.busy = False
                self.queue.task_done()
                self.emit({'type': 'state', 'text': 'Ready', 'mic': self.mic})

    def microphone(self):
        speech_socket = SOCKET.with_name('noobia-speech.sock')
        while True:
            if not self.mic:
                time.sleep(.2)
                continue
            try:
                with socket.socket(socket.AF_UNIX) as connection:
                    connection.settimeout(2)
                    connection.connect(str(speech_socket))
                    self.mic_connection = connection
                    self.emit({'type': 'state', 'text': 'Gathering speech · say “love” to send · English', 'mic': True})
                    pending = b''
                    while self.mic:
                        try:
                            data = connection.recv(65536)
                        except socket.timeout:
                            continue
                        if not data:
                            break
                        pending += data
                        while b'\n' in pending:
                            line, pending = pending.split(b'\n', 1)
                            event = json.loads(line)
                            if event.get('type') == 'transcript' and self.mic:
                                self.accept_transcript(event)
                            elif event.get('type') == 'status' and event.get('phase'):
                                self.mic_phase = event['phase']
                                self.emit({'type': 'microphone_state', 'phase': self.mic_phase, 'text': event['message']})
                            elif event.get('type') == 'audio':
                                self.mic_phase = 'listening'
                                self.emit({'type': 'microphone_audio', 'level': event.get('level', 0), 'speech': event.get('speech', False)})
                        if len(pending) > 262144:
                            raise ValueError('Oversized speech event')
            except (ValueError, queue.Full):
                self.mic = False
                self.emit({'type': 'error', 'text': 'Speech buffer or input queue is full; microphone stopped'})
                self.emit({'type': 'state', 'text': 'Microphone stopped', 'mic': False})
            except OSError:
                if self.mic:
                    self.emit({'type': 'state', 'text': 'Waiting for microphone service…', 'mic': True})
                    self.mic_phase = 'retrying'
                    self.emit({'type': 'microphone_state', 'phase': 'retrying', 'text': 'Microphone service unavailable · reconnecting…'})
                time.sleep(1)
            finally:
                self.mic_connection = None


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.request.settimeout(3)
        try:
            while True:
                try:
                    raw = self.rfile.readline(65537)
                except (OSError, socket.timeout):
                    break
                if not raw or len(raw) > 65536:
                    break
                command = json.loads(raw)
                kind = command.get('type')
                if kind == 'subscribe':
                    self.request.settimeout(None)
                    with self.server.app.lock:
                        self.server.app.clients.add(self.request)
                    self.server.app.emit({'type': 'state', 'text': 'Connected', 'mic': self.server.app.mic})
                elif kind == 'submit':
                    self.server.app.submit(command.get('text'), command.get('source', 'external'))
                elif kind == 'microphone':
                    self.server.app.mic = command.get('enabled') is True
                    config = settings()
                    config['mic_enabled'] = self.server.app.mic
                    save_settings(config)
                    self.server.app.speech_buffer = SpeechBuffer()
                    self.server.app.close_microphone()
                    self.server.app.emit({'type': 'state', 'text': 'Microphone enabled' if self.server.app.mic else 'Microphone stopped', 'mic': self.server.app.mic})
                elif kind == 'microphone_status':
                    self.wfile.write((json.dumps({'enabled': self.server.app.mic,
                        'phase': getattr(self.server.app, 'mic_phase', 'unknown'),
                        'buffered_phrases': len(self.server.app.speech_buffer.phrases)}) + '\n').encode())
                    self.wfile.flush()
                elif kind == 'display_state':
                    mode = command.get('mode')
                    if mode in {'video', 'login', 'idle'}:
                        self.server.app.emit({'type': 'display_state', 'mode': mode})
                elif kind == 'cancel':
                    self.server.app.conversation.tools.stop()
                    while True:
                        try:
                            self.server.app.queue.get_nowait()
                            self.server.app.queue.task_done()
                        except queue.Empty:
                            break
                    self.server.app.emit({'type': 'state', 'text': 'Stopping…'})
                elif kind == 'clear':
                    if not self.server.app.busy:
                        self.server.app.conversation.turns.clear()
                        self.server.app.speech_buffer = SpeechBuffer()
                        self.server.app.emit({'type': 'state', 'text': 'Conversation cleared'})
        except (ValueError, TypeError, queue.Full):
            self.server.app.emit({'type': 'error', 'text': 'Invalid input or input queue full'})
        finally:
            with self.server.app.lock:
                self.server.app.clients.discard(self.request)


class Server(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True


def main():
    if SOCKET.exists():
        with socket.socket(socket.AF_UNIX) as probe:
            try:
                probe.connect(str(SOCKET))
            except OSError:
                SOCKET.unlink()
            else:
                raise SystemExit('Rose chatbot is already running')
    os.umask(0o077)
    with Server(str(SOCKET), Handler) as server:
        SOCKET.chmod(0o600)
        server.app = App()
        def terminate(*_):
            server.app.mic = False
            server.app.close_microphone()
            server.app.conversation.tools.stop()
            raise KeyboardInterrupt
        signal.signal(signal.SIGTERM, terminate)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            SOCKET.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
