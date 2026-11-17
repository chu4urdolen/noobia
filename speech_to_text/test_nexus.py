import base64
import unittest
from unittest.mock import Mock, patch
import json
import zlib
from nexus_client import Router, Remote
from nexus_worker import decode_request


class RoutingTests(unittest.TestCase):
    def test_prefers_nexus_then_falls_back_then_returns_without_duplicate_decode(self):
        local = Mock()
        local.decode.side_effect = lambda audio: {'text': 'local', 'language': 'en'}
        remote = Mock()
        remote.decode.side_effect = [{'text': 'remote', 'executor': 'Nexus'},
                                     ConnectionError('offline'),
                                     {'text': 'back', 'executor': 'Nexus'}]
        now = [0]
        router = Router(local, remote, clock=lambda: now[0])
        self.assertEqual(router.decode(None)['text'], 'remote')
        local.decode.assert_not_called()
        self.assertEqual(router.decode(None)['executor'], 'Syra')
        remote.close.assert_called_once()
        now[0] = 5
        self.assertEqual(router.decode(None)['text'], 'local')
        self.assertEqual(remote.decode.call_count, 2)
        now[0] = 11
        self.assertEqual(router.decode(None)['executor'], 'Nexus')
        self.assertEqual(local.decode.call_count, 2)

    def test_worker_rejects_invalid_or_oversized_pcm_without_decoding(self):
        decoder = Mock()
        for raw in [b'', b'x', b'\0' * (960000 + 2)]:
            with self.assertRaises(ValueError):
                decode_request({'type': 'transcribe', 'pcm': base64.b64encode(raw).decode()}, decoder)
        decoder.decode.assert_not_called()

    def test_worker_uses_pcm_in_memory(self):
        decoder = Mock()
        decoder.decode.return_value = {'text': 'hello', 'language': 'en'}
        result = decode_request({'type': 'transcribe', 'pcm': base64.b64encode(b'\0\0' * 16000).decode()}, decoder)
        self.assertEqual(result['text'], 'hello')
        self.assertEqual(len(decoder.decode.call_args.args[0]), 16000)

    def test_remote_sends_complete_request_after_partial_pipe_writes(self):
        remote = Remote({}, 'base', 'en')
        remote.process = Mock()
        sent = bytearray()
        def write(data):
            sent.extend(data[:3])
            return min(3, len(data))
        remote.process.stdin.write.side_effect = write
        with patch('nexus_client.select.select', return_value=([remote.process.stdout], [], [])), \
             patch('nexus_client.os.read', return_value=b'{"ok":true}\n'):
            remote.exchange({'type': 'hello'})
        self.assertEqual(json.loads(sent), {'type': 'hello'})

    def test_compressed_audio_and_decompression_limit(self):
        decoder = Mock()
        decoder.decode.return_value = {'text': 'hello', 'language': 'en'}
        pcm = b'\0\0' * 16000
        result = decode_request({'type': 'transcribe', 'pcm_zlib':
            base64.b64encode(zlib.compress(pcm)).decode()}, decoder)
        self.assertEqual(result['text'], 'hello')
        with self.assertRaises(ValueError):
            decode_request({'type': 'transcribe', 'pcm_zlib':
                base64.b64encode(zlib.compress(b'\0' * 1000000)).decode()}, decoder)


if __name__ == '__main__':
    unittest.main()
