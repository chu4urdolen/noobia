import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import banshee_helper_mirror as mirror


SESSION = '11111111-1111-1111-1111-111111111111'


class BansheeMirrorTests(unittest.TestCase):
    def test_only_new_conversations_reuse_a_persistent_helper_thread(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            conversations = root / 'conversations'
            conversations.mkdir()
            old = conversations / ('22222222-2222-2222-2222-222222222222.db')
            old.touch()
            calls = []
            def turn(prompt, previous):
                calls.append((prompt, previous))
                return '33333333-3333-3333-3333-333333333333', []
            turns = [{'index': 0, 'role': 'noob', 'text': 'hello'}]
            with patch.object(mirror, 'CONVERSATIONS', conversations), \
                 patch.object(mirror, 'ROOT', root / 'mirror'), \
                 patch.object(mirror, 'ACTIVATION', root / 'mirror' / 'activation.json'), \
                 patch.object(mirror, 'visible_turns', side_effect=lambda _: list(turns)), \
                 patch.object(mirror.shared, 'run_turn', side_effect=turn):
                mirror.activate()
                self.assertFalse(mirror.eligible(old.stem))
                fresh = conversations / (SESSION + '.db')
                fresh.touch()
                self.assertTrue(mirror.eligible(SESSION))
                first = mirror.sync(SESSION)
                self.assertEqual(first['sent'], 1)
                turns.append({'index': 1, 'role': 'banshee', 'text': 'hi'})
                second = mirror.sync(SESSION)
                self.assertEqual(second['sent'], 2)
                self.assertEqual(len(mirror.records(SESSION)), 2)
            self.assertEqual(calls[0][1], None)
            self.assertEqual(calls[1][1], '33333333-3333-3333-3333-333333333333')
            self.assertIn('hello', calls[0][0])
            self.assertIn('hi', calls[1][0])

    def test_ask_includes_cumulative_conversation_summary(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            conversations = root / 'conversations'
            conversations.mkdir()
            calls = []
            def turn(prompt, previous):
                calls.append((prompt, previous))
                return '33333333-3333-3333-3333-333333333333', [
                    {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'Yes, I see the summary.'}}
                ]
            turns = [{'index': 0, 'role': 'noob', 'text': 'hello'}]
            with patch.object(mirror, 'CONVERSATIONS', conversations), \
                 patch.object(mirror, 'ROOT', root / 'mirror'), \
                 patch.object(mirror, 'ACTIVATION', root / 'mirror' / 'activation.json'), \
                 patch.object(mirror, 'visible_turns', side_effect=lambda _: list(turns)), \
                 patch.object(mirror.shared, 'run_turn', side_effect=turn), \
                 patch.object(mirror.dushich_summarizer, 'incremental_summarize', return_value='Compacted summary text.'):
                mirror.activate()
                fresh = conversations / (SESSION + '.db')
                fresh.touch()
                answer = mirror.ask(SESSION, 'Can you see the summary?')
            self.assertEqual(answer, 'Yes, I see the summary.')
            self.assertIn('Cumulative conversation summary', calls[-1][0])
            self.assertIn('Compacted summary text.', calls[-1][0])


if __name__ == '__main__':
    unittest.main()
