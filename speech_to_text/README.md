# ReSpeaker transcription in Noobia

## Nexus first, Syra fallback

Rose captures stereo ReSpeaker audio on Syra, selects channel 1 and performs
local voice activity detection. Capture continues while completed phrases are
decoded. English `base` Whisper decoding prefers a free Nexus worker, then a free
Syra worker, then optional Argus. At most one chunk runs per worker: two active
jobs with Nexus/Syra, or three when Argus is installed and enabled. Queued chunks
have no assigned worker until their dispatch turn. Results that finish early are
held and released in capture order, preserving the `love` trigger. The resulting
text returns to the existing private speech socket and
Rose's normal microphone input path. Phrase order and the `love` trigger are
unchanged. No transcription cloud API is used.

Nexus runs `noobia-transcription-worker.service`, keeping the CPU int8 model warm
between requests. Its Unix socket is `/run/user/1000/noobia-transcribe.sock`, mode
0600. Syra uses a persistent encrypted SSH connection with a dedicated key,
pinned Nexus host key and forced transcription-only command. The key cannot
open a shell, allocate a terminal, or forward ports. The bridge forwards bytes
only to the private worker socket. There is no public transcription TCP server.

Syra's private settings live in `~/.config/noobia-speech/nexus.json`: `target`,
`identity` and `known_hosts` point to the worker account and dedicated local key
files. Without this file, standalone capture remains local. The `--nexus-config`
option can select another private configuration. Neither SSH credentials nor
settings belong in Git. For another installation, install the worker unit on
Nexus, authorize a dedicated public key with the exact options
`restrict,command="/usr/bin/python3 /noobia/speech_to_text/worker_bridge.py"`, and
pin Nexus's actual SSH host public key in the configured known-hosts file.

Audio transfers as losslessly compressed 16 kHz mono int16 PCM. Requests are
bounded to 30 seconds, and decompression has an enforced size limit. Audio and
transcripts remain in memory. Failed transfers retry the same phrase locally;
the local model loads on its first job and remains warm thereafter. After a
failure, Nexus is retried on a subsequent phrase following a 10-second cooldown.
Connection handshakes time out after two seconds and response reads after eight
seconds; failed links can add latency before fallback. A failed remote chunk
waits for the single Syra slot, so fallback never adds a concurrent local decode
or exceeds the worker limit. No phrase is emitted twice. Capture and decoding
run concurrently with a bounded eight-phrase queue; held results are bounded too.

Argus is currently offline, so its slot is disabled. When it is online, run
`python3 /noobia/speech_to_text/setup_argus_worker.py` on Nexus. This uses the
existing verified Argus SSH alias, installs the worker in Argus's user account,
creates a dedicated transcription-only Syra key and pins Argus's actual host
key, then writes Syra's private `argus.json` and restarts capture. It requires
Argus's account to be able to write `/noobia/speech_to_text` and create a Python
venv. No broad shell key is granted to Rose. Missing `argus.json` disables Argus.

The connected ReSpeaker advertises only 16 kHz, 16-bit stereo PCM capture.
There is no compressed hardware capture endpoint. No software speech codec was
added to Syra. Only the selected mono channel is transmitted, using the existing
lossless compression; raw mono PCM is 32 kB/s before protocol overhead.

Transcript events include `executor` and `worker_decode_seconds` in addition to
the previous metrics. `decode_seconds` includes transport and any fallback;
`worker_decode_seconds` measures inference only. `chunk_id` records capture
order and `ordering_seconds` records waiting for earlier results. End-to-text
includes that waiting. The speed GUI identifies the
worker. Fixed English, subscriber recovery, microphone controls and local
capture supervision are preserved.

Verified on 2026-10-07: routing and transport tests, real remote transcription,
same-phrase local fallback, and return to Nexus. The public Whisper JFK reference
was used instead of saving microphone recordings. Warm six-second excerpts took
1.49–2.23 seconds end to end with about 0.42 seconds of Nexus decoding. Larger
recordings were slowed by WiFi transfer; this is a measurement, not a guaranteed
latency for other speech or network conditions. Nexus currently uses CPU, not GPU.

