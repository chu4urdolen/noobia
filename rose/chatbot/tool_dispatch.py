#!/usr/bin/env python3
"""JSON-stdin implementations for Rose's shell wrappers; no shell interpolation."""
import json
from pathlib import Path
import subprocess
import socket
import os
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BIN = Path.home() / '.local/bin'


def dispatch(name, args):
    if name == 'rose_youtube_search':
        from youtube_api import search
        result = search(args['query'], args['limit'])
        print(json.dumps(result))
        return 0 if result['ok'] else 1
    if name in {'rose_youtube_play', 'rose_youtube_stop', 'rose_display_status', 'rose_youtube_login',
                'rose_youtube_pause', 'rose_youtube_resume', 'rose_youtube_volume', 'rose_youtube_mute', 'rose_youtube_seek'}:
        from media_client import request
        action = {'rose_youtube_play': 'play', 'rose_youtube_stop': 'stop',
                  'rose_display_status': 'status', 'rose_youtube_login': 'login',
                  'rose_youtube_pause': 'pause', 'rose_youtube_resume': 'resume',
                  'rose_youtube_volume': 'volume', 'rose_youtube_mute': 'mute', 'rose_youtube_seek': 'seek'}[name]
        result = request(dict(args, action=action))
        print(json.dumps(result))
        return 0 if result.get('ok', True) else 1
    if name.startswith('lolth_'):
        command = ['/usr/bin/python3', '/noobia/lolth/tools/lafvinctl.py']
        action = name.removeprefix('lolth_')
        if action in {'info', 'state', 'servos', 'distance', 'calibration'}:
            command += [action]
        elif action == 'action':
            command += ['action', args['name']]
        elif action == 'servo':
            command += ['servo', str(args['number']), str(args['angle'])]
        elif action == 'step':
            command += [args['direction'], str(args['number']), str(args['degrees'])]
        elif action == 'stop':
            command += ['stop', args['mode']]
        elif action == 'calibration_change':
            command += ['calibration', args['operation'], str(args['servo_id']), str(args['degrees'])]
        elif action == 'program':
            command += ['program', '/noobia/lolth/programs/lafvin/' + args['pose'] + '.json']
            if args['servo'] is not None:
                command += ['--servo', str(args['servo'])]
            if args['execute']:
                command.append('--execute')
                if args['all']:
                    command.append('--all')
        else:
            raise ValueError('Unknown Lolth command')
        return subprocess.call(command)
    name = name.removeprefix('rose_').removeprefix('syra_')
    if name == 'microphone':
        path = Path(os.environ.get('XDG_RUNTIME_DIR', '/run/user/' + str(os.getuid()))) / 'rose-chat.sock'
        with socket.socket(socket.AF_UNIX) as connection:
            connection.settimeout(5)
            connection.connect(str(path))
            if args['action'] != 'status':
                command = {'type': 'microphone', 'enabled': args['action'] == 'on'}
                connection.sendall((json.dumps(command) + '\n').encode())
            connection.sendall(b'{"type":"microphone_status"}\n')
            with connection.makefile('r') as stream:
                print(stream.readline().strip())
        return 0
    if name == 'speech':
        from core import clean_response
        return subprocess.call([str(BIN / 'rose-say'), clean_response(args['text'])])
    if name == 'camera':
        result = subprocess.run([str(BIN / 'rose-nyx-detect'), 'object0'],
            capture_output=True, text=True, timeout=350)
        if result.stderr:
            print(result.stderr, file=sys.stderr, end='')
        if result.returncode:
            print(result.stdout, end='')
            return result.returncode
        manifest = json.loads(result.stdout.strip().splitlines()[-1])
        run = manifest['runs'][0]
        objects = json.loads(Path(run['detections']).read_text())
        print(json.dumps({'image': run['image'], 'model': 'object0', 'objects': objects,
                          'metadata_path': run['metadata']}))
        return 0
    if name == 'camera_snapshot':
        return subprocess.call([str(BIN / 'rose-nyx-snapshot')])
    if name == 'camera_detect':
        return subprocess.call([str(BIN / 'rose-nyx-detect'), args['model']])
    if name == 'hue_off':
        return subprocess.call([str(BIN / 'rose-hue-off')])
    if name == 'hue_strip':
        command = [str(ROOT.parent / 'aria/hue-strip'), args['action']]
        if args['brightness'] is not None:
            command += ['--brightness', str(args['brightness'])]
        return subprocess.call(command)
    if name == 'hue_pattern':
        if sum(row['seconds'] for row in args['steps']) > 120:
            raise ValueError('Pattern must finish within 120 seconds')
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv') as file:
            for row in args['steps']:
                file.write(','.join(str(row[k]) for k in ('red', 'green', 'blue', 'brightness', 'seconds')) + '\n')
            file.flush()
            return subprocess.call([str(BIN / 'rose-hue'), file.name])
    if name == 'projector_cast':
        file = Path(args['path']).expanduser().resolve(strict=True)
        allowed = [ROOT.parent.resolve(), (Path.home() / 'Pictures').resolve(),
                   (Path.home() / 'Videos').resolve(), (Path.home() / 'Downloads').resolve()]
        if not any(file.is_relative_to(folder) for folder in allowed) or not file.is_file():
            raise ValueError('Choose a media file in /noobia, Pictures, Videos, or Downloads')
        if file.suffix.lower() not in {'.jpg', '.jpeg', '.png', '.webp', '.mp4', '.mkv', '.mov', '.gif'}:
            raise ValueError('Unsupported media extension')
        if any(part.startswith('.') or part in {'private', 'backups'} for part in file.parts):
            raise ValueError('Private files cannot be projected')
        return subprocess.call([str(BIN / 'projector-cast'), str(file)])
    if name == 'plug':
        # Off and toggle never reach the power controller through this interface.
        if args['action'] not in {'status', 'on'}:
            raise ValueError('Syra power cuts are protected')
        return subprocess.call([str(ROOT.parent / 'aria/plug'), args['action']])
    if name == 'devices':
        return subprocess.call(['/usr/bin/python3', '/noobia/rose-hardware/devices.py'])
    if name == 'gnss':
        return subprocess.call(['gpspipe', '-w', '-n', '6'])
    if name == 'ubertooth_info':
        return subprocess.call(['ubertooth-util', '-v'])
    raise ValueError('Unknown wrapper')


if __name__ == '__main__':
    try:
        from jsonschema import validate
        name = sys.argv[1]
        args = json.loads(sys.stdin.read(65536))
        manifest = json.loads((ROOT / 'calls' / (name + '.json')).read_text())
        validate(args, manifest['parameters'])
        sys.exit(dispatch(name, args))
    except Exception as exc:
        print('Tool failed: ' + type(exc).__name__, file=sys.stderr)
        sys.exit(1)
