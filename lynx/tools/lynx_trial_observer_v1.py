"""Passive sysfs USB transitions with a durable, bounded trial receipt."""
import atexit
import json
from pathlib import Path
import threading
import time


class USBObserver:
    def __init__(self, output):
        self.output = output
        self.started = time.monotonic()
        self.started_ns = time.time_ns()
        self.events = []
        self.failure = None
        self.seen_fastboot = False
        self.departed = False
        self.finished = False
        self.ready = threading.Event()
        self.returned = threading.Event()
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)

    @staticmethod
    def snapshot():
        found = []
        for path in Path('/sys/bus/usb/devices').iterdir():
            try:
                vendor = (path / 'idVendor').read_text().strip()
                product = (path / 'idProduct').read_text().strip()
                identifier = vendor + ':' + product
                if identifier not in ['0e8d:201c', '22d9:0006', '0e8d:2000', '0e8d:2001', '1d6b:0104']:
                    continue
                found.append(dict(sysfs=str(path), identifier=identifier,
                                  bus=(path / 'busnum').read_text().strip(),
                                  device=(path / 'devnum').read_text().strip()))
            except OSError:
                continue
        return sorted(found, key=lambda item: item['sysfs'])

    def record(self, state):
        fastboot = any(item['identifier'] == '0e8d:201c' for item in state)
        if self.seen_fastboot and not fastboot:
            self.departed = True
        if self.departed and fastboot:
            self.returned.set()
        self.seen_fastboot |= fastboot
        if not self.events or self.events[-1]['usb'] != state:
            self.events.append(dict(wall_time_ns=time.time_ns(), elapsed_seconds=time.monotonic() - self.started, usb=state))

    def save(self):
        temporary = self.output.with_suffix('.tmp')
        temporary.write_text(json.dumps(dict(started_ns=self.started_ns, elapsed_seconds=time.monotonic() - self.started,
                                            heartbeat_ns=time.time_ns(), observation_complete=self.finished,
                                            initial_fastboot_seen=self.seen_fastboot, departure_observed=self.departed,
                                            fastboot_return_observed=self.returned.is_set(), error=self.failure,
                                            phone_commands_sent=False, poll_interval_seconds=0.25, events=self.events), indent=2) + '\n')
        temporary.replace(self.output)

    def run(self):
        try:
            while not self.stop_event.is_set():
                self.record(self.snapshot())
                self.save()
                self.ready.set()
                self.stop_event.wait(0.25)
        except Exception as error:
            self.failure = repr(error)
        finally:
            self.finished = True
            self.save()

    def start(self):
        self.thread.start()
        atexit.register(self.stop)
        if not self.ready.wait(3) or self.failure or not self.seen_fastboot:
            self.stop()
            raise RuntimeError('Passive observer did not become ready with Fastboot present')

    def observe_return(self, seconds):
        result = self.returned.wait(seconds)
        self.stop()
        return result

    def stop(self):
        self.stop_event.set()
        if self.thread.is_alive():
            self.thread.join(timeout=3)
