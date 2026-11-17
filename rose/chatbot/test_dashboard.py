"""GTK routing and resize checks; no microphone, API calls, or speech playback."""
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from dashboard import Window
from dashboard_views import Gtk, GdkPixbuf, fit_size, camera_image


def contents(view):
    buffer = view.get_buffer()
    return buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)


def pump():
    until = time.monotonic() + .15
    while time.monotonic() < until:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        time.sleep(.01)


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.window = Window(start_listener=False)
        pump()

    def tearDown(self):
        self.window.close()
        self.window.destroy()
        pump()

    def test_inputs_replies_and_raw_outputs_go_to_separate_panels(self):
        window = self.window
        window.event({'type': 'heard', 'text': 'Microphone phrase'})
        window.event({'type': 'input', 'source': 'keyboard', 'text': 'Typed phrase'})
        with patch('dashboard.settings', return_value={'speak': True}):
            window.event({'type': 'reply', 'text': 'Spoken sentence', 'seconds': .5})
        window.event({'type': 'tool', 'name': 'shell', 'state': 'finished',
                      'result': {'ok': True, 'output': 'RAW_STDOUT_ONLY'}})
        self.assertIn('Microphone phrase', contents(window.inputs))
        self.assertIn('Typed phrase', contents(window.inputs))
        self.assertNotIn('Spoken sentence', contents(window.inputs))
        self.assertIn('Spoken sentence', contents(window.speech))
        self.assertNotIn('RAW_STDOUT_ONLY', contents(window.speech))
        self.assertIn('RAW_STDOUT_ONLY', contents(window.tools))

    def test_camera_preview_fits_resized_window_and_other_tools_restore_text(self):
        window = self.window
        window.open_display()
        with tempfile.TemporaryDirectory() as folder:
            photo = Path(folder) / 'camera.jpg'
            pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, 800, 400)
            pixbuf.fill(0x227744ff)
            pixbuf.savev(str(photo), 'jpeg', [], [])
            output = 'Nyx camera log\n' + json.dumps({'runs': [{'image': str(photo), 'metadata': 'data.json'}]})
            self.assertEqual(camera_image(output), photo)
            window.event({'type': 'tool', 'name': 'camera_detect', 'state': 'finished',
                          'result': {'ok': True, 'output': output}})
            for size in ((760, 500), (360, 240), (900, 600)):
                window.display_window.resize(*size)
                pump()
                scaled = window.display_photo.scaled
                self.assertIsNotNone(scaled)
                self.assertLessEqual(scaled.get_width(), window.display_photo.get_allocated_width())
                self.assertLessEqual(scaled.get_height(), window.display_photo.get_allocated_height())
                self.assertAlmostEqual(scaled.get_width() / scaled.get_height(), 2, delta=.03)
            window.event({'type': 'tool', 'name': 'shell', 'state': 'running', 'arguments': {'command': 'true'}})
            self.assertIn('camera_detect', contents(window.tools))
            self.assertIn('shell', contents(window.tools))
            self.assertIsNotNone(window.display_photo.original)

    def test_panel_proportion_survives_window_resize(self):
        window = self.window
        window.top.set_position(round(window.top.extent * .65))
        pump()
        ratio = window.top.ratio
        window.resize(900, 620)
        pump()
        self.assertAlmostEqual(window.top.ratio, ratio, delta=.015)
        self.assertAlmostEqual(window.top.get_position() / window.top.extent, ratio, delta=.015)

    def test_fit_math_preserves_shape(self):
        self.assertEqual(fit_size(1920, 1080, 640, 480), (640, 360))
        self.assertEqual(fit_size(1080, 1920, 640, 480), (270, 480))

    def test_default_voice_diagnostics_do_not_enter_dialogue_or_tool_panel(self):
        window = self.window
        with patch('dashboard.settings', return_value={'speak': True}):
            window.event({'type': 'reply', 'text': 'Hello Noob.', 'seconds': .1})
        window.event({'type': 'tool', 'name': 'rose_speech', 'state': 'finished',
                      'result': {'ok': True, 'output': 'VOICE_AND_HUE_INTERNAL_LOGS'}})
        self.assertEqual(contents(window.tools), '')
        self.assertNotIn('playback completed', contents(window.speech))
        self.assertNotIn('VOICE_AND_HUE_INTERNAL_LOGS', contents(window.speech))


if __name__ == '__main__':
    unittest.main()
