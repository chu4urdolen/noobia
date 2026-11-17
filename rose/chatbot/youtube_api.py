"""Official YouTube Data API search; credentials never appear in returned results."""
import html
import json
import urllib.error
import urllib.parse
import urllib.request
from core import settings


def search(query, limit=5):
    key = settings().get('youtube_api_key')
    if not key:
        return {'ok': False, 'error': 'Set a YouTube Data API key in Rose Settings. Browser sign-in is separate from the search API key.'}
    parameters = urllib.parse.urlencode(dict(part='snippet', type='video',
        videoEmbeddable='true', q=query, maxResults=limit, key=key))
    request = urllib.request.Request('https://www.googleapis.com/youtube/v3/search?' + parameters)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            value = json.load(response)
    except urllib.error.HTTPError as error:
        return {'ok': False, 'error': 'YouTube search API returned HTTP ' + str(error.code) + '; check API enablement, key restrictions and quota.'}
    except (OSError, ValueError):
        return {'ok': False, 'error': 'YouTube search is temporarily unavailable'}
    return {'ok': True, 'results': [dict(video_id=item['id']['videoId'],
        title=html.unescape(item['snippet']['title']), channel=item['snippet']['channelTitle'],
        url='https://www.youtube.com/watch?v=' + item['id']['videoId'])
        for item in value.get('items', []) if item.get('id', {}).get('videoId')]}
