"""Shared lazy English Whisper decoder; audio and transcripts stay in memory."""
import os
from pathlib import Path
import time


class Decoder:
    def __init__(self, model='base', language='en', threads=6):
        self.model_name, self.language, self.threads = model, language, threads
        self.model = None

    def prepare(self):
        if self.model is None:
            from faster_whisper import WhisperModel
            self.model = WhisperModel(self.model_name, device='cpu', compute_type='int8',
                cpu_threads=min(self.threads, os.cpu_count() or 2),
                download_root=str(Path(__file__).parent / 'models'))

    def decode(self, audio):
        self.prepare()
        started = time.monotonic()
        segments, info = self.model.transcribe(audio, language=self.language, beam_size=1,
            vad_filter=True, condition_on_previous_text=False)
        text = ' '.join(segment.text.strip() for segment in segments).strip()
        return {'text': text, 'language': info.language,
                'worker_decode_seconds': time.monotonic() - started}
