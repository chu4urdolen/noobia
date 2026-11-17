"""Bounded result paging for the Nexus-facing Lynx agent client."""

import base64
import json
import unittest
from unittest.mock import patch

import lynx_agent_remote as client


class RemoteResultTest(unittest.TestCase):
    def test_queue_health_decodes_aggregate_only(self):
        payload = {'counts': {'pending': 0, 'running': 0, 'done': 7},
                   'oldest_pending_seconds': None, 'issues': [], 'stopped': False}
        encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
        with patch.object(client, 'call', return_value=(1, {
                'tool': 'LYNX_QUEUE_HEALTH', 'data': encoded})):
            self.assertEqual(client.health(), payload)

    def test_queue_health_rejects_unexpected_fields(self):
        payload = {'counts': {'pending': 0, 'running': 0, 'done': 0},
                   'oldest_pending_seconds': None, 'issues': [], 'stopped': False,
                   'prompt': 'must not leave phone'}
        encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
        with patch.object(client, 'call', return_value=(1, {
                'tool': 'LYNX_QUEUE_HEALTH', 'data': encoded})):
            with self.assertRaisesRegex(RuntimeError, 'incomplete queue health'):
                client.health()

    def test_paged_utf8_result(self):
        calls = []
        pages = [
            (9, {'data': 'THlu', 'more': '1', 'ok': '1'}),
            (9, {'data': 'eCDwn4y5', 'more': '0', 'ok': '1'}),
        ]

        def fake_call(*words):
            calls.append(words)
            return pages.pop(0)

        with patch.object(client, 'call', side_effect=fake_call):
            self.assertEqual(client.result('a' * 32)['text'], 'Lynx 🌹')
        self.assertEqual([call[2] for call in calls], ['0', '3'])

    def test_rejects_inconsistent_length(self):
        pages = [(3, {'data': 'YQ', 'more': '1', 'ok': '1'}),
                 (4, {'data': 'Yg', 'more': '0', 'ok': '1'})]
        with patch.object(client, 'call', side_effect=pages):
            with self.assertRaisesRegex(RuntimeError, 'inconsistent result length'):
                client.result('a' * 32)

    def test_rejects_invalid_page_encoding(self):
        with patch.object(client, 'call', return_value=(2, {'data': '!*', 'more': '0', 'ok': '1'})):
            with self.assertRaisesRegex(RuntimeError, 'invalid result page encoding'):
                client.result('a' * 32)


if __name__ == '__main__':
    unittest.main()
