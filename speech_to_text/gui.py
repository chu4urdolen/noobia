#!/usr/bin/python3
"""Desktop subscriber for Noobia's local English speech service."""
import json
import math
import os
from pathlib import Path
import socket
import threading
import time

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib


class SpeechWindow(Gtk.Window):
    def __init__(self):
        self.host_label = socket.gethostname()
        super().__init__(title=f'{self.host_label} · Speech speed test')
        self.set_default_size(780, 640)
        self.set_border_width(24)
        self.connect('destroy', self.close)
        self.generation = 0
        self.stopping = threading.Event()
        self.client = None
        self.running = False
        self.closed = False
        self.started = None
        self.rows = []
        self.path = str(Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')) / 'noobia-speech.sock')
        css = Gtk.CssProvider()
        css.load_from_data(b'''
            window { background: #121b24; color: #edf4f8; }
            label { color: #edf4f8; }
            .title { font-size: 27px; font-weight: bold; }
            .muted { color: #9fb2c2; }
            .metric { font-size: 26px; font-weight: bold; color: #71dcc2; }
            .card { background: #1c2936; border-radius: 10px; padding: 14px; }
            button { padding: 8px 18px; }
            textview, textview text { background: #1c2936; color: #edf4f8; font-size: 16px; }
            progressbar trough { background: #263b4c; min-height: 8px; }
            progressbar progress { background: #71dcc2; min-height: 8px; }
        ''')
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.add(box)
        box.pack_start(self.label('Speech → text', 'title'), False, False, 0)
        box.pack_start(self.label(f'English · local on {self.host_label} · ReSpeaker microphone', 'muted'), False, False, 0)
        controls = Gtk.Box(spacing=10)
        self.start_button = Gtk.Button(label='Start listening')
        self.start_button.connect('clicked', self.start)
        self.stop_button = Gtk.Button(label='Stop')
        self.stop_button.set_sensitive(False)
        self.stop_button.connect('clicked', self.stop)
        clear = Gtk.Button(label='Clear results')
        clear.connect('clicked', self.clear)
        for button in (self.start_button, self.stop_button, clear):
            controls.pack_start(button, False, False, 0)
        box.pack_start(controls, False, False, 0)
        self.status = self.label('Ready. Press Start, then read a few sentences aloud.', 'muted')
        self.status.set_line_wrap(True)
        box.pack_start(self.status, False, False, 0)
        cards = Gtk.Box(spacing=12, homogeneous=True)
        self.metrics = {}
        for key, title, tip in (
            ('delay', 'End → text', 'Approximate delay after the last detected speech block, including pause and decoding.'),
            ('decode', 'Decode time', 'CPU time to recognize the most recent audio phrase.'),
            ('speed', 'Decode speed', 'Audio duration divided by decoding time. Above 1× keeps up with live speech.')):
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            card.get_style_context().add_class('card')
            card.pack_start(self.label(title, 'muted'), False, False, 0)
            value = self.label('—', 'metric')
            card.pack_start(value, False, False, 0)
            card.set_tooltip_text(tip)
            self.metrics[key] = value
            cards.pack_start(card, True, True, 0)
        box.pack_start(cards, False, False, 0)
        meter_row = Gtk.Box(spacing=12)
        self.voice = self.label('Input level', 'muted')
        meter_row.pack_start(self.voice, False, False, 0)
        self.meter = Gtk.ProgressBar()
        meter_row.pack_start(self.meter, True, True, 0)
        box.pack_start(meter_row, False, False, 0)
        self.detail = self.label('Queue — · speaking pace — · audio —', 'muted')
        box.pack_start(self.detail, False, False, 0)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.text = Gtk.TextView()
        self.text.set_editable(False)
        self.text.set_cursor_visible(False)
        self.text.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.text.set_left_margin(16)
        self.text.set_right_margin(16)
        self.text.set_top_margin(14)
        self.text.set_bottom_margin(14)
        scroll.add(self.text)
        box.pack_start(scroll, True, True, 0)
        self.summary = self.label('No phrases yet.', 'muted')
        box.pack_start(self.summary, False, False, 0)
        footer = self.label('Pause between phrases to see results. Close or Stop to unsubscribe.\nAudio and text are not saved. Another subscriber can keep the microphone open.', 'muted')
        footer.set_line_wrap(True)
        box.pack_start(footer, False, False, 0)
        GLib.timeout_add(1000, self.tick)

    @staticmethod
    def label(text, style):
        label = Gtk.Label(label=text, xalign=0)
        label.get_style_context().add_class(style)
        return label

    def dispatch(self, generation, event):
        if self.closed or generation != self.generation:
            return False
        kind = event.get('type')
        if kind == 'audio':
            self.status.set_text('Listening in English. Read aloud, then pause.')
            level = max(0.0, event.get('level', 0))
            self.meter.set_fraction(min(1.0, math.sqrt(level)))
            self.voice.set_text('Voice detected' if event.get('speech') else 'Input level')
        elif kind == 'transcript':
            self.rows.append(event)
            elapsed = event['decode_seconds']
            audio = event['audio_seconds']
            self.metrics['delay'].set_text(f"≈{event['end_to_text_seconds']:.2f} s")
            self.metrics['decode'].set_text(f'{elapsed:.2f} s')
            self.metrics['speed'].set_text(f'{audio / elapsed:.1f}×' if elapsed > 0 else '—')
            voice = event['voice_seconds']
            wpm = f"≈{event['words'] * 60 / voice:.0f} WPM" if voice else '—'
            self.detail.set_text(f"Worker {event.get('executor', 'local')} · queue {event['queue_seconds']:.2f} s · speaking pace {wpm} · audio {audio:.1f} s")
            buffer = self.text.get_buffer()
            stamp = time.strftime('%H:%M:%S', time.localtime(event.get('timestamp', time.time())))
            text = event.get('text') or '(Speech detected, but no words recognized.)'
            buffer.insert(buffer.get_end_iter(), f'{stamp}   {text}\n\n')
            # Keep the window bounded during long sessions.
            if buffer.get_line_count() > 600:
                buffer.delete(buffer.get_start_iter(), buffer.get_iter_at_line(100))
            self.text.scroll_to_iter(buffer.get_end_iter(), 0, False, 0, 0)
            self.update_summary()
        elif kind == 'closed':
            self.running = False
            self.start_button.set_sensitive(True)
            self.stop_button.set_sensitive(False)
            self.status.set_text(event['message'])
            self.meter.set_fraction(0)
            self.voice.set_text('Input level')
        elif kind == 'status':
            message = event.get('message', '')
            if event.get('language') and event['language'] != 'en':
                self.stop()
                self.status.set_text('Service language is not English. Restart noobia-speech.service.')
            elif 'LISTENING' in message:
                self.status.set_text('Listening in English. Read aloud, then pause.')
            elif message.startswith('Subscribed'):
                self.status.set_text('Subscribed. Waiting for microphone audio…')
            elif message.startswith('Loading') or message.startswith('Transcriber stopped'):
                self.status.set_text(message)
        return False

    def start(self, *_):
        if self.running:
            return
        self.generation += 1
        generation = self.generation
        self.stopping = threading.Event()
        stop = self.stopping
        self.running = True
        self.started = time.monotonic()
        self.start_button.set_sensitive(False)
        self.stop_button.set_sensitive(True)
        self.status.set_text('Connecting to the speech service…')
        self.client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client = self.client
        client.settimeout(.5)

        def receive():
            message = 'Disconnected from speech service.'
            try:
                client.connect(self.path)
                buffered = b''
                while not stop.is_set():
                    try:
                        data = client.recv(65536)
                    except socket.timeout:
                        continue
                    if not data:
                        break
                    buffered += data
                    if len(buffered) > 1024 * 1024:
                        raise ValueError('Speech event exceeded size limit')
                    while b'\n' in buffered:
                        line, buffered = buffered.split(b'\n', 1)
                        GLib.idle_add(self.dispatch, generation, json.loads(line))
            except (OSError, ValueError) as exc:
                message = f'Could not receive speech: {exc}. Start noobia-speech.service and try again.'
            finally:
                client.close()
                if not stop.is_set():
                    GLib.idle_add(self.dispatch, generation, {'type': 'closed', 'message': message})
        threading.Thread(target=receive, daemon=True).start()

    def stop(self, *_):
        self.stopping.set()
        self.generation += 1
        self.running = False
        if self.client:
            try:
                self.client.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.client.close()
            self.client = None
        self.start_button.set_sensitive(True)
        self.stop_button.set_sensitive(False)
        self.status.set_text('Stopped. This window is no longer subscribed.')
        self.meter.set_fraction(0)
        self.voice.set_text('Input level')

    def clear(self, *_):
        self.rows.clear()
        self.text.get_buffer().set_text('')
        for metric in self.metrics.values():
            metric.set_text('—')
        self.detail.set_text('Queue — · speaking pace — · audio —')
        self.update_summary()

    def update_summary(self):
        if not self.rows:
            self.summary.set_text('No phrases yet.')
            return
        audio = sum(r['audio_seconds'] for r in self.rows)
        decode = sum(r['decode_seconds'] for r in self.rows)
        delay = sum(r['end_to_text_seconds'] for r in self.rows) / len(self.rows)
        self.summary.set_text(f'{len(self.rows)} phrases · average delay ≈{delay:.2f} s · overall decode {audio / decode:.1f}× realtime')

    def tick(self):
        if self.closed:
            return False
        elapsed = int(time.monotonic() - self.started) if self.running and self.started else 0
        self.set_title(f'{self.host_label} · Speech speed test · {elapsed}s' if self.running else f'{self.host_label} · Speech speed test')
        return True

    def close(self, *_):
        self.closed = True
        self.stop()
        Gtk.main_quit()


if __name__ == '__main__':
    window = SpeechWindow()
    window.show_all()
    Gtk.main()
