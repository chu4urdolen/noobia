import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from media_server import Media


class MediaTests(unittest.TestCase):
    def test_play_replaces_video_and_enables_autoplay(self):
        with tempfile.TemporaryDirectory() as folder, patch('media_server.STATE', Path(folder) / 'state.json'), \
             patch.object(Media, 'notify'), patch('media_server.subprocess.Popen') as spawn:
            media = Media()
            result = media.control({'action': 'play', 'video_id': 'M7lc1UVf-VE', 'start_seconds': 0, 'muted': True})
            self.assertNotIn('queued', result)
            self.assertEqual(media.state['playback_state'], 'starting')
            self.assertFalse(media.state['paused'])
            self.assertEqual(media.state['volume'], 50)
            generation = media.state['generation']
            self.assertTrue(media.control({'action': 'pause'})['ok'])
            self.assertTrue(media.state['paused'])
            self.assertTrue(media.control({'action': 'resume'})['ok'])
            self.assertFalse(media.state['paused'])
            self.assertTrue(media.control({'action': 'volume', 'volume': 35})['ok'])
            self.assertEqual(media.state['volume'], 35)
            self.assertEqual(media.state['generation'], generation)
            self.assertTrue(media.control({'action': 'seek', 'seconds': 60})['ok'])
            self.assertEqual(media.state['seek_seconds'], 60)
            spawn.assert_not_called()
            self.assertEqual(media.control({'action': 'stop'})['mode'], 'idle')
            self.assertFalse(media.control({'action': 'play', 'video_id': 'javascript:evil'})['ok'])

    def test_public_search_missing_key_does_not_call_network(self):
        from youtube_api import search
        with patch('youtube_api.settings', return_value={}), patch('youtube_api.urllib.request.urlopen') as request:
            self.assertFalse(search('ambient music')['ok'])
            request.assert_not_called()

    def test_play_success_requires_requested_video_actually_playing(self):
        with tempfile.TemporaryDirectory() as folder, patch('media_server.STATE', Path(folder) / 'state.json'), \
             patch.object(Media, 'notify'):
            media = Media()
            result = media.control({'action': 'play', 'video_id': '0t_I5IdYGBg'})
            media.state.update(playback_state=1, reported_video_id='M7lc1UVf-VE')
            self.assertFalse(media.wait_for_playback(result['generation'], timeout=0)['ok'])
            media.state['reported_video_id'] = '0t_I5IdYGBg'
            self.assertTrue(media.wait_for_playback(result['generation'], timeout=0)['playing'])
            media.control({'action': 'stop'})
            self.assertFalse(media.wait_for_playback(result['generation'], timeout=0)['ok'])

    def test_frozen_renderer_recovers_but_loading_and_paused_player_do_not(self):
        with tempfile.TemporaryDirectory() as folder, patch('media_server.STATE', Path(folder) / 'state.json'), \
             patch.object(Media, 'notify'), patch.object(Media, 'close_browser') as close:
            media = Media()
            media.control({'action': 'play', 'video_id': '0t_I5IdYGBg'})
            media.browser = object()
            media.player_deadline = 160
            media.last_player_heartbeat = 100
            self.assertFalse(media.recover_stale_player(150))
            media.state.update(position=42, paused=True)
            media.last_player_heartbeat = 165
            self.assertFalse(media.recover_stale_player(170))
            self.assertTrue(media.recover_stale_player(200))
            close.assert_called_once()
            self.assertEqual(media.state['start_seconds'], 42)
            self.assertTrue(media.state['paused'])
            self.assertEqual(media.state['browser_recoveries'], 1)
