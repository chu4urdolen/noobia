#!/usr/bin/env python3
"""Rose's four-panel dashboard and independent camera-aware tool window."""
import json
from pathlib import Path
import socket
import tempfile
import threading
import time
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Gdk
from core import settings, save_settings
from server import SOCKET
from dashboard_views import panel, scroll, text_view, RatioPane, Photo, camera_image

LAYOUT = Path.home() / '.config/rose-chat/layout.json'
CSS = b'''
window, dialog { background-color: #000000; color: #a8eeb8; }
.rose-panel { border: 1px solid #32c96c; background-color: #000000; }
.rose-title { color: #62ed94; font-weight: bold; padding: 4px 2px; }
textview, textview text { background-color: #000000; color: #c3f2cc; font-family: monospace; font-size: 14px; }
entry { background: #000000; color: #c3f2cc; border: 1px solid #32c96c; }
button { background: #07130b; color: #a8eeb8; border: 1px solid #287a43; box-shadow: none; }
button:hover, button:checked { background: #12391f; border-color: #62ed94; }
scrolledwindow, viewport { background-color: #000000; }
label { color: #a8eeb8; }
'''


class Window(Gtk.Window):
    def __init__(self, start_listener=True):
        super().__init__(title='Rose · Controls')
        self.connection = None
        self.alive = True
        self.display_window = None
        self.display_photo = None
        self.current_camera_path = None
        self.fullscreen_controls = False
        self.fullscreen_display = False
        self.save_timer = None
        self.start_listener = start_listener
        try:
            self.layout = json.loads(LAYOUT.read_text())
        except (OSError, ValueError):
            self.layout = {}
        self.set_default_size(*self.layout.get('main_size', [1080, 760]))
        self.set_size_request(600, 420)
        css = Gtk.CssProvider()
        css.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.connect('delete-event', self.close)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=12)
        self.add(outer)
        controls = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, row_spacing=6, column_spacing=6,
                               min_children_per_line=1, max_children_per_line=6)
        self.mic = Gtk.ToggleButton(label='Microphone · English')
        self.mic_handler = self.mic.connect('toggled', lambda button: self.send(type='microphone', enabled=button.get_active()))
        controls.insert(self.mic, -1)
        for label, handler in [('Stop response', lambda *_: self.send(type='cancel')),
                               ('New chat', self.clear), ('Settings', self.configure),
                               ('Display', self.open_display), ('Stop video', self.stop_video),
                               ('YouTube sign in', self.youtube_login), ('Close GUI', self.exit_gui)]:
            button = Gtk.Button(label=label)
            button.connect('clicked', handler)
            controls.insert(button, -1)
        outer.pack_start(controls, False, False, 0)
        self.status = Gtk.Label(label='Connecting…', xalign=0)
        outer.pack_start(self.status, False, False, 0)
        self.mic_status = Gtk.Label(label='Microphone · connecting…', xalign=0)
        outer.pack_start(self.mic_status, False, False, 0)
        self.hardware_status = Gtk.Label(label='Hardware · checking connected devices…', xalign=0)
        self.hardware_status.set_line_wrap(True)
        outer.pack_start(self.hardware_status, False, False, 0)
        self.inputs = text_view()
        self.speech = text_view()
        self.entry = text_view(editable=True)
        self.entry.connect('key-press-event', self.keyboard_key)
        self.tools_buffer = Gtk.TextBuffer()
        self.tools = text_view(self.tools_buffer)
        self.top = RatioPane(Gtk.Orientation.HORIZONTAL, self.layout.get('top_ratio', .5), self.schedule_save)
        self.top.pack1(panel('INPUT HISTORY · keyboard and microphone', scroll(self.inputs)), True, False)
        self.top.pack2(panel('ROSE · spoken replies', scroll(self.speech)), True, False)
        keyboard = panel('KEYBOARD · Ctrl+Enter to send', scroll(self.entry))
        button = Gtk.Button(label='Send to Rose')
        button.connect('clicked', self.submit)
        keyboard.pack_start(button, False, False, 0)
        self.bottom = RatioPane(Gtk.Orientation.HORIZONTAL, self.layout.get('bottom_ratio', .5), self.schedule_save)
        self.bottom.pack1(keyboard, True, False)
        self.bottom.pack2(panel('TOOLS · commands and results', scroll(self.tools)), True, False)
        self.split = RatioPane(Gtk.Orientation.VERTICAL, self.layout.get('vertical_ratio', .58), self.schedule_save)
        self.split.pack1(self.top, True, False)
        self.split.pack2(self.bottom, True, False)
        outer.pack_start(self.split, True, True, 0)
        self.timing = Gtk.Label(label='Reply timing and API token counts appear here.', xalign=0)
        outer.pack_start(self.timing, False, False, 0)
        hint = Gtk.Label(label='Microphone gathers phrases · “love” sends the batch · closing the GUI keeps Rose listening', xalign=0)
        hint.set_line_wrap(True)
        outer.pack_start(hint, False, False, 0)
        self.connect('configure-event', lambda *_: self.schedule_save())
        self.connect('key-press-event', self.window_key)
        if start_listener:
            self.place_controls()
        self.show_all()
        if start_listener:
            self.open_display()
            threading.Thread(target=self.restore_display_mode, daemon=True).start()
            display = Gdk.Display.get_default()
            display.connect('monitor-added', lambda *_: GLib.idle_add(self.monitors_changed))
            display.connect('monitor-removed', lambda *_: GLib.idle_add(self.monitors_changed))
            threading.Thread(target=self.listen, daemon=True).start()

    def restore_display_mode(self):
        try:
            from media_client import request
            state = request({'action': 'status'})
            GLib.idle_add(self.event, {'type': 'display_state', 'mode': state['mode']})
        except (OSError, ValueError, KeyError):
            pass

    def schedule_save(self):
        if self.save_timer:
            GLib.source_remove(self.save_timer)
        if self.alive and self.start_listener:
            self.save_timer = GLib.timeout_add(500, self.save_layout)
        return False

    def save_layout(self):
        self.save_timer = None
        self.layout.update(main_size=list(self.get_size()), top_ratio=self.top.ratio,
            bottom_ratio=self.bottom.ratio, vertical_ratio=self.split.ratio)
        if self.display_window:
            self.layout['display_size'] = list(self.display_window.get_size())
        LAYOUT.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.NamedTemporaryFile(mode='w', dir=LAYOUT.parent, delete=False) as file:
            json.dump(self.layout, file)
            temporary = Path(file.name)
        temporary.replace(LAYOUT)
        return False

    def output_indices(self):
        display = Gdk.Display.get_default()
        screen = self.get_screen()
        names = [screen.get_monitor_plug_name(i) or '' for i in range(display.get_n_monitors())]
        preferred_control = self.layout.get('control_output', 'DSI-2')
        control = next((i for i, name in enumerate(names) if name == preferred_control),
                       next((i for i, name in enumerate(names) if name.startswith('DSI')), 0))
        preferred_display = self.layout.get('display_output', 'HDMI-A-2')
        output = next((i for i, name in enumerate(names) if name == preferred_display and i != control),
                      next((i for i, name in enumerate(names) if name.startswith('HDMI') and i != control), None))
        if names:
            self.layout['control_output'] = names[control]
        if output is not None:
            self.layout['display_output'] = names[output]
        return control, output

    def place_controls(self):
        control, _ = self.output_indices()
        self.fullscreen_on_monitor(self.get_screen(), control)
        self.fullscreen_controls = True

    def open_display(self, *_):
        _, output = self.output_indices()
        if self.start_listener and output is None:
            self.status.set_text('No HDMI screen is connected for the display window')
            return
        if self.display_window is None:
            self.display_window = Gtk.Window(title='Rose · Display')
            self.display_window.set_default_size(*self.layout.get('display_size', [680, 440]))
            self.display_window.set_size_request(160, 120)
            self.display_window.connect('delete-event', lambda window, *_: (window.hide(), True)[1])
            self.display_window.connect('configure-event', lambda *_: self.schedule_save())
            self.display_window.connect('key-press-event', self.window_key)
            self.display_photo = Photo()
            self.display_window.add(self.display_photo)
            if self.current_camera_path:
                self.display_photo.load(self.current_camera_path)
        if self.start_listener and output is not None:
            self.display_window.fullscreen_on_monitor(self.get_screen(), output)
            self.fullscreen_display = True
        self.display_window.show_all()

    def media_command(self, action):
        def command():
            from media_client import request
            try:
                result = request({'action': action})
                if not result.get('ok', True):
                    GLib.idle_add(self.status.set_text, 'Display request failed')
            except (OSError, ValueError):
                GLib.idle_add(self.status.set_text, 'Display service is unavailable')
        threading.Thread(target=command, daemon=True).start()

    def stop_video(self, *_):
        self.media_command('stop')

    def youtube_login(self, *_):
        self.media_command('login')

    def monitors_changed(self):
        self.place_controls()
        _, output = self.output_indices()
        if output is None and self.display_window:
            self.display_window.hide()
        else:
            self.open_display()
        return False

    def window_key(self, window, event):
        if event.keyval == Gdk.KEY_F11:
            if window is self:
                if self.fullscreen_controls:
                    self.unfullscreen()
                    self.fullscreen_controls = False
                else:
                    self.place_controls()
            elif self.display_window:
                if self.fullscreen_display:
                    self.display_window.unfullscreen()
                    self.fullscreen_display = False
                else:
                    self.open_display()
            return True
        return False

    def exit_gui(self, *_):
        self.close()
        self.destroy()

    def close(self, *_):
        if self.start_listener:
            self.save_layout()
        self.alive = False
        if self.save_timer:
            GLib.source_remove(self.save_timer)
        if self.display_window:
            self.display_window.destroy()
        if self.connection:
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.connection.close()
        if Gtk.main_level():
            Gtk.main_quit()
        return False

    def send(self, **command):
        try:
            if not self.connection:
                raise OSError()
            self.connection.sendall((json.dumps(command) + '\n').encode())
            return True
        except OSError:
            self.status.set_text('Waiting for Rose’s backend…')
            return False

    def submit(self, *_):
        buffer = self.entry.get_buffer()
        text = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True).strip()
        if text and self.send(type='submit', text=text, source='keyboard'):
            buffer.set_text('')

    def keyboard_key(self, widget, event):
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and event.state & Gdk.ModifierType.CONTROL_MASK:
            self.submit()
            return True
        return False

    def clear(self, *_):
        self.send(type='clear')

    def append(self, view, text):
        buffer = self.tools_buffer if view == 'tools' else view.get_buffer()
        buffer.insert(buffer.get_end_iter(), text + '\n\n')
        if buffer.get_char_count() > 100000:
            buffer.delete(buffer.get_start_iter(), buffer.get_iter_at_offset(buffer.get_char_count() - 80000))
        mark = buffer.create_mark(None, buffer.get_end_iter(), False)
        targets = [self.tools] if view == 'tools' else [view]
        for target in targets:
            target.scroll_mark_onscreen(mark)
        buffer.delete_mark(mark)

    def event(self, event):
        kind = event.get('type')
        stamp = time.strftime('%H:%M:%S', time.localtime(event.get('timestamp', time.time())))
        if kind == 'input':
            self.append(self.inputs, stamp + ' · Sent · ' + event['source'] + '\n' + event['text'])
        elif kind == 'heard':
            if event['text'].strip():
                self.append(self.inputs, stamp + ' · Mic · gathering\n' + event['text'])
        elif kind == 'microphone_state':
            self.mic_status.set_text(event['text'])
        elif kind == 'microphone_audio':
            self.mic_status.set_text('Microphone connected · ' + ('speech detected' if event.get('speech') else 'listening') + f" · level {event.get('level', 0):.3f}")
        elif kind == 'hardware':
            missing = [name.replace('_', ' ') for name, item in event.get('usb', {}).items() if not item.get('present')]
            self.hardware_status.set_text('Hardware · ' + ('missing: ' + ', '.join(missing) if missing else 'USB devices connected') + (' · speaker connected' if event.get('speaker_connected') else ' · speaker reconnecting'))
        elif kind == 'display_state':
            if event['mode'] in {'video', 'login'}:
                if self.display_window:
                    self.display_window.hide()
            else:
                self.open_display()
                if self.display_window:
                    self.display_window.present()
        elif kind == 'reply':
            self.append(self.speech, stamp + ' · Rose\n' + event['text'])
            self.timing.set_text(f"Reply ready in {event['seconds']:.2f}s")
        elif kind == 'state':
            self.status.set_text(event['text'])
            if 'mic' in event:
                self.mic.handler_block(self.mic_handler)
                self.mic.set_active(event['mic'])
                self.mic.handler_unblock(self.mic_handler)
            if event['text'] == 'Conversation cleared':
                for buffer in (self.inputs.get_buffer(), self.speech.get_buffer(), self.tools_buffer):
                    buffer.set_text('')
        elif kind == 'error':
            self.append('tools', stamp + ' · Error\n' + event['text'])
            self.status.set_text(event['text'])
        elif kind == 'tool':
            name = event['name']
            if name in {'speech', 'rose_speech'}:
                if event['state'] == 'running' and isinstance(event.get('arguments', {}).get('text'), str):
                    self.append(self.speech, stamp + ' · Rose\n' + event['arguments']['text'])
                elif event['state'] == 'finished' and not event.get('result', {}).get('ok'):
                    self.status.set_text('Voice output failed · check the speaker connection')
                return False
            if event['state'] == 'running':
                args = event.get('arguments', {})
                self.append('tools', stamp + ' · ' + name + ' · running\n' + json.dumps(args, ensure_ascii=False))
                if name in {'speech', 'rose_speech'} and isinstance(args.get('text'), str):
                    self.append(self.speech, stamp + ' · Rose\n' + args['text'])
            else:
                result = event['result']
                detail = result.get('output', result.get('error', ''))
                self.append('tools', stamp + ' · ' + name + (' · completed' if result.get('ok') else ' · failed') + '\n' + detail)
                if name in {'camera_snapshot', 'camera_detect', 'rose_camera_snapshot', 'rose_camera_detect', 'rose_camera'}:
                    path = camera_image(detail) if result.get('ok') else None
                    if path:
                        try:
                            self.current_camera_path = path
                            self.open_display()
                            if self.display_photo:
                                self.display_photo.load(path)
                            if self.start_listener:
                                self.stop_video()
                        except GLib.Error:
                            self.append('tools', 'Camera image could not be decoded; see the result path above.')
        elif kind == 'usage':
            self.timing.set_text(f"API tokens · in {event.get('input_tokens', 0)} · out {event.get('output_tokens', 0)}")
        return False

    def listen(self):
        while self.alive:
            try:
                with socket.socket(socket.AF_UNIX) as connection:
                    connection.connect(str(SOCKET))
                    self.connection = connection
                    connection.sendall(b'{"type":"subscribe"}\n')
                    with connection.makefile('r') as stream:
                        for line in stream:
                            if not self.alive:
                                break
                            GLib.idle_add(self.event, json.loads(line))
            except (OSError, ValueError):
                GLib.idle_add(self.status.set_text, 'Waiting for Rose’s backend…')
            finally:
                self.connection = None
            time.sleep(1)

    def configure(self, *_):
        config = settings()
        dialog = Gtk.Dialog(title='Rose · Private API settings', transient_for=self, modal=True)
        dialog.add_buttons('Cancel', Gtk.ResponseType.CANCEL, 'Save', Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_spacing(8)
        box.set_border_width(12)
        for label in ('API key (saved privately on this computer)',):
            box.pack_start(Gtk.Label(label=label, xalign=0), False, False, 0)
        key = Gtk.Entry(visibility=False)
        key.set_text(config.get('api_key', ''))
        box.pack_start(key, False, False, 0)
        box.pack_start(Gtk.Label(label='Responses model', xalign=0), False, False, 0)
        model = Gtk.Entry()
        model.set_text(config.get('model', 'gpt-5.4-mini'))
        box.pack_start(model, False, False, 0)
        box.pack_start(Gtk.Label(label='YouTube Data API key (for search)', xalign=0), False, False, 0)
        youtube_key = Gtk.Entry(visibility=False)
        youtube_key.set_text(config.get('youtube_api_key', ''))
        box.pack_start(youtube_key, False, False, 0)
        speak = Gtk.CheckButton(label='Speak every reply with the Hue lights')
        speak.set_active(config.get('speak', True))
        box.pack_start(speak, False, False, 0)
        box.pack_start(Gtk.Label(label='English microphone transcripts and typed text go to OpenAI when sent.', xalign=0), False, False, 0)
        dialog.show_all()
        if dialog.run() == Gtk.ResponseType.OK:
            config.update(api_key=key.get_text().strip(), model=model.get_text().strip(), speak=speak.get_active(),
                          youtube_api_key=youtube_key.get_text().strip())
            save_settings(config)
            self.status.set_text('Settings saved')
        dialog.destroy()