```sh
# Nexus worker
systemctl --user status noobia-transcription-worker.service
# Syra microphone service
systemctl --user status noobia-speech.service
# Routing, protocol and capture-recovery checks
.venv/bin/python -m unittest test_scheduler.py test_nexus.py test_capture_supervisor.py
```

The older initial setup notes below describe the original local-only session.

## Desktop GUI

```sh
/noobia/speech_to_text/gui
```

Press **Start listening** to subscribe, then speak English and pause between
phrases. The window shows live transcripts, voice activity/input level,
approximate end-to-text delay, decoding time, decoding speed, queue delay,
speaking pace, and session averages. Above 1× decoding speed means the CPU
keeps up. End-to-text is estimated using 0.5-second speech-detection blocks.
**Stop** or closing the window disconnects this subscriber. Another subscriber
can keep capture active. **Clear results** resets the displayed session.

The GUI uses the installed system GTK 3/PyGObject libraries and requires no
additional packages. The service and command-line transcriber now default to
fixed English; the registered service explicitly passes `--language en`.
Automatic language detection is disabled. The GUI refuses a service reporting
a non-English language. No audio or transcript files are saved by the GUI.

Verified the live English connection, metric rendering, and microphone release
with Start/Stop. A synthetic transcript was used to check the metric display;
it was not a spoken recognition accuracy test.

## Speech speed tester

```sh
/noobia/speech_to_text/test-speed --language en
```

This listens for 60 seconds, prints each transcript and its timings, then
closes the microphone and summarizes the session. Ctrl+C stops early.
Read a paragraph at your usual pace, pause, then repeat it faster. For example:

> The Nexus is listening to a new microphone. Today we are testing how quickly
> speech becomes text. I can speak slowly, leave a short pause, and then speak
> faster. The important test is whether the words remain correct.

Check the displayed words against what you actually read. A fast incorrect
transcript does not demonstrate good recognition.

- **RTF:** decoding seconds divided by audio seconds. Below 1 means the model
  decodes faster than audio arrives. For example, 0.1 means 10× realtime.
- **Queue:** time a captured phrase waits before decoding starts.
- **End→text:** approximate time from the last voice-positive capture block
  to the completed transcript. It includes waiting for a pause, queueing,
  and decoding. Capture blocks are 0.5 seconds, so this is an estimate rather
  than a precise acoustic measurement. It is not first-word latency.
- **WPM:** recognized words per minute of voice detected by VAD. This is an
  approximate speaking rate, affected by recognition errors and VAD boundaries.
- **Session median/p95:** median and nearest-rank 95th percentile of the
  measured end-to-text delays. Small sessions have too few phrases for a
  reliable p95 comparison. Model loading is excluded from all timings.

For shorter updates, trade some recognition context for smaller chunks:

```sh
/noobia/speech_to_text/test-speed --language en --chunk-seconds 3 --pause-seconds 0.5
```

Use `--duration 120` for two minutes, `--duration 0` until Ctrl+C, or
`--language bg` for Bulgarian. Models and channels use the same options as
`listen`. New model choices require a download on first use.
An optional report includes transcripts and metrics, and never overwrites an
existing file:

```sh
/noobia/speech_to_text/test-speed --language en --report /tmp/speed-report.json
```

Without `--report`, the program saves neither audio nor transcripts.

## Live transcription

Start local live transcription:

```sh
/noobia/speech_to_text/listen
```

Stop with Ctrl+C. The array's physical mute button also silences input.
For a bounded session, use `--duration 30`. Language is fixed to English;
use `--language bg` to select Bulgarian explicitly. The default model is
multilingual `base`, running on the Ryzen CPU with int8 inference.

Speech is printed after approximately one second of silence or after six
seconds of continuous speech, plus decoding time. This is phrase transcription,
not a continuously revised word-by-word caption stream. Long speech can be cut
at a word boundary. The printed timing measures decoding and queue delay;
it does not measure latency from each spoken word.

