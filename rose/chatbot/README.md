# Rose chatbot

Rose runs on Syra with the OpenAI Responses API. `gpt-5.4-mini` is the configurable
default. English Whisper prefers Nexus, with local Syra fallback; OpenAI receives text.
Final replies use the existing local `rose-say` voice and Hue animation.

The black-and-green GTK dashboard has separate keyboard, input-history, spoken
reply, and tool-output panels. All tool outputs stay textual on the main GUI.
It opens fullscreen on the DSI touchscreen. A second fullscreen window on
HDMI-A-2 shows camera images, fitted with their aspect ratio preserved. It starts
black and keeps the latest photo while other tools continue logging on the main
GUI. Output connector preferences are saved; another HDMI is used if the preferred
one is absent. If there is no HDMI display, the camera window stays hidden.
Both windows open automatically at desktop login via XDG autostart and one user
service. The Display button restores the display window; F11 toggles fullscreen
for either window. Closing the GUI leaves the chatbot and microphone running.
Window sizes and panel proportions are saved in `~/.config/rose-chat/layout.json`.
Resizing scales from the original image rather than progressively resizing a
previous preview. Raw tool outputs never feed the automatic speech path.

Run `./install.sh` as Rose on Syra, then launch `rose-chat` or **Rose Chat** from
the application menu. Settings stores the API key in
`~/.config/rose-chat/settings.json` with mode 0600, outside the repository.
Keyboard input is always available. Microphone collection starts enabled by
default and remains running when the GUI closes. The `rose_microphone` tool supports
status/on/off; explicitly stopping it persists across service restarts until
listening is resumed. Off clears unsent speech. It stops this agent's subscription,
not other independent users of the shared speech service.
The microphone gathers finalized phrases and sends the entire batch when its
latest phrase contains the whole word **“love”** (case insensitive). “Lovely”
does not trigger it. The GUI shows phrases as they accumulate. Hearing continues
while the model thinks. Transcripts whose estimated capture interval overlaps
Rose's own spoken output are discarded to prevent feedback; overlapping human
speech may also be discarded because there is no speaker separation. Stopping
or restarting microphone input clears its unsent batch. Batches are limited to
8,000 characters; the microphone stops and displays an error if that fills up.
This is a local transcript gate, not speaker identification/authentication.
Stop cancels pending work and terminates tool
processes; an in-flight API request can take up to its 90-second timeout to return.
Closing the window leaves microphone input running. The service remains available for
other local inputs. No conversation is written to disk; restarting clears it.

Conversation context contains the last eight complete turns. Responses are
limited to 1,200 output tokens per call and six API calls per turn. Tool execution
is sequential. API errors are displayed without automatic retries, to avoid
repeating physical actions. The speech checkbox controls automatic spoken replies.
Tool failures leave text replies visible. Remote storage is disabled with
`store: false`; that setting does not override OpenAI account retention policies.

## Tools

All regular, non-symlink `../calls/*.sh` files with valid function names are
discovered before each turn. The runner invokes each wrapper's `--help` and uses
that exact stdout as the agent tool description. Every wrapper must provide
successful, nonempty help. A same-name JSON manifest supplies its strict
parameters schema, timeout, and protocol. Built-in wrappers read one JSON
object from stdin and call the installed commands with literal argument lists.
They independently validate their input. A custom wrapper without a manifest
receives an `argv` array as literal arguments (no shell expansion), with a
60-second timeout. New scripts are trusted local code: review them before putting
them in `calls`. API-key environment variables are removed from tool processes.

Included: microphone control, full shell execution, speech, a single camera capture/object-detection tool, Hue patterns/direct control/off,
USB inventory and Tuya
status/on. The Tuya local key is still required; its OFF/toggle commands are
deliberately unavailable because the plug powers Syra.

There are 30 active wrappers. GNSS and Ubertooth wrappers are preserved outside
discovery; the removed TP-Link has no specialized wrapper. Default voice and light execution stays out of the
tool panel; it shows other tools' results. Replies favor shorter natural speech.
Before display and speech, punctuation other than `. , ! ?` becomes a space and
repeated whitespace collapses. Raw tool results are preserved.

## YouTube and recovery

`rose_youtube_search` uses the official YouTube Data API v3. The default search
key and OpenAI key are private settings outside Git, with file mode 0600.
Never put either key in source, examples, logs or commits. Local credentials and
runtime artifacts are ignored by Git; scan staged content before any publication.

