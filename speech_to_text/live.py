#!/usr/bin/env python3
"""Concurrent, phrase-at-a-time ReSpeaker transcription. No recordings saved."""
import argparse
import collections
import pathlib
import queue
import json
import re
import statistics
import builtins
import os
import subprocess
import threading
import time

import numpy as np
from faster_whisper.vad import VadOptions, get_speech_timestamps
from decode_engine import Decoder
from nexus_client import remote_from_config
from transcription_scheduler import Scheduler


def speed_summary(measurements):
    if not measurements:
        return {'phrases': 0}
    audio = sum(row['audio_seconds'] for row in measurements)
    decode = sum(row['decode_seconds'] for row in measurements)
    voice = sum(row['voice_seconds'] for row in measurements)
    words = sum(row['words'] for row in measurements)
    delays = sorted(row['end_to_text_seconds'] for row in measurements)
    return {'phrases': len(measurements), 'words': words,
            'audio_seconds': audio, 'decode_seconds': decode,
            'realtime_factor': decode / audio,
            'words_per_voice_minute': words * 60 / voice if voice else None,
            'median_end_to_text_seconds': statistics.median(delays),
            'p95_end_to_text_seconds': delays[max(0, int(np.ceil(len(delays) * .95)) - 1)]}


def main(speed_test=False):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', default='base')
    parser.add_argument('--language', default='en', help='Fixed language code; default: en')
    parser.add_argument('--channel', type=int, choices=[0, 1], default=1)
    parser.add_argument('--device', default='hw:Array,0')
    parser.add_argument('--duration', type=int, default=60 if speed_test else 0, help='Capture seconds; 0 means until Ctrl+C')
    parser.add_argument('--prepare', action='store_true', help='Download/load model without opening microphone')
    parser.add_argument('--json-events', action='store_true', help='Emit newline-delimited JSON for service subscribers')
    parser.add_argument('--nexus-config', type=pathlib.Path,
        default=pathlib.Path.home() / '.config/noobia-speech/nexus.json',
        help='Private preferred Nexus worker configuration; absent means local decoding')
    parser.add_argument('--argus-config', type=pathlib.Path,
        default=pathlib.Path.home() / '.config/noobia-speech/argus.json',
        help='Optional private third worker configuration; absent disables Argus')
    parser.add_argument('--chunk-seconds', type=float, default=6, help='Maximum phrase length, rounded to half-second blocks')
    parser.add_argument('--pause-seconds', type=float, default=1, help='Silence before decoding, rounded to half-second blocks')
    if speed_test:
        parser.add_argument('--report', type=pathlib.Path, help='Save metrics and transcripts as JSON to this new file')
    args = parser.parse_args()
    def event(kind, **fields):
        builtins.print(json.dumps({'type': kind, 'timestamp': time.time(), **fields}, ensure_ascii=False), flush=True)

    def print(message='', **kwargs):
        if args.json_events:
            event('status', message=message)
        else:
            builtins.print(message, **kwargs)
    if args.duration < 0:
        parser.error('duration must be nonnegative')
    if not np.isfinite(args.chunk_seconds) or not .5 <= args.chunk_seconds <= 30:
        parser.error('chunk-seconds must be between 0.5 and 30')
    if not np.isfinite(args.pause_seconds) or not .5 <= args.pause_seconds <= 10:
        parser.error('pause-seconds must be between 0.5 and 10')
    if speed_test and args.report and args.report.exists():
        parser.error('report already exists; choose a new filename')
    max_blocks = int(np.ceil(args.chunk_seconds * 2))
    silence_blocks = int(np.ceil(args.pause_seconds * 2))
    measurements = []
    interrupted = False
    local = Decoder(args.model, args.language)
    if args.prepare:
        local.prepare()
        print('Model ready. Microphone was not opened.', flush=True)
        return
    remote = remote_from_config(args.nexus_config, args.model, args.language)
    argus = remote_from_config(args.argus_config, args.model, args.language)
    def route_status(worker, sequence):
        if args.json_events:
            event('status', phase='listening', message=f'Transcribing chunk {sequence + 1} on {worker}',
                  executor=worker, chunk_id=sequence)
        else:
            print(f'Transcribing chunk {sequence + 1} on {worker}', flush=True)
    model = Scheduler(local, remote, argus, on_dispatch=route_status)
    if remote is None:
        print(f'Loading {args.model} on CPU (int8)…', flush=True)
        local.prepare()
    else:
        print('Nexus-first transcription; local fallback ready on demand.', flush=True)
    vad_options = VadOptions(min_speech_duration_ms=100, min_silence_duration_ms=100)
    pending = queue.Queue(maxsize=8)
    stop = threading.Event()
    errors = []
    command = ['arecord', '-q', '-D', args.device, '-t', 'raw', '-f', 'S16_LE',
               '-r', '16000', '-c', '2']
    if args.duration:
        command += ['-d', str(args.duration)]
    recorder = subprocess.Popen(command, stdout=subprocess.PIPE)

    def capture():
        phrase = []
        preroll = collections.deque(maxlen=1)
        silence = 0
        last_voice = None
        continued = False

        def enqueue():
            pending.put_nowait((np.concatenate(phrase), time.monotonic(), last_voice))

        try:
            while not stop.is_set():
                raw = recorder.stdout.read(32000)  # half a second, stereo
                if not raw:
                    break
                audio = np.frombuffer(raw, dtype='<i2').reshape(-1, 2)[:, args.channel].astype(np.float32) / 32768
                speech = bool(get_speech_timestamps(audio, vad_options))
                if args.json_events:
                    event('audio', level=float(np.sqrt(np.mean(audio * audio))), speech=speech)
                if speech:
                    last_voice = time.monotonic()
                if speech and not phrase and not continued:
                    phrase.extend(preroll)
                if speech or phrase:
                    phrase.append(audio)
                    silence = 0 if speech else silence + 1
                    if silence >= silence_blocks or len(phrase) >= max_blocks:
                        continued = silence < silence_blocks
                        enqueue()
                        phrase = []
                        silence = 0
                elif not speech:
                    continued = False
                preroll.append(audio)
            if phrase and not stop.is_set():
                enqueue()
            if not stop.is_set() and recorder.wait() != 0:
                raise RuntimeError('Audio capture failed; check device availability.')
        except Exception as exc:
            errors.append(exc)
            stop.set()

    thread = threading.Thread(target=capture, daemon=True)
    print(f'LISTENING — channel {args.channel}; Ctrl+C stops. Audio stays in memory.', flush=True)
    if speed_test:
        print('Read a paragraph aloud, pause, and compare the transcript with what you said.\n'
              'RTF below 1 means decoding is faster than the incoming audio.\n'
              'End→text is approximate: measured from the last voice-positive half-second block.\n'
              'WPM uses recognized words and detected voice time, excluding pauses.', flush=True)
    def emit_transcript(job, decoded, finished):
        audio, captured, last_voice, started = job.audio, job.captured, job.last_voice, job.started
        released = time.monotonic()
        transcript = decoded['text']
        elapsed = finished - started
        if transcript:
            print(f'[{time.strftime("%H:%M:%S")}] {transcript}', flush=True)
            print(f'  ({decoded["language"]}; {len(audio)/16000:.1f}s audio, {elapsed:.2f}s decoding, '
                  f'{time.monotonic()-captured:.2f}s since phrase queued)', flush=True)
        if speed_test or args.json_events:
            voice = sum((span['end']-span['start'])/16000 for span in
                        get_speech_timestamps(audio, VadOptions(speech_pad_ms=0)))
            row = {'text': transcript, 'language': decoded['language'],
                   'executor': decoded['executor'], 'chunk_id': job.sequence,
                   'ordering_seconds': released - finished,
                   'worker_decode_seconds': decoded['worker_decode_seconds'],
                   'audio_seconds': len(audio)/16000, 'voice_seconds': voice,
                   'words': len(re.findall(r"\b\w+(?:['’]\w+)*\b", transcript)),
                   'decode_seconds': elapsed, 'queue_seconds': started-captured,
                   'end_to_text_seconds': released-(last_voice or captured)}
            measurements.append(row)
            if args.json_events:
                event('transcript', **row)
            rtf = elapsed/row['audio_seconds']
            wpm = f"{row['words']*60/voice:.0f}" if voice else 'n/a'
            print(f"  SPEED: RTF {rtf:.3f} ({1/rtf:.1f}× realtime); "
                  f"end→text ≈{row['end_to_text_seconds']:.2f}s; queue {row['queue_seconds']:.2f}s; "
                  f"speaking ≈{wpm} WPM", flush=True)
    thread.start()
    try:
        while thread.is_alive() or not pending.empty() or model.busy:
            if errors:
                raise RuntimeError(f'Capture stopped: {errors[0]}')
            ready = model.pump(pending)
            if not ready:
                time.sleep(.02)
                continue
            for job, decoded, finished in ready:
                emit_transcript(job, decoded, finished)
        if errors:
            raise RuntimeError(f'Capture stopped: {errors[0]}')
    except KeyboardInterrupt:
        interrupted = True
    finally:
        stop.set()
        if recorder.poll() is None:
            recorder.terminate()
        recorder.wait()
        thread.join(timeout=3)
        recorder.stdout.close()
        model.close()
        print('Microphone closed.', flush=True)
        if speed_test:
            summary = speed_summary(measurements)
            print('\nSESSION RESULTS', flush=True)
            if measurements:
                print(f"{summary['phrases']} phrases; {summary['words']} recognized words\n"
                      f"Decoding: {summary['decode_seconds']:.2f}s for {summary['audio_seconds']:.1f}s audio; "
                      f"RTF {summary['realtime_factor']:.3f}\n"
                      f"Approximate end→text: median {summary['median_end_to_text_seconds']:.2f}s; "
                      f"p95 {summary['p95_end_to_text_seconds']:.2f}s", flush=True)
            else:
                print('No speech phrases detected; no speed measurement available.', flush=True)
            if args.report:
                with args.report.open('x') as report:
                    json.dump({'model': args.model, 'channel': args.channel, 'language': args.language,
                               'summary': summary, 'phrases': measurements,
                               'complete': not errors and not interrupted}, report, indent=2, ensure_ascii=False)
                    report.write('\n')
                print(f'Report saved to {args.report}', flush=True)


if __name__ == '__main__':
    main()
