#!/usr/bin/env python3
"""Nonblocking YouTube display service with persistent private Chromium sign-in."""
import json
import os
from pathlib import Path
import re
import secrets
import signal
import socket
import socketserver
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import urllib.request
from media_client import SOCKET

ROOT = Path(__file__).resolve().parent
PROFILE = Path.home() / '.config/rose-display-browser'
PAGE = 'http://127.0.0.1:18580/'
SIGN_IN = 'https://accounts.google.com/ServiceLogin?service=youtube&continue=https%3A%2F%2Fwww.youtube.com%2F'
STATE = SOCKET.with_name('rose-display-state.json')


class Media:
    def __init__(self):
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.browser = None
        self.session = secrets.token_urlsafe(32)
        try:
            self.state = json.loads(STATE.read_text())
        except (OSError, ValueError):
            self.state = {'mode': 'idle', 'generation': 0}
        self.navigated = -1
        self.last_checkpoint = 0
        self.last_player_heartbeat = time.monotonic()
        self.player_deadline = time.monotonic() + 60
        self.recoveries = 0

    def save(self):
        temporary = STATE.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.state))
        temporary.chmod(0o600)
        temporary.replace(STATE)

    def notify(self):
        try:
            with socket.socket(socket.AF_UNIX) as connection:
                connection.settimeout(.5)
                connection.connect(str(SOCKET.with_name('rose-chat.sock')))
                connection.sendall((json.dumps({'type': 'display_state', 'mode': self.state['mode']}) + '\n').encode())
        except OSError:
            pass

    def control(self, args):
        with self.lock:
            action = args.get('action')
            if action == 'status':
                return dict(self.state)
            if action in {'pause', 'resume', 'volume', 'mute', 'seek'}:
                if self.state['mode'] != 'video':
                    return {'ok': False, 'error': 'No YouTube video is active'}
                revision = self.state.get('revision', 0) + 1
                if action in {'pause', 'resume'}:
                    self.state['paused'] = action == 'pause'
                elif action == 'volume':
                    volume = args.get('volume')
                    if type(volume) is not int or not 0 <= volume <= 100:
                        return {'ok': False, 'error': 'Volume must be an integer from 0 to 100'}
                    self.state['volume'] = volume
                elif action == 'mute':
                    self.state['muted'] = bool(args.get('muted', True))
                elif action == 'seek':
                    seconds = args.get('seconds')
                    if type(seconds) is not int or not 0 <= seconds <= 86400:
                        return {'ok': False, 'error': 'Seek position must be 0–86400 seconds'}
                    self.state.update(seek_seconds=seconds, seek_revision=revision,
                                      start_seconds=seconds, position=seconds)
                self.state['revision'] = revision
                self.save()
                return {'ok': True, 'action': action, 'revision': revision}
            if action not in {'play', 'stop', 'login'}:
                return {'ok': False, 'error': 'Unknown display action'}
            if action == 'play' and not re.fullmatch(r'[A-Za-z0-9_-]{11}', args.get('video_id', '')):
                return {'ok': False, 'error': 'Expected an 11-character YouTube video ID'}
            generation = self.state.get('generation', 0) + 1
            self.state = {'mode': {'play': 'video', 'stop': 'idle', 'login': 'login'}[action],
                          'generation': generation, 'playback_state': 'stopped' if action == 'stop' else 'starting'}
            if action == 'play':
                self.state.update(video_id=args['video_id'], muted=bool(args.get('muted', False)),
                                  start_seconds=max(0, int(args.get('start_seconds', 0))), paused=False,
                                  volume=50, revision=0)
                self.player_deadline = time.monotonic() + 60
            self.save()
            self.notify()
            return {'ok': True, 'mode': self.state['mode'], 'generation': generation}

    def wait_for_playback(self, generation, timeout=20):
        """Confirm startup, without waiting for the video to finish."""
        deadline = time.monotonic() + timeout
        while True:
            with self.lock:
                state = dict(self.state)
            if state.get('generation') != generation or state.get('mode') != 'video':
                return {'ok': False, 'error': 'Play request was replaced or stopped'}
            if state.get('player_error'):
                return {'ok': False, 'error': 'YouTube rejected playback', 'player_error': state['player_error']}
            if state.get('playback_state') == 1 and state.get('reported_video_id') == state.get('video_id'):
                return {'ok': True, 'playing': True, 'autoplay': True,
                        'video_id': state['video_id'], 'muted': state.get('muted', False),
                        'position': state.get('position', 0)}
            if time.monotonic() >= deadline or self.stop.wait(.1):
                return {'ok': False, 'error': 'Playback did not start within 20 seconds',
                        'video_id': state.get('video_id'), 'playback_state': state.get('playback_state')}

    @staticmethod
    def output():
        outputs = json.loads(subprocess.check_output(['wlr-randr', '--json'], timeout=3))
        if isinstance(outputs, dict):
            outputs = outputs.get('outputs', [])
        choices = [item for item in outputs if item.get('enabled') and item.get('name', '').startswith('HDMI')]
        return next((item for item in choices if item['name'] == 'HDMI-A-2'), choices[0] if choices else None)

    @staticmethod
    def cdp(target, method, params):
        import websocket
        connection = websocket.create_connection(target['webSocketDebuggerUrl'], timeout=3, suppress_origin=True)
        try:
            connection.send(json.dumps({'id': 1, 'method': method, 'params': params}))
            while True:
                response = json.loads(connection.recv())
                if response.get('id') == 1:
                    if response.get('error'):
                        raise RuntimeError('Browser rejected display command')
                    return response.get('result', {})
        finally:
            connection.close()

    def close_browser(self):
        browser, self.browser = self.browser, None
        if browser:
            if browser.poll() is None:
                browser.terminate()
                try:
                    browser.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(browser.pid, signal.SIGKILL)
                    browser.wait()
            self.navigated = -1

    def recover_stale_player(self, now):
        """A living browser process can contain a frozen renderer."""
        with self.lock:
            stale = (self.state['mode'] == 'video' and self.browser is not None
                     and now > self.player_deadline
                     and now - self.last_player_heartbeat > 30)
            if stale:
                self.recoveries += 1
                self.state['browser_status'] = 'recovering unresponsive player'
                self.state['browser_recoveries'] = self.recoveries
                self.state['start_seconds'] = int(self.state.get('position', self.state.get('start_seconds', 0)))
                self.player_deadline = now + 60
                self.save()
        if stale:
            self.close_browser()
        return stale

    def supervise(self):
        while not self.stop.is_set():
            try:
                self.recover_stale_player(time.monotonic())
                with self.lock:
                    state = dict(self.state)
                output = self.output()
                if state['mode'] == 'idle' or output is None:
                    self.close_browser()
                    self.stop.wait(1)
                    continue
                if self.browser is None or self.browser.poll() is not None:
                    with self.lock:
                        self.state['start_seconds'] = int(self.state.get('position', self.state.get('start_seconds', 0)))
                    PROFILE.mkdir(parents=True, exist_ok=True, mode=0o700)
                    preferences = PROFILE / 'Default/Preferences'
                    preferences.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    try:
                        prefs = json.loads(preferences.read_text())
                    except (OSError, ValueError):
                        prefs = {}
                    prefs['credentials_enable_service'] = False
                    prefs.setdefault('profile', {})['password_manager_enabled'] = False
                    preferences.write_text(json.dumps(prefs))
                    preferences.chmod(0o600)
                    position = output.get('position', {'x': 2464, 'y': 0})
                    command = ['/usr/bin/chromium', '--ozone-platform=x11', '--class=rose-display-web',
                        '--password-store=basic',
                        '--user-data-dir=' + str(PROFILE), '--remote-debugging-port=18581',
                        '--remote-debugging-address=127.0.0.1', '--no-first-run', '--no-default-browser-check',
                        '--autoplay-policy=no-user-gesture-required', '--app=' + PAGE,
                        '--window-position=' + str(position['x']) + ',' + str(position['y'])]
                    environment = {k: v for k, v in os.environ.items() if 'API_KEY' not in k and not k.startswith('OPENAI_')}
                    self.browser = subprocess.Popen(command, env=environment, start_new_session=True,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    self.navigated = -1
                    self.player_deadline = time.monotonic() + 60
                with urllib.request.urlopen('http://127.0.0.1:18581/json', timeout=2) as response:
                    targets = json.load(response)
                target = next((item for item in targets if item.get('type') == 'page'), None)
                if target and self.navigated != state['generation']:
                    window = self.cdp(target, 'Browser.getWindowForTarget', {})
                    position = output.get('position', {'x': 2464, 'y': 0})
                    self.cdp(target, 'Browser.setWindowBounds', {'windowId': window['windowId'], 'bounds': {'windowState': 'normal'}})
                    self.stop.wait(.3)
                    self.cdp(target, 'Browser.setWindowBounds', {'windowId': window['windowId'], 'bounds': {'left': position['x'], 'top': position['y'], 'width': 1280, 'height': 720}})
                    # labwc applies moves asynchronously. Fullscreen must wait
                    # until the window has actually reached the HDMI output.
                    for _ in range(10):
                        bounds = self.cdp(target, 'Browser.getWindowBounds', {'windowId': window['windowId']})['bounds']
                        if bounds.get('left') == position['x'] and bounds.get('top') == position['y']:
                            break
                        self.stop.wait(.1)
                    self.stop.wait(.2)
                    self.cdp(target, 'Browser.setWindowBounds', {'windowId': window['windowId'], 'bounds': {'windowState': 'fullscreen'}})
                    # The local page polls commands; changing tracks must not
                    # tear down and reload the live YouTube renderer.
                    if state['mode'] == 'login' or not target.get('url', '').startswith(PAGE):
                        self.cdp(target, 'Page.navigate', {'url': SIGN_IN if state['mode'] == 'login' else PAGE})
                    self.navigated = state['generation']
                if target:
                    with self.lock:
                        self.state['browser_status'] = 'ready'
                        self.state.pop('browser_error_type', None)
            except Exception as error:
                with self.lock:
                    self.state['browser_status'] = 'starting or reconnecting'
                    self.state['browser_error_type'] = type(error).__name__
            self.stop.wait(1)
        self.close_browser()


class HTTP(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def reply(self, body, kind='application/json'):
        self.send_response(200)
        self.send_header('Content-Type', kind)
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        media = self.server.media
        if self.path == '/':
            self.reply((ROOT / 'player.html').read_text().replace('SESSION_TOKEN', media.session).encode(), 'text/html; charset=utf-8')
        elif self.path == '/api/state':
            with media.lock:
                self.reply(json.dumps(media.state).encode())
        else:
            self.send_error(404)

    def do_POST(self):
        media = self.server.media
        if self.path != '/api/player' or self.headers.get('X-Rose-Session') != media.session:
            self.send_error(403)
            return
        try:
            value = json.loads(self.rfile.read(min(2048, int(self.headers.get('Content-Length', 0)))))
            with media.lock:
                if value.get('generation') == media.state.get('generation'):
                    video_id = value.get('video_id')
                    if isinstance(video_id, str) and re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id):
                        media.state['reported_video_id'] = video_id
                    if isinstance(value.get('position'), (int, float)):
                        media.last_player_heartbeat = time.monotonic()
                    for key in ('playback_state', 'player_error', 'position'):
                        if key in value and isinstance(value[key], (int, float)):
                            media.state[key] = value[key]
                    # Startup emits temporary paused/cued states. They must
                    # not overwrite the requested autoplay/pause setting.
                    if time.monotonic() - media.last_checkpoint > 5:
                        media.save()
                        media.last_checkpoint = time.monotonic()
            self.reply(b'{}')
        except (ValueError, TypeError):
            self.send_error(400)


class Control(socketserver.StreamRequestHandler):
    def handle(self):
        self.request.settimeout(3)
        try:
            args = json.loads(self.rfile.readline(8192))
            if not isinstance(args, dict):
                raise ValueError('Expected a command object')
            result = self.server.media.control(args)
            if args.get('action') == 'play' and result.get('ok'):
                result = self.server.media.wait_for_playback(result['generation'])
        except (OSError, ValueError, TypeError):
            result = {'ok': False, 'error': 'Invalid display request'}
        self.wfile.write((json.dumps(result) + '\n').encode())


def main():
    os.umask(0o077)
    if SOCKET.exists():
        SOCKET.unlink()
    media = Media()
    http = ThreadingHTTPServer(('127.0.0.1', 18580), HTTP)
    http.media = media
    threading.Thread(target=http.serve_forever, daemon=True).start()
    threading.Thread(target=media.supervise, daemon=True).start()
    with socketserver.ThreadingUnixStreamServer(str(SOCKET), Control) as control:
        control.daemon_threads = True
        control.media = media
        SOCKET.chmod(0o600)
        signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
        try:
            control.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            media.stop.set()
            media.close_browser()
            http.shutdown()
            http.server_close()
            SOCKET.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
