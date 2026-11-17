import queue
import threading
import time
import unittest
from transcription_scheduler import Scheduler


class BlockingDecoder:
    def __init__(self):
        self.started = {}
        self.release = {}
        self.calls = []
        self.lock = threading.Lock()

    def decode(self, audio):
        with self.lock:
            self.calls.append(audio)
            gate = self.release.setdefault(audio, threading.Event())
            self.started.setdefault(audio, threading.Event()).set()
        if not gate.wait(3):
            raise TimeoutError('Test worker not released')
        return {'text': str(audio), 'language': 'en', 'worker_decode_seconds': .01}

    def allow(self, *ids):
        with self.lock:
            for i in ids:
                self.release.setdefault(i, threading.Event()).set()

    def close(self):
        self.allow(*range(20))


def wait_until(check, timeout=1):
    deadline = time.monotonic() + timeout
    while not check():
        if time.monotonic() > deadline:
            raise AssertionError('Timed out waiting for test worker')
        time.sleep(.005)


def source(count):
    result = queue.Queue()
    for i in range(count):
        result.put((i, time.monotonic(), time.monotonic()))
    return result


class SchedulerTests(unittest.TestCase):
    def test_two_jobs_max_fifo_dispatch_time_choice_and_ordered_results(self):
        nexus, syra = BlockingDecoder(), BlockingDecoder()
        scheduler = Scheduler(syra, nexus)
        pending = source(4)
        try:
            self.assertEqual(scheduler.pump(pending), [])
            wait_until(lambda: nexus.calls == [0] and syra.calls == [1])
            self.assertEqual(pending.qsize(), 2)
            syra.allow(1)
            wait_until(lambda: scheduler.active['Syra'][0].done())
            self.assertEqual(scheduler.pump(pending), [])
            wait_until(lambda: syra.calls == [1, 2])
            self.assertEqual(len(scheduler.active), 2)
            nexus.allow(0)
            wait_until(lambda: scheduler.active['Nexus'][0].done())
            ready = scheduler.pump(pending)
            self.assertEqual([j.sequence for j, _, _ in ready], [0, 1])
            # Chunk 3 wasn't reserved for Syra: it goes to now-free Nexus.
            wait_until(lambda: nexus.calls == [0, 3])
            nexus.allow(3)
            wait_until(lambda: scheduler.active['Nexus'][0].done())
            self.assertEqual(scheduler.pump(pending), [])
            syra.allow(2)
            wait_until(lambda: scheduler.active['Syra'][0].done())
            ready = scheduler.pump(pending)
            self.assertEqual([j.sequence for j, _, _ in ready], [2, 3])
        finally:
            nexus.close(); syra.close(); scheduler.close()

    def test_optional_argus_is_third_and_never_runs_a_fourth_job(self):
        nexus, syra, argus = [BlockingDecoder() for _ in range(3)]
        scheduler = Scheduler(syra, nexus, argus)
        pending = source(4)
        try:
            scheduler.pump(pending)
            wait_until(lambda: nexus.calls == [0] and syra.calls == [1] and argus.calls == [2])
            self.assertEqual(len(scheduler.active), 3)
            self.assertEqual(pending.qsize(), 1)
            nexus.allow(0)
            wait_until(lambda: scheduler.active['Nexus'][0].done())
            ready = scheduler.pump(pending)
            self.assertEqual(ready[0][0].sequence, 0)
            wait_until(lambda: nexus.calls == [0, 3])
            self.assertEqual(len(scheduler.active), 3)
        finally:
            for decoder in (nexus, syra, argus): decoder.close()
            scheduler.close()

    def test_remote_failure_waits_for_local_slot_without_concurrent_local_decodes(self):
        class Failed:
            def decode(self, audio): raise ConnectionError('offline')
            def close(self): pass
        syra = BlockingDecoder()
        scheduler = Scheduler(syra, Failed())
        pending = source(3)
        try:
            scheduler.pump(pending)
            wait_until(lambda: scheduler.active['Nexus'][0].done() and syra.calls == [1])
            scheduler.pump(pending)
            self.assertEqual(syra.calls, [1])
            self.assertEqual(pending.qsize(), 1)
            syra.allow(1)
            wait_until(lambda: scheduler.active['Syra'][0].done())
            scheduler.pump(pending)
            wait_until(lambda: syra.calls == [1, 0])
            syra.allow(0)
            wait_until(lambda: scheduler.active['Syra'][0].done())
            ready = scheduler.pump(pending)
            self.assertEqual([j.sequence for j, _, _ in ready], [0, 1])
            self.assertEqual(ready[0][1]['executor'], 'Syra')
        finally:
            syra.close(); scheduler.close()
