"""Restart the transcriber after USB loss without dropping socket subscribers."""
import asyncio
from contextlib import suppress
import json
import os
import signal


class Capture:
    def __init__(self, factory, broadcast, retry_seconds=3, health_timeout=20):
        self.factory = factory
        self.broadcast = broadcast
        self.retry_seconds = retry_seconds
        self.health_timeout = health_timeout
        self.task = None
        self.process = None

    def status(self, phase, message):
        self.broadcast({'type': 'status', 'phase': phase, 'message': message})

    def start(self):
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self.supervise())

    async def terminate(self):
        process = self.process
        self.process = None
        if process is None:
            return
        # Kill the entire capture group, including arecord, even if Python exited.
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGTERM)
        try:
            await asyncio.wait_for(process.communicate(), 5)
        except asyncio.TimeoutError:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            await process.communicate()

    async def stop(self):
        if self.task:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task
            self.task = None

    async def supervise(self):
        try:
            while True:
                self.status('starting', 'Starting English microphone capture…')
                try:
                    self.process = await self.factory()
                    audio_seen = False
                    while True:
                        line = await asyncio.wait_for(self.process.stdout.readline(),
                            self.health_timeout if audio_seen else 120)
                        if not line:
                            break
                        try:
                            event = json.loads(line)
                        except (ValueError, UnicodeDecodeError):
                            continue
                        if event.get('type') == 'audio' and not audio_seen:
                            audio_seen = True
                            self.status('listening', 'Microphone connected · English')
                        self.broadcast(event)
                    await self.process.wait()
                except (OSError, asyncio.TimeoutError):
                    pass
                finally:
                    await self.terminate()
                self.status('retrying', 'Microphone unavailable; reconnecting automatically…')
                await asyncio.sleep(self.retry_seconds)
        finally:
            await self.terminate()
