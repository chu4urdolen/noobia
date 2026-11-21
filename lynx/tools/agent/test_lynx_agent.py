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

    def test_sense_job_must_start_with_a_tool(self):
        payloads = self._run('[sense] This is something your senses perceived ... cat')
        self.assertEqual(payloads[0].get('tool_choice'), 'required')
        self.assertNotIn('tool_choice', payloads[1])     # only the first step is forced

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
