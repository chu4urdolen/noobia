"""The New conversation choice starts a fresh agent terminal."""

from subprocess import CompletedProcess
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import plugins


ARIA_ID = '11111111-1111-1111-1111-111111111111'
BANSHEE_ID = '22222222-2222-2222-2222-222222222222'


class NewConversationTests(unittest.TestCase):
    def test_handoff_feed_shows_task_and_visible_dushich_messages_only(self):
        with tempfile.TemporaryDirectory() as directory:
            job = Path(directory) / 'handoff-1'
            job.mkdir()
            (job / 'state.json').write_text(json.dumps({
                'aria_session_id': ARIA_ID, 'status': 'done',
                'created': '2026-11-14T13:00:00Z', 'finished': '2026-11-14T13:01:00Z'}))
            (job / 'brief.txt').write_text('Current Dushich task:\nRead the sample.\n\nPrivate context attached.')
            (job / 'public-dialogue.json').write_text(json.dumps([
                {'text': 'I found the issue.', 'time': 1794661220},
                {'text': 'Fixed and verified.', 'time': 1794661240}]))
            (job / 'result.txt').write_text('PRIVATE TRACE MUST NOT APPEAR')
            events = plugins._job_results(Path(directory), 'aria_session_id', ARIA_ID)
        self.assertEqual([(e['role'], e['text']) for e in events], [
            ('aria', 'To Dushich: Read the sample.'),
            ('dushich', 'I found the issue.'),
            ('dushich', 'Fixed and verified.')])
        self.assertTrue(events[-1]['final'])

    def test_aria_starts_new_two_pane_session(self):
        output = f'Two-pane session ready: noobia-aria-{ARIA_ID}\n'
        with patch.object(plugins.subprocess, 'run', return_value=CompletedProcess([], 0, output, '')) as run, \
             patch.object(plugins, '_aria_pane', return_value='%11'), \
             patch.object(plugins, '_send_tmux') as send:
            session = plugins.AriaPlugin().send('new', 'hello')
        self.assertEqual(session, 'noobia-aria-' + ARIA_ID)
        self.assertEqual(run.call_args.args[0], ['/noobia/aria/codex-with-dushich', '--detached'])
        send.assert_called_once_with('%11', 'hello')

    def test_existing_aria_conversation_sends_to_live_pane(self):
        with patch.object(plugins.AriaPlugin, '_paths', return_value={ARIA_ID: Path('/tmp/rollout.jsonl')}), \
             patch.object(plugins, '_aria_pane', return_value='%11'), \
             patch.object(plugins, '_aria_pane_conversation', return_value=ARIA_ID), \
             patch.object(plugins.subprocess, 'run') as run, \
             patch.object(plugins, '_send_tmux') as send:
            result = plugins.AriaPlugin().send(ARIA_ID, 'hello')
        self.assertEqual(result, 'noobia-aria-' + ARIA_ID)
        run.assert_not_called()
        send.assert_called_once_with('%11', 'hello')

    def test_existing_aria_conversation_reopens_closed_pane(self):
        output = f'Two-pane session ready: noobia-aria-{ARIA_ID}\n'
        with patch.object(plugins.AriaPlugin, '_paths', return_value={ARIA_ID: Path('/tmp/rollout.jsonl')}), \
             patch.object(plugins, '_aria_pane', return_value=None), \
             patch.object(plugins, '_tmux_sessions', return_value=[]), \
             patch.object(plugins, '_aria_pane_conversation', return_value=ARIA_ID), \
             patch.object(plugins.subprocess, 'run', return_value=CompletedProcess([], 0, output, '')) as run, \
             patch.object(plugins, '_wait_for_aria', return_value='%11'), \
             patch.object(plugins, '_send_tmux') as send:
            result = plugins.AriaPlugin().send(ARIA_ID, 'hello')
        self.assertEqual(result, 'noobia-aria-' + ARIA_ID)
        self.assertEqual(run.call_args.args[0],
                         ['/noobia/aria/codex-with-dushich', '--detached', '--resume', ARIA_ID])
        send.assert_called_once_with('%11', 'hello')

    def test_aria_reports_fork_that_received_message(self):
        child = '33333333-3333-3333-3333-333333333333'
        with patch.object(plugins.AriaPlugin, '_paths', return_value={ARIA_ID: Path('/tmp/rollout.jsonl')}), \
             patch.object(plugins, '_aria_pane', return_value='%11'), \
             patch.object(plugins, '_aria_pane_conversation', return_value=child), \
             patch.object(plugins, '_send_tmux') as send:
            result = plugins.AriaPlugin().send(ARIA_ID, 'hello')
        self.assertEqual(result, 'noobia-aria-' + child)
        send.assert_called_once_with('%11', 'hello')

    def test_aria_lists_live_conversation_before_transcript_exists(self):
        session = 'noobia-aria-' + ARIA_ID
        with patch.object(plugins.AriaPlugin, '_paths', return_value={}), \
             patch.object(plugins, '_tmux_sessions', return_value=[session]), \
             patch.object(plugins, '_aria_pane', return_value='%11'), \
             patch.object(plugins, '_aria_pane_conversation', return_value=ARIA_ID), \
             patch.object(plugins, '_queued_codex_inputs', return_value=[]):
            agent = plugins.AriaPlugin()
            self.assertEqual(agent.conversations(), [
                {'id': ARIA_ID, 'label': 'New Codex conversation', 'active': True}])
            self.assertEqual(agent.timeline(ARIA_ID), [])

    def test_queued_aria_message_is_visible_before_turn_starts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'queue.sqlite'
            db = sqlite3.connect(path)
            db.execute('CREATE TABLE queued_items(id text, thread_id text, payload_json text, '
                       'queue_order integer, created_at_ms integer)')
            payload = {'UserInput': {'content': [{'type': 'text', 'text': 'Hello from the page'}]}}
            db.execute('INSERT INTO queued_items VALUES (?, ?, ?, ?, ?)',
                       ('message-id', ARIA_ID, json.dumps(payload), 1, 1794660000000))
            db.commit()
            db.close()
            with patch.object(plugins, 'CODEX_QUEUE', path):
                events = plugins._queued_codex_inputs(ARIA_ID)
        self.assertEqual([(event['role'], event['text'], event['queued']) for event in events],
                         [('noob', 'Hello from the page', True)])

    def test_banshee_starts_new_two_pane_session(self):
        output = 'Two-pane session ready: noobia-banshee-22222222\n'
        with patch.object(plugins.subprocess, 'run', return_value=CompletedProcess([], 0, output, '')) as run, \
             patch.object(plugins, '_wait_for_banshee') as ready, \
             patch.object(plugins, '_banshee_pane_alive', return_value=True), \
             patch.object(plugins, '_send_tmux') as send:
            session = plugins.BansheePlugin().send('new', 'hello')
        self.assertEqual(session, 'noobia-banshee-22222222')
        self.assertEqual(run.call_args.args[0], ['/noobia/banshee/launch', '--detached'])
        ready.assert_called_once_with(session)
        send.assert_called_once_with(session, 'hello')

    def test_solo_dushich_starts_local_codex(self):
        ident = '33333333-3333-3333-3333-333333333333'
        output = f'Solo Dushich session ready: noobia-dushich-solo-{ident}\n'
        with patch.object(plugins.subprocess, 'run', return_value=CompletedProcess([], 0, output, '')) as run, \
             patch.object(plugins, '_wait_for_codex') as ready, \
             patch.object(plugins, '_tmux_sessions', return_value=['noobia-dushich-solo-' + ident]), \
             patch.object(plugins.DushichSoloPlugin, 'timeline', return_value=[
                 {'role': 'noob', 'text': 'hello'}]), \
             patch.object(plugins, '_send_tmux') as send:
            session = plugins.DushichSoloPlugin().send('new', 'hello')
        self.assertEqual(session, 'noobia-dushich-solo-' + ident)
        self.assertEqual(run.call_args.args[0], ['/noobia/dushich/solo/launch', '--detached'])
        ready.assert_called_once_with(session)
        send.assert_called_once_with(session, 'hello')

    def test_solo_timeline_keeps_visible_messages_only(self):
        ident = '33333333-3333-3333-3333-333333333333'
        records = [
            {'type': 'response_item', 'timestamp': '2026-11-14T13:00:00Z',
             'payload': {'type': 'message', 'role': 'user',
                         'content': [{'type': 'input_text', 'text': 'Hello'}]}},
            {'type': 'response_item', 'timestamp': '2026-11-14T13:00:01Z',
             'payload': {'type': 'reasoning', 'role': 'assistant',
                         'content': [{'type': 'output_text', 'text': 'Private thought'}]}},
            {'type': 'response_item', 'timestamp': '2026-11-14T13:00:02Z',
             'payload': {'type': 'message', 'role': 'assistant',
                         'content': [{'type': 'output_text', 'text': 'Hi'}]}},
        ]
        output = '\n'.join(json.dumps(x) for x in records)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.jsonl'
            path.write_text(output, encoding='utf-8')
            with patch.object(plugins.DushichSoloPlugin, '_registered', return_value=[ident]), \
                 patch.object(plugins.DushichSoloPlugin, '_paths', return_value={ident: path}):
                events = plugins.DushichSoloPlugin().timeline(ident)
        self.assertEqual([(x['role'], x['text']) for x in events],
                         [('noob', 'Hello'), ('dushich', 'Hi')])



    def test_aria_tokens_weekly_and_hourly_from_rollout(self):
        agent = plugins.AriaPlugin()
        self.assertTrue(agent.has_tokens)
        with tempfile.TemporaryDirectory() as directory:
            rollout = Path(directory) / 'rollout.jsonl'
            data = [
                {'type': 'event_msg', 'payload': {
                    'type': 'token_count',
                    'rate_limits': {
                        'primary': {'used_percent': 12.0, 'window_minutes': 300, 'resets_at': 1794700000},
                        'secondary': {'used_percent': 49.0, 'window_minutes': 10080, 'resets_at': 1795200000},
                    }
                }}
            ]
            rollout.write_text('\n'.join(json.dumps(x) for x in data), encoding='utf-8')
            with patch.object(plugins.AriaPlugin, '_paths', return_value={ARIA_ID: rollout}):
                res = agent.tokens(ARIA_ID)
                new_res = agent.tokens('new')
            self.assertEqual(res['weekly_remaining_percent'], 51.0)
            self.assertEqual(res['hourly_remaining_percent'], 88.0)
            self.assertEqual(res['percent_remaining'], 51.0)
            self.assertEqual(new_res['weekly_remaining_percent'], 51.0)
            self.assertEqual(new_res['hourly_remaining_percent'], 88.0)

    def test_banshee_tokens_weekly_and_hourly_quota(self):
        agent = plugins.BansheePlugin()
        self.assertTrue(agent.has_tokens)
        fake_quota = {
            'weekly_remaining_percent': 97.45,
            'hourly_remaining_percent': 100.0,
            'percent_remaining': 97.45,
            'weekly_resets_at': '2026-11-22T19:19:40Z',
            'hourly_resets_at': '2026-11-16T00:19:40Z',
        }
        with tempfile.TemporaryDirectory() as directory:
            brain_dir = Path(directory) / BANSHEE_ID / '.system_generated' / 'logs'
            brain_dir.mkdir(parents=True)
            (brain_dir / 'transcript.jsonl').write_text('{}\n', encoding='utf-8')
            with patch.object(plugins, 'BANSHEE_BRAIN', Path(directory)), \
                 patch.object(plugins.BansheePlugin, '_paths', return_value={}), \
                 patch.object(plugins.BansheePlugin, '_live', return_value={}), \
                 patch.object(plugins, '_banshee_quota', return_value=fake_quota):
                res = agent.tokens(BANSHEE_ID)
                new_res = agent.tokens('new')
                unknown = agent.tokens('99999999-9999-9999-9999-999999999999')
            self.assertEqual(res['weekly_remaining_percent'], 97.45)
            self.assertEqual(res['hourly_remaining_percent'], 100.0)
            self.assertEqual(res['percent_remaining'], 97.45)
            self.assertEqual(new_res['weekly_remaining_percent'], 97.45)
            self.assertIsNone(unknown)

    def test_banshee_usage_reads_group_limits_without_oauth_file(self):
        output = ('Gemini Models\tWeekly Limit Remaining\t97%\t2026-11-22T19:19:40Z\n'
                  'Gemini Models\tFive Hour Limit Remaining\t100%\t2026-11-17T20:07:53Z\n'
                  'Gemini 4 Argon\tGemini 4 Argon Weekly Limit\t58%\t2026-11-22T19:11:19Z\n')
        result = plugins._parse_banshee_usage(output)
        self.assertEqual(result['weekly_remaining_percent'], 97.0)
        self.assertEqual(result['hourly_remaining_percent'], 100.0)
        self.assertEqual(result['percent_remaining'], 97.0)
        self.assertEqual(result['weekly_resets_at'], '2026-11-22T19:19:40Z')

    def test_solo_dushich_has_no_tokens(self):
        agent = plugins.DushichSoloPlugin()
        self.assertFalse(agent.has_tokens)
        self.assertIsNone(agent.tokens('new'))
        self.assertIsNone(agent.tokens('33333333-3333-3333-3333-333333333333'))


if __name__ == '__main__':
    unittest.main()
