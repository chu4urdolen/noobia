import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import helper_mirror as mirror


SESSION = '11111111-1111-1111-1111-111111111111'


class MirrorTests(unittest.TestCase):
    def test_only_conversations_created_after_activation_are_eligible(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old = root / f'rollout-{SESSION}.jsonl'
            old.write_text(json.dumps({'type': 'session_meta', 'payload': {
                'timestamp': '2026-11-14T00:00:00Z'}}) + '\n')
            with patch.object(mirror, 'SESSIONS', root), patch.object(mirror, 'ROOT', root / 'mirror'), \
                 patch.object(mirror, 'ACTIVATION', root / 'mirror' / 'activation.json'), \
                 patch.object(mirror.time, 'time', return_value=1794700800.0):
                mirror.activate()
                self.assertFalse(mirror.eligible(SESSION))
                old.write_text(json.dumps({'type': 'session_meta', 'payload': {
                    'timestamp': '2026-11-16T00:00:00Z'}}) + '\n')
                self.assertTrue(mirror.eligible(SESSION))

    def test_visible_events_are_archived_once_and_reuse_one_helper_thread(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / f'rollout-{SESSION}.jsonl'
            def append(ordinal, kind, **payload):
                with source.open('a') as stream:
                    stream.write(json.dumps({'type': 'response_item', 'ordinal': ordinal,
                                             'timestamp': '2026-11-15T00:00:00Z',
                                             'payload': {'type': kind, **payload}}) + '\n')
            append(1, 'message', role='user', content=[{'type': 'input_text', 'text': 'hello'}])
            append(2, 'reasoning', summary='private')
            calls = []
            def turn(prompt, previous):
                calls.append((prompt, previous))
                return '22222222-2222-2222-2222-222222222222', []
            with patch.object(mirror, 'SESSIONS', root), patch.object(mirror, 'ROOT', root / 'mirror'), \
                 patch.object(mirror, 'run_turn', side_effect=turn):
                first = mirror.sync(SESSION)
                self.assertEqual(first['sent'], 1)
                self.assertEqual(len(mirror.records(SESSION)), 1)
                mirror.sync(SESSION)
                self.assertEqual(len(calls), 1)
                append(3, 'message', role='assistant', phase='final_answer',
                       content=[{'type': 'output_text', 'text': 'hi'}])
                second = mirror.sync(SESSION)
                self.assertEqual(second['sent'], 2)
                self.assertEqual(len(mirror.records(SESSION)), 2)
            self.assertEqual(calls[0][1], None)
            self.assertEqual(calls[1][1], '22222222-2222-2222-2222-222222222222')
            self.assertIn('hello', calls[0][0])
            self.assertIn('hi', calls[1][0])
            self.assertNotIn('private', ''.join(prompt for prompt, _ in calls))

    def test_large_tool_result_is_sent_in_order_across_turns(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / f'rollout-{SESSION}.jsonl'
            source.write_text(json.dumps({'type': 'response_item', 'ordinal': 1,
                'timestamp': '2026-11-15T00:00:00Z', 'payload': {
                'type': 'custom_tool_call_output', 'output': '~' * 22_000}}) + '\n')
            prompts = []
            def turn(prompt, previous):
                prompts.append(prompt)
                return '22222222-2222-2222-2222-222222222222', []
            with patch.object(mirror, 'SESSIONS', root), patch.object(mirror, 'ROOT', root / 'mirror'), \
                 patch.object(mirror, 'run_turn', side_effect=turn), \
                 patch.object(mirror, 'MAX_BATCH', 15_000):
                result = mirror.sync(SESSION, max_batches=5)
            self.assertEqual(result['sent'], 1)
            self.assertEqual(result['sent_chars'], 0)
            self.assertEqual(sum(p.count('~') for p in prompts), 22_000)


if __name__ == '__main__':
    unittest.main()
