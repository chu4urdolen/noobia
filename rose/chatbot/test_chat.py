import json
from pathlib import Path
import tempfile
import unittest
from core import Conversation, Tools


class FakeTools:
    def __init__(self):
        import threading
        self.cancelled = threading.Event()
        self.calls = []

    def definitions(self):
        return []

    def run(self, name, args):
        self.calls.append((name, args))
        return {'ok': True, 'output': 'light is reachable'}


class ChatTests(unittest.TestCase):
    def test_response_punctuation_filter_keeps_only_requested_marks(self):
        from core import clean_response
        self.assertEqual(clean_response('**Hello** (Noob) - this   is _Rose_. Yes, really!?'),
                         'Hello Noob this is Rose . Yes, really!?')
        self.assertEqual(clean_response('“I\'m”\tready:\n`now`.'), 'I m ready now .')
    def test_reasoning_and_function_outputs_survive_continuation(self):
        tools = FakeTools()
        payloads = []
        def request(payload, key):
            payloads.append(payload)
            if len(payloads) == 1:
                return {'output': [dict(type='reasoning', id='r1', encrypted_content='opaque'),
                    dict(type='function_call', name='rose_hue_strip', call_id='c1', arguments='{"action":"status","brightness":null}')],
                    'status': 'completed'}
            return {'output': [dict(type='message', role='assistant', content=[dict(type='output_text', text='Ready.')])],
                    'status': 'completed'}
        chat = Conversation(tools, request)
        self.assertEqual(chat.respond('Check the light', config={'api_key': 'test'}), 'Ready.')
        self.assertEqual(payloads[1]['input'][1]['type'], 'reasoning')
        self.assertEqual(payloads[1]['input'][-1]['call_id'], 'c1')
        self.assertEqual([call[0] for call in tools.calls], ['rose_hue_strip', 'rose_speech'])
        self.assertFalse(payloads[0]['store'])

    def test_no_key_does_not_send_or_speak(self):
        tools = FakeTools()
        with self.assertRaises(RuntimeError):
            Conversation(tools, lambda *_: self.fail('Should not call API')).respond('Hi', config={})
        self.assertEqual(tools.calls, [])

    def test_cancel_after_response_prevents_tools(self):
        tools = FakeTools()
        def request(*_):
            tools.cancelled.set()
            return {'output': [dict(type='function_call', name='speech', call_id='c1', arguments='{}')]}
        with self.assertRaisesRegex(RuntimeError, 'Cancelled'):
            Conversation(tools, request).respond('Hi', config={'api_key': 'test'})
        self.assertFalse(tools.calls)

    def test_registry_does_not_execute_shell_text_or_unknown_tools(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            marker = directory / 'injected'
            (directory / 'echo.sh').write_text('#!/bin/sh\nprintf "%s" "$1"\n')
            tools = Tools(directory)
            argument = '$(touch ' + str(marker) + ')'
            result = tools.run('echo', {'argv': [argument]})
            self.assertTrue(result['ok'])
            self.assertEqual(result['output'], argument)
            self.assertFalse(marker.exists())
            self.assertFalse(tools.run('missing', {})['ok'])
            self.assertFalse(tools.run('echo', {'argv': 'wrong type'})['ok'])

    def test_wrapper_timeout_kills_child(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            (directory / 'sleep.sh').write_text('#!/bin/sh\nsleep 30\n')
            (directory / 'sleep.json').write_text(json.dumps(dict(description='test', timeout=1,
                protocol='argv', parameters={'type': 'object', 'properties': {'argv': {'type': 'array', 'items': {'type': 'string'}}},
                'required': ['argv'], 'additionalProperties': False})))
            self.assertEqual(Tools(directory).run('sleep', {'argv': []})['error'], 'Tool timed out')

    def test_syra_power_off_is_not_in_schema(self):
        from jsonschema import ValidationError, validate
        schema = Tools().registry()['syra_plug'][1]['parameters']
        with self.assertRaises(ValidationError):
            validate({'action': 'off'}, schema)

    def test_tool_descriptions_are_wrapper_help_stdout(self):
        definitions = {item['name']: item for item in Tools().definitions()}
        from wrapper_help import render
        self.assertEqual(definitions['rose_shell']['description'], render(Tools().directory / 'rose_shell.sh').strip())
        self.assertIn('command (string, required)', definitions['rose_shell']['description'])
        self.assertIn('Allowed values: status, on, off, toggle', definitions['rose_hue_strip']['description'])

    def test_shell_returns_combined_outputs_and_real_exit_status(self):
        result = Tools().run('rose_shell', {'command': "printf 'normal output'; printf 'error output' >&2; exit 7"})
        self.assertFalse(result['ok'])
        self.assertEqual(result['exit_code'], 7)
        self.assertIn('normal output', result['output'])
        self.assertIn('error output', result['output'])

    def test_love_triggers_batch_of_all_prior_phrases(self):
        from server import SpeechBuffer
        buffer = SpeechBuffer()
        self.assertIsNone(buffer.add('Rose awake please.'))
        self.assertIsNone(buffer.add('Look at the lovely lights.'))
        self.assertEqual(buffer.add('What do you think, LOVE?'),
            'Rose awake please.\nLook at the lovely lights.\nWhat do you think, LOVE?')
        self.assertEqual(buffer.phrases, [])
        self.assertIsNone(buffer.add('A new thought.'))
        self.assertEqual(buffer.add('love'), 'A new thought.\nlove')

    def test_microphone_control_protocol_changes_state_and_reports_it(self):
        import socket
        import threading
        from types import SimpleNamespace
        from unittest.mock import patch
        from server import Server, Handler, SpeechBuffer
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / 'chat.sock')
            with Server(path, Handler) as server:
                server.app = SimpleNamespace(mic=True, speech_buffer=SpeechBuffer(),
                    close_microphone=lambda: None, emit=lambda *_: None,
                    lock=threading.Lock(), clients=set())
                worker = threading.Thread(target=server.serve_forever, daemon=True)
                worker.start()
                with patch('server.settings', return_value={}), patch('server.save_settings') as save:
                    with socket.socket(socket.AF_UNIX) as connection:
                        connection.connect(path)
                        with connection.makefile('r') as stream:
                            for enabled in (False, True):
                                commands = [{'type': 'microphone', 'enabled': enabled}, {'type': 'microphone_status'}]
                                connection.sendall(('\n'.join(json.dumps(x) for x in commands) + '\n').encode())
                                self.assertEqual(json.loads(stream.readline())['enabled'], enabled)
                                self.assertEqual(save.call_args.args[0]['mic_enabled'], enabled)
                server.shutdown()
                worker.join()

    def test_delayed_self_speech_is_filtered_before_love_trigger(self):
        from unittest.mock import Mock
        from server import App, SpeechBuffer
        app = App.__new__(App)
        app.speaking_started = None
        app.spoken_intervals = [(100, 110.5)]
        app.speech_buffer = SpeechBuffer()
        app.emit = Mock()
        app.submit = Mock()
        # Recognition arrives after playback, but audio overlaps our own voice.
        self.assertFalse(app.accept_transcript(dict(text='with love', timestamp=115,
                                                   end_to_text_seconds=4, audio_seconds=3)))
        self.assertFalse(app.speech_buffer.phrases)
        self.assertTrue(app.accept_transcript(dict(text='First thought.', timestamp=121,
                                                  end_to_text_seconds=2, audio_seconds=3)))
        app.submit.assert_not_called()
        self.assertTrue(app.accept_transcript(dict(text='Second thought, love.', timestamp=125,
                                                  end_to_text_seconds=2, audio_seconds=2)))
        app.submit.assert_called_once_with('First thought.\nSecond thought, love.', 'microphone')


if __name__ == '__main__':
    unittest.main()
