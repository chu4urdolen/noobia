#!/usr/bin/env python3
"""Broadcast local transcription as JSON lines over a private Unix socket."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import signal
import sys
import re
from capture_supervisor import Capture

ROOT = Path(__file__).resolve().parent


async def serve(args):
    path = Path(args.socket)
    if path.exists():
        raise RuntimeError(f'Socket path already exists: {path}; check the existing service before removing it')
    clients = set()
    lock = asyncio.Lock()

    def send(writer, event):
        writer.write((json.dumps(event, ensure_ascii=False) + '\n').encode())

    def broadcast(event):
        for writer in tuple(clients):
            if writer.is_closing():
                continue
            if writer.transport.get_write_buffer_size() > 256 * 1024:
                writer.close()  # a stalled reader cannot consume unbounded memory
                continue
            try:
                send(writer, event)
            except (ConnectionError, BrokenPipeError):
                writer.close()

    async def spawn():
        nodes = list(Path('/dev/snd/by-id').glob('*reSpeaker*'))
        if not nodes:
            raise FileNotFoundError('ReSpeaker USB sound card is unavailable')
        control = nodes[0].resolve(strict=True).name
        match = re.fullmatch(r'controlC(\d+)', control)
        if not match:
            raise OSError('Cannot resolve the ReSpeaker audio card')
        command = [sys.executable, str(ROOT / 'live.py'), '--json-events',
                   '--model', args.model, '--channel', str(args.channel),
                   '--device', 'hw:' + match.group(1) + ',0']
        if args.language:
            command += ['--language', args.language]
        return await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.PIPE,
            start_new_session=True, env={**os.environ, 'HF_HUB_DISABLE_XET': '1'})

    capture = Capture(spawn, broadcast)

    async def connect(reader, writer):
        clients.add(writer)
        try:
            async with lock:
                send(writer, {'type': 'status', 'message': 'Subscribed; speech capture runs while subscribers are connected',
                              'language': args.language, 'model': args.model})
                capture.start()
            await writer.drain()
            # No client command protocol: connection lifetime is subscription lifetime.
            while await reader.read(1024):
                pass
        except (ConnectionError, BrokenPipeError):
            pass
        finally:
            clients.discard(writer)
            writer.close()
            async with lock:
                if not clients:
                    await capture.stop()

    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stopped.set)
    server = await asyncio.start_unix_server(connect, path=str(path))
    path.chmod(0o600)
    print(f'Speech socket ready: {path}. Microphone opens on subscription.', flush=True)
    try:
        async with server:
            await stopped.wait()
    finally:
        server.close()
        for writer in tuple(clients):
            writer.close()
        async with lock:
            await capture.stop()
        await server.wait_closed()
        path.unlink(missing_ok=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--socket', default=str(Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')) / 'noobia-speech.sock'))
    parser.add_argument('--model', default='base')
    parser.add_argument('--language', default='en')
    parser.add_argument('--channel', type=int, choices=[0, 1], default=1)
    asyncio.run(serve(parser.parse_args()))