`rose_youtube_play` starts playback through `rose-display-media.service`.
There is no video queue: a new play replaces the current video. Autoplay is
enabled, with new videos starting at 50 percent volume. The tool returns success only after the requested video starts playing,
or a startup error within 20 seconds; it never waits for the video to finish.
Chromium embeds the official IFrame player fullscreen on HDMI; it autoplays with
sound unless muted. Pause, resume, volume, mute, seek and stop are separate tools.
Status reports actual player state and position. The camera display and player
share the HDMI screen; camera results switch back to the fitted photo view.

The YouTube sign-in button opens native Chromium for Noob to sign in once.
Search credentials do not authenticate a YouTube account. Its dedicated private
profile preserves session cookies. `--password-store=basic` avoids keyring
prompts, and password saving is disabled; the profile is not an encrypted vault.

The speech supervisor reacquires ReSpeaker by stable USB identity after a
disconnect or capture-process failure, restarts capture, and retains subscribers.
`rose-hardware-watch.service` watches USB presence and reconnects the paired JBL
speaker, restoring the audio sink. Network profiles bind adapter MAC addresses;
The removed TP-Link, GNSS and Ubertooth are excluded from active monitoring.
The display service supervises Chromium
and checkpoints playback position for recovery. This handles reconnection, not
physical power loss itself. Failed physical actions are never automatically
replayed.

The player sends a heartbeat even when paused. If heartbeats cease, the display
watchdog restarts its browser after a 60-second startup grace period and 30
seconds without a report, retaining the latest saved playback position. Track
changes update the existing IFrame instead of navigating the entire page.
Observed loading states do not overwrite the requested autoplay/pause setting.

Function and wrapper prefixes identify the entity: `rose_` for voice/mic/shell/
camera/Hue, `syra_` for computer hardware, and `lolth_` for the spiderbot.
Eleven Lolth tools cover info, state, servos, distance, calibration read/change,
factory actions, absolute servo motion, small steps, pose-stop, and saved pose
preview/execution. Only read-only commands are used for connectivity tests.
Motion and calibration changes require a specific agreed request from Noob;
Lolth's pose-stop can itself move joints. Original unprefixed wrappers are kept
outside discovery in `disabled_calls/legacy/`.

`calls/rose_shell.sh` directly executes the C program `shell/rose-shell`. Its tool
manifest uses `command-stdin`: the runner writes the validated `command` string
to stdin, and C replaces itself with `/bin/sh -c` to execute it. Stdout and stderr
are captured together, with the actual exit status. Commands have a 120-second
timeout. Standalone use: `calls/rose_shell.sh -c 'uname -a'`. It runs with Rose's
existing account permissions, with no added root privileges or sandbox. This
is intentionally broad access: the plug-specific OFF restriction is no longer
a security boundary against arbitrary shell commands. The agent is instructed
never to cut Syra's power or expose credentials. Its shell actions appear in the
GUI tool log along with their results.

The chatbot definition is `agent.md`, including Rose's supplied personality,
identity declaration, environment, tool instructions, and present memory limits.
It is reread each turn. The separate Council personality file is preserved.

Camera outputs are artifact paths, not automatically uploaded images. The
projector is temporarily excluded from tool discovery; its wrapper is preserved
in `../disabled_calls/` and the installer keeps it disabled. When re-enabled, it
accepts media under `/noobia`, `~/Pictures`, `~/Videos`, or
`~/Downloads`; hidden/private/backup files are rejected. Other unavailable
hardware returns an error to the conversation rather than claiming success.

## Other inputs and subscribers

`$XDG_RUNTIME_DIR/rose-chat.sock` is a private Unix socket (0600). Send UTF-8 JSON
objects, one per line:

```json
{"type":"subscribe"}
{"type":"submit","source":"keyboard","text":"Hello Rose"}
{"type":"microphone","enabled":true}
{"type":"microphone_status"}
{"type":"cancel"}
{"type":"clear"}
```

Subscribers receive `heard`, `input`, `state`, `tool`, `usage`, `reply`, and `error`
events. A source tag distinguishes keyboard, microphone, and future adapters.
Inputs are limited to 8,000 characters and eight queued requests. The example
adapter is `python3 submit.py --source sensor 'Your text here'`. Socket access is
restricted to the Rose account; there is no network listener.

```sh
systemctl --user status rose-chat.service
systemctl --user restart rose-chat.service
systemctl --user stop rose-chat.service
.venv/bin/python -m unittest test_chat.py
```

API references: [Responses function calling](https://developers.openai.com/api/docs/guides/function-calling),
[GPT-5.4 mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini).