Audio remains in memory and transcripts are printed to the terminal. There is
no background service and no automatic startup. Models are downloaded once
to `models/`; speech processing then runs locally. No audio is sent to a cloud
transcription service. New model names trigger another model download.

The stable ALSA device name is `hw:Array,0`. The connected device on 2026-10-06
reported 16 kHz, S16_LE, two capture channels. The initial three-second capture
contained signal on both channels, but voice detection found no speech.
Software channel 1 is the initial choice and remains to be compared using
spoken tests; use `--channel 0` to compare. USB channel meaning depends on
firmware and routing. No firmware or desktop audio defaults were changed.

The first 30-second live test on channel 1 incorrectly produced “Don't worry
about that.” when the speaker said “bla bla bla”. The 2.0-second audio phrase
took 0.41 seconds to decode with no measured queue backlog. The microphone closed automatically at the end. This confirms
the capture-to-text path, but the first live recognition was wrong. More spoken
tests are needed, especially for Bulgarian.

The public whisper.cpp JFK reference sample (11.0 seconds, 16 kHz mono) was
also recognized coherently in 0.52 seconds using the same in-memory audio
path. File decoding through faster-whisper's PyAV helper is incompatible with
the installed PyAV 19 (`metadata_errors` argument); this live tool bypasses
that helper by supplying PCM arrays directly.

An isolated `.venv` contains dependencies. The system lacks `ensurepip`, so it
was populated with `pip --python .venv/bin/python install faster-whisper`.
`requirements.txt` records the installed versions. Preparation without listening:

```sh
/noobia/speech_to_text/listen --prepare
```

## Subscribe to live speech

The registered user service is `noobia-speech.service`. It is running for this
session; it is not enabled to start automatically at login. The socket server
opens the microphone on the first subscription and closes it after the last
subscriber disconnects. All clients share one transcriber. A subscription is
also a request to capture room audio, so connect only when listening is wanted.

```sh
systemctl --user start noobia-speech.service
/noobia/speech_to_text/subscribe
```

Ctrl+C unsubscribes. For raw JSON events, use `subscribe --json`. Stop the whole
service, including any active capture, with:

```sh
systemctl --user stop noobia-speech.service
```

The socket is `$XDG_RUNTIME_DIR/noobia-speech.sock` (currently
`/run/user/1000/noobia-speech.sock`), mode 0600. It uses AF_UNIX/SOCK_STREAM with
one UTF-8 JSON object per line. There is no TCP listener. It sends `status`
events and `transcript` events with `text`, `language`, `timestamp` (Unix wall
time), `audio_seconds`, `voice_seconds`, `words`, `decode_seconds`,
`queue_seconds`, and approximate `end_to_text_seconds`. Live `audio` events
include normalized RMS `level` and a `speech` detection flag every 0.5 seconds.
Subscribers cannot
change settings through the socket. Slow subscribers are disconnected if
their pending output exceeds 256 KiB. Transcript events are not stored in a
database or journal by the service. Its stdout contains startup status and
stderr may contain diagnostics.

Any local program, including Aria's command session, can subscribe:

```python
import json, socket
with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
    client.connect('/run/user/1000/noobia-speech.sock')
    with client.makefile() as events:
        for line in events:
            event = json.loads(line)
            if event['type'] == 'transcript':
                print(event['text'], flush=True)
```

This makes speech available to a running subscriber; it does not automatically
send speech into an idle chat or turn it into commands. To set a fixed language
or model, stop the systemd service and run `speech_service.py` using `.venv/bin/python`
with `--language en`, `--language bg`, or `--model NAME`. The standalone speed
tester and subscriber should be used separately because they both need the
same ALSA capture device.

Validated with two simultaneous clients: capture stayed active after the first
disconnect and stopped after the last. Speed summary calculations and a bounded
test/report run also passed. The short validation run contained no speech.

References: [Seeed setup guide](https://wiki.seeedstudio.com/respeaker_xvf3800_introduction/),
[faster-whisper](https://github.com/SYSTRAN/faster-whisper).
