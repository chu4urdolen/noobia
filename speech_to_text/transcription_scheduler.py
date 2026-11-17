"""One job per available worker; FIFO dispatch and ordered transcripts."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import queue
import subprocess
import time


@dataclass
class Job:
    sequence: int
    audio: object
    captured: float
    last_voice: float
    started: float = 0


class Scheduler:
    def __init__(self, local, remote=None, argus=None, clock=time.monotonic, on_dispatch=lambda *_: None):
        self.local, self.remote, self.clock, self.on_dispatch = local, remote, clock, on_dispatch
        self.decoders = {name: decoder for name, decoder in
                         [('Nexus', remote), ('Syra', local), ('Argus', argus)] if decoder is not None}
        # Dedicated single-thread pools keep each decoder and SSH stream serial.
        self.pools = {name: ThreadPoolExecutor(max_workers=1, thread_name_prefix='stt-' + name)
                      for name in self.decoders}
        self.active = {}
        self.completed = {}
        self.retry = []
        self.retry_after = {name: 0 for name in self.decoders}
        self.next_sequence = self.next_emit = 0
        self.closed = False

    @property
    def busy(self):
        return bool(self.active or self.completed or self.retry)

    def pump(self, pending):
        if self.closed:
            raise RuntimeError('Transcription scheduler is closed')
        for worker, (future, job) in list(self.active.items()):
            if not future.done():
                continue
            del self.active[worker]
            try:
                result = dict(future.result())
            except (OSError, ValueError, subprocess.SubprocessError):
                if worker == 'Syra':
                    raise
                self.decoders[worker].close()
                self.retry_after[worker] = self.clock() + 10
                # Same chunk waits for the one local slot, never an extra job.
                self.retry.append(job)
                self.retry.sort(key=lambda failed: failed.sequence)
                continue
            result['executor'] = worker if len(self.decoders) > 1 else 'local'
            self.completed[job.sequence] = (job, result, self.clock())

        ready = []
        while self.next_emit in self.completed:
            ready.append(self.completed.pop(self.next_emit))
            self.next_emit += 1

        while len(self.active) < len(self.decoders):
            if self.retry:
                if 'Syra' in self.active:
                    break
                worker, job = 'Syra', self.retry.pop(0)
            else:
                # Bound held results if an earlier chunk is unusually slow.
                if self.next_sequence - self.next_emit >= 8 + len(self.decoders):
                    break
                worker = next((name for name in self.decoders if name not in self.active
                               and self.clock() >= self.retry_after[name]), None)
                if worker is None:
                    break
                try:
                    audio, captured, last_voice = pending.get_nowait()
                except queue.Empty:
                    break
                job = Job(self.next_sequence, audio, captured, last_voice)
                self.next_sequence += 1
                job.started = self.clock()
            decoder = self.decoders[worker]
            self.active[worker] = (self.pools[worker].submit(decoder.decode, job.audio), job)
            self.on_dispatch(worker, job.sequence)
        return ready

    def close(self):
        self.closed = True
        for pool in self.pools.values():
            pool.shutdown(wait=True, cancel_futures=True)
        for name, decoder in self.decoders.items():
            if name != 'Syra':
                decoder.close()
