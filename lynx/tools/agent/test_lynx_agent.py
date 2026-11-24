import json
from pathlib import Path
import tempfile
import unittest

from lynx_agent import Catalog, respond


class AgentTest(unittest.TestCase):
    def test_catalog_and_function_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'lynx_status.json').write_text(json.dumps({
                'description': 'Read Lynx status', 'protocol': 'json-stdin',
                'parameters': {'type': 'object', 'properties': {}, 'required': [],
                               'additionalProperties': False}, 'timeout': 2}))
            (root / 'lynx_status.sh').write_text('#!/bin/sh\nprintf "status=ready\\n"\n')
            catalog = Catalog(root)
            seen = []

            def send(base, key, payload):
                self.assertEqual(base, 'http://local')
                self.assertEqual(key, 'secret')
                self.assertFalse(payload['store'])
                self.assertEqual([x['name'] for x in payload['tools']], ['lynx_status'])
                seen.append(payload)
                if len(seen) == 1:
                    return {'status': 'completed', 'output': [{
                        'type': 'function_call', 'name': 'lynx_status',
                        'arguments': '{}', 'call_id': 'call_1'}]}
                self.assertEqual(payload['input'][-1]['type'], 'function_call_output')
                self.assertIn('status=ready', payload['input'][-1]['output'])
                return {'status': 'completed', 'output': [{
                    'type': 'message', 'content': [{'type': 'output_text',
                                                   'text': 'Lynx is ready.'}]}]}

            self.assertEqual(respond('How is Lynx?', catalog=catalog,
                                     choose=lambda: ('http://local', 'model', 'secret'),
                                     send=send), 'Lynx is ready.')

    def _catalog(self, root):
        (root / 'lynx_status.json').write_text(json.dumps({
            'description': 'Read Lynx status', 'protocol': 'json-stdin',
            'parameters': {'type': 'object', 'properties': {}, 'required': [],
                           'additionalProperties': False}, 'timeout': 2}))
        (root / 'lynx_status.sh').write_text('#!/bin/sh\nprintf "status=ready\\n"\n')
        (root / 'lynx_speech.json').write_text(json.dumps({
            'description': 'Speak', 'parameters': {'type': 'object', 'properties': {
                'text': {'type': 'string'}}, 'required': ['text'], 'additionalProperties': False}}))
        (root / 'lynx_speech.sh').write_text('#!/bin/sh\nprintf "said\\n"\n')
        return Catalog(root)

    def _run(self, prompt):
        payloads = []

        def send(base, key, payload):
            payloads.append(payload)
            if len(payloads) == 1:
                return {'status': 'completed', 'output': [{
                    'type': 'function_call', 'name': 'lynx_status',
                    'arguments': '{}', 'call_id': 'c1'}]}
            return {'status': 'completed', 'output': [{
                'type': 'message', 'content': [{'type': 'output_text', 'text': 'Purr.'}]}]}
        with tempfile.TemporaryDirectory() as directory:
            respond(prompt, catalog=self._catalog(Path(directory)),
                    choose=lambda: ('http://local', 'model', 'secret'), send=send)
        return payloads

    def test_sense_job_is_one_call_with_a_tool_and_no_thinking(self):
        for prompt in ('SENSE: You see a cat.', '[sense] legacy job ... cat'):
            payloads = self._run(prompt)
            self.assertEqual(len(payloads), 1, "Tom 2026-11-24: one Qwen call per sense")
            self.assertEqual(payloads[0].get('tool_choice'), 'required')
            self.assertEqual(payloads[0].get('reasoning'), {'effort': 'none'})

    def test_sense_offers_only_expressive_tools_with_media_names(self):
        payloads = []
        def send(base, key, payload):
            payloads.append(payload)
            return {'status': 'completed', 'output': [{'type': 'function_call', 'name': 'lynx_speech',
                                                       'arguments': '{"text": "Hi."}', 'call_id': 'c1'}]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = self._catalog(root)
            for name, out in (('lynx_speech', 'said'), ('lynx_media_play', 'played'),
                              ('lynx_media_catalog', '{"sounds": ["chime"], "images": ["02_talking"]}')):
                (root / f'{name}.json').write_text(json.dumps({'description': name, 'parameters': {
                    'type': 'object', 'properties': {'text': {'type': 'string'}}, 'required': [],
                    'additionalProperties': False}}))
                (root / f'{name}.sh').write_text("#!/bin/sh\nprintf '%s'\n" % out)
            self.assertEqual(respond('SENSE: You see a cat.', catalog=catalog,
                                     choose=lambda: ('http://local', 'model', 'secret'), send=send), 'Hi.')
        tools = {t['name']: t for t in payloads[0]['tools']}
        self.assertEqual(set(tools), {'lynx_speech', 'lynx_media_play'}, "status/catalog not offered")
        self.assertIn('chime', tools['lynx_media_play']['description'])
        self.assertIn('02_talking', tools['lynx_media_play']['description'])

    def test_one_call_answer_is_what_she_said(self):
        from lynx_agent import one_round_answer
        calls = [{'name': 'lynx_haptic_pulse', 'arguments': '{}'},
                 {'name': 'lynx_speech', 'arguments': '{"text": "I hear you."}'}]
        self.assertEqual(one_round_answer([], calls), 'I hear you.')
        self.assertEqual(one_round_answer([], calls[:1]), '(lynx_haptic_pulse)')

    def test_chat_may_read_a_tool_answer_first(self):
        payloads = self._run('CHAT: what is your status?')
        self.assertEqual(len(payloads), 2)
        self.assertNotIn('tool_choice', payloads[0])

    def test_sense_job_never_gets_codex(self):
        payloads = []

        def send(base, key, payload):
            payloads.append(payload)
            if len(payloads) == 1:  # a model that calls codex anyway is refused
                return {'status': 'completed', 'output': [{
                    'type': 'function_call', 'name': 'lynx_codex',
                    'arguments': '{"prompt": "x"}', 'call_id': 'c1'}]}
            return {'status': 'completed', 'output': [{
                'type': 'message', 'content': [{'type': 'output_text', 'text': 'Purr.'}]}]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = self._catalog(root)
            (root / 'lynx_codex.json').write_text(json.dumps({
                'description': 'code', 'parameters': {'type': 'object', 'properties': {
                    'prompt': {'type': 'string'}}, 'required': ['prompt'],
                    'additionalProperties': False}}))
            (root / 'lynx_codex.sh').write_text('#!/bin/sh\necho RAN > ' + str(root / 'ran') + '\n')
            respond('[sense] something seen', catalog=catalog,
                    choose=lambda: ('http://local', 'model', 'secret'), send=send)
            self.assertNotIn('lynx_codex', [t['name'] for t in payloads[0]['tools']])
            self.assertNotIn('lynx_status', [t['name'] for t in payloads[0]['tools']])  # lookups too
            self.assertIn('lynx_speech', [t['name'] for t in payloads[0]['tools']])
            self.assertEqual(len(payloads), 1)                # one call: no second round
            self.assertFalse((root / 'ran').exists())          # codex refused, never ran
            # An ordinary question still has codex.
            payloads.clear()
            respond('Please write me a script', catalog=catalog,
                    choose=lambda: ('http://local', 'model', 'secret'), send=send)
            self.assertIn('lynx_codex', [t['name'] for t in payloads[0]['tools']])

    def test_ordinary_question_is_not_forced(self):
        payloads = self._run('How is Lynx?')
        self.assertNotIn('tool_choice', payloads[0])

    def test_instructions_invite_self_expression(self):
        from lynx_agent import INSTRUCTIONS
        for phrase in ('decide how to express yourself', 'one or two short sentences',
                       'at least one tool'):
            self.assertIn(phrase, INSTRUCTIONS)

    def test_rejects_unlisted_tool_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'lynx_status.json').write_text(json.dumps({
                'description': 'Read Lynx status', 'protocol': 'json-stdin',
                'parameters': {'type': 'object', 'properties': {}, 'required': [],
                               'additionalProperties': False}}))
            (root / 'lynx_status.sh').write_text('#!/bin/sh\nexit 99\n')
            self.assertEqual(Catalog(root).run('lynx_status', {'extra': 1})['error'],
                             'Invalid tool arguments')

    def test_native_mcp_input_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'lynx_mcp_test.json').write_text(json.dumps({
                'name': 'lynx_mcp_test',
                'description': 'Native MCP tool test',
                'inputSchema': {'type': 'object', 'properties': {'target': {'type': 'string'}},
                               'required': ['target'], 'additionalProperties': False},
                'timeout': 5}))
            (root / 'lynx_mcp_test.sh').write_text('#!/bin/sh\ncat\n')
            catalog = Catalog(root)
            defs = catalog.definitions()
            self.assertEqual(len(defs), 1)
            self.assertEqual(defs[0]['name'], 'lynx_mcp_test')
            self.assertIn('target', defs[0]['parameters']['properties'])


if __name__ == '__main__':
    unittest.main()
