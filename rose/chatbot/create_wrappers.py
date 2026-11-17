"""Generate the documented JSON-stdin wrappers for tools already installed on Syra."""
import json
from pathlib import Path

CALLS = Path(__file__).resolve().parents[1] / 'calls'
DISABLED = {'projector_cast', 'camera_snapshot', 'camera_detect', 'gnss', 'ubertooth_info'}
PREFIXES = {name: 'rose_' + name for name in (
    'microphone', 'speech', 'camera', 'camera_snapshot', 'camera_detect', 'hue_off', 'hue_strip', 'hue_pattern', 'shell')}
PREFIXES.update({name: 'syra_' + name for name in ('plug', 'devices', 'gnss', 'ubertooth_info')})


def object_schema(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties),
            'additionalProperties': False}


def enum(*values):
    return {'type': 'string', 'enum': list(values)}


byte = {'type': 'integer', 'minimum': 0, 'maximum': 255}
tools = {
    'rose_youtube_pause': ('Entity: Rose. Pause the embedded YouTube player. Queues the action and returns immediately.', {}, 10),
    'rose_youtube_resume': ('Entity: Rose. Resume the paused embedded YouTube player. Returns immediately.', {}, 10),
    'rose_youtube_volume': ('Entity: Rose. Set YouTube player volume only, without changing Rose’s speech volume. Returns immediately.',
        {'volume': {'type': 'integer', 'minimum': 0, 'maximum': 100, 'description': 'YouTube player volume percentage, 0 through 100.'}}, 10),
    'rose_youtube_mute': ('Entity: Rose. Mute or unmute the embedded YouTube player. Returns immediately.',
        {'muted': {'type': 'boolean', 'description': 'True mutes; false unmutes.'}}, 10),
    'rose_youtube_seek': ('Entity: Rose. Seek the active YouTube video to a position in seconds. Returns immediately.',
        {'seconds': {'type': 'integer', 'minimum': 0, 'maximum': 86400, 'description': 'Position from the beginning of the video, in seconds.'}}, 10),
    'rose_youtube_search': ('Entity: Rose. Search YouTube using the official Data API. Returns video IDs, titles, channels and links. Requires a YouTube Data API key saved in Settings; browser login is separate.',
        {'query': {'type': 'string', 'minLength': 1, 'maxLength': 500, 'description': 'The video search words.'},
         'limit': {'type': 'integer', 'minimum': 1, 'maximum': 10, 'description': 'Maximum number of video results.'}}, 25),
    'rose_youtube_play': ('Entity: Rose. Play a YouTube video immediately on the HDMI screen with autoplay enabled. Replaces the current video; there is no queue. Confirms that this video is playing, or returns a startup error within 20 seconds. Does not wait for the video to finish; continue the conversation and other tools.',
        {'video_id': {'type': 'string', 'pattern': '^[A-Za-z0-9_-]{11}$', 'description': 'The 11-character YouTube video ID returned by search or extracted from a link.'},
         'start_seconds': {'type': 'integer', 'minimum': 0, 'maximum': 86400, 'description': 'Start position in seconds.'},
         'muted': {'type': 'boolean', 'description': 'True starts muted; false plays audio through the system speaker.'}}, 30),
    'rose_youtube_stop': ('Entity: Rose. Stop background YouTube playback and restore the camera display. Returns immediately.', {}, 10),
    'rose_display_status': ('Entity: Rose. Read current player mode, video ID, player state, position and errors. State 1 means playing, 2 paused, 3 buffering, 0 ended. No video queue exists.', {}, 10),
    'rose_youtube_login': ('Entity: Rose. Open Google’s YouTube sign-in in the private display browser. Noob signs in directly; never ask for or type passwords in chat. The browser keeps the session across launches. This does not create the Data API search key.', {}, 10),
    'camera': ('Capture a camera image with IMX500 object detection. Returns the saved image path and detected objects, labels, confidence and boxes. The photo is also shown on HDMI. No arguments. Initial model loading may take several minutes.', {}, 360),
    'lolth_info': ('Entity: Lolth, the LAFVIN Spiderbot. Read firmware identity and available factory action names; no motion.', {}, 15),
    'lolth_state': ('Entity: Lolth. Read current/requested action; no motion.', {}, 15),
    'lolth_servos': ('Entity: Lolth. Read eight last-commanded servo angles; these are not measured joint positions.', {}, 15),
    'lolth_distance': ('Entity: Lolth. Read ultrasonic distance in millimetres and validity; no echo is not a valid measurement.', {}, 15),
    'lolth_calibration': ('Entity: Lolth. Read the eight saved servo calibration offsets; no motion or writes.', {}, 15),
    'lolth_action': ('Entity: Lolth. Run one factory motion action. Read lolth_info for supported names. Requires a specific move agreed with Noob; never test motion automatically.',
        {'name': {'type': 'string', 'minLength': 1, 'maxLength': 64, 'description': 'Factory action name reported by lolth_info.'}}, 15),
    'lolth_servo': ('Entity: Lolth. Move exactly one servo to an absolute electrical angle. Requires a specific move agreed with Noob.',
        {'number': {'type': 'integer', 'minimum': 1, 'maximum': 8, 'description': 'Human servo number, 1 through 8.'},
         'angle': {'type': 'integer', 'minimum': 1, 'maximum': 180, 'description': 'Absolute electrical angle in degrees; physical direction depends on the joint.'}}, 15),
    'lolth_step': ('Entity: Lolth. Move one servo by a small electrical-angle step. Requires a specific move agreed with Noob.',
        {'number': {'type': 'integer', 'minimum': 1, 'maximum': 8, 'description': 'Human servo number 1 through 8.'},
         'direction': enum('up', 'down'), 'degrees': {'type': 'integer', 'minimum': 1, 'maximum': 20,
         'description': 'Step magnitude in electrical degrees. Up increases, down decreases; this does not imply physical up/down.'}}, 15),
    'lolth_stop': ('Entity: Lolth. Stop the current action and request a pose; this CAN MOVE joints. Requires an agreed physical move, not a passive emergency stop.',
        {'mode': enum('standby', 'center', 'zero')}, 15),
    'lolth_calibration_change': ('Entity: Lolth. Change one EEPROM calibration offset and verify it. No immediate movement, but changes future motions. Requires Noob’s explicit calibration request.',
        {'operation': enum('set', 'add'), 'servo_id': {'type': 'integer', 'minimum': 0, 'maximum': 7,
         'description': 'ZERO-based calibration ID, 0 through 7; unlike human servo numbering.'},
         'degrees': {'type': 'integer', 'minimum': -124, 'maximum': 124, 'description': 'Signed absolute offset for set, or signed delta for add; final offset must remain -124..124.'}}, 20),
    'lolth_program': ('Entity: Lolth. Preview or explicitly apply a saved pose. Targets are calibration candidates; servo 8 default is provisional. Execute only after an agreed physical move.',
        {'pose': enum('default', 'standby'), 'execute': {'type': 'boolean', 'description': 'False previews locally without contacting the robot; true applies selected targets.'},
         'servo': {'type': ['integer', 'null'], 'minimum': 1, 'maximum': 8, 'description': 'One human servo number to select, or null.'},
         'all': {'type': 'boolean', 'description': 'With execute=true and servo=null, true explicitly selects all targets.'}}, 60),
    'microphone': ('Check, stop, or resume Rose’s live microphone collection. Off clears unsent speech; keyboard still works. The explicit setting persists across restart.',
                   {'action': enum('status', 'on', 'off')}, 10),
    'speech': ('Speak text using Rose’s local voice and animated Hue strip.',
               {'text': {'type': 'string', 'minLength': 1, 'maxLength': 8000}}, 300),
    'camera_snapshot': ('Capture an image with the local camera; returns a JPEG path.', {}, 60),
    'camera_detect': ('Run IMX500 object/pose detection; returns local artifact paths and results.',
                      {'model': enum('object0', 'object1', 'object2', 'pose0')}, 360),
    'hue_off': ('Stop the Hue strip and clear its animation lock. This does not affect Syra power.', {}, 15),
    'hue_strip': ('Read or control the Hue light strip. Brightness may be null to keep its setting.',
                  {'action': enum('status', 'on', 'off', 'toggle'),
                   'brightness': {'type': ['integer', 'null'], 'minimum': 1, 'maximum': 254}}, 20),
    'hue_pattern': ('Play up to 120 seconds of RGB steps on the strip; darkens at the end.',
                    {'steps': {'type': 'array', 'minItems': 1, 'maxItems': 60,
                     'items': object_schema(dict(red=byte, green=byte, blue=byte, brightness=byte,
                         seconds={'type': 'number', 'minimum': 0, 'maximum': 120}))}}, 160),
    'projector_cast': ('Show a local image/video on the Hccast projector. Requires it to be online.',
                       {'path': {'type': 'string', 'maxLength': 1024}}, 180),
    'plug': ('Read the Tuya plug or ensure it is ON. Local key may still be missing. Power OFF is prohibited.',
             {'action': enum('status', 'on')}, 20),
    'devices': ('Inventory Syra’s connected USB devices and hardware services.', {}, 30),
    'gnss': ('Read six GPSD reports from the GNSS receiver; indoors a fix may be unavailable.', {}, 15),
    'ubertooth_info': ('Read Ubertooth firmware version without radio capture or transmission.', {}, 15),
}

argument_descriptions = {
    'microphone': {'action': 'status reports enabled state and buffered phrase count; off stops this agent’s subscription and clears unsent speech; on resumes collection with love as the send trigger.'},
    'speech': {'text': 'The English text to speak aloud; Hue brightness follows the voice.'},
    'camera_detect': {'model': 'Detection model: object0/1/2 are object detectors, pose0 estimates human poses.'},
    'hue_strip': {'action': 'Read status, turn on, turn off, or toggle only the Hue strip.',
                  'brightness': 'Hue brightness 1–254; null preserves the current setting.'},
    'hue_pattern': {'steps': 'Ordered RGB/brightness steps. Each seconds value is its transition/hold duration; total must be at most 120 seconds.'},
    'projector_cast': {'path': 'Absolute path to an existing image or video in /noobia, ~/Pictures, ~/Videos, or ~/Downloads. Hidden/private/backup files are rejected.'},
    'plug': {'action': 'Read relay status or turn the plug on. Off/toggle are absent because it powers Syra.'},
}
examples = {
    'rose_youtube_volume': {'volume': 50}, 'rose_youtube_mute': {'muted': True}, 'rose_youtube_seek': {'seconds': 60},
    'rose_youtube_search': {'query': 'ambient music', 'limit': 5},
    'rose_youtube_play': {'video_id': 'M7lc1UVf-VE', 'start_seconds': 0, 'muted': False},
    'lolth_action': {'name': 'standby'}, 'lolth_servo': {'number': 1, 'angle': 90},
    'lolth_step': {'number': 1, 'direction': 'up', 'degrees': 5}, 'lolth_stop': {'mode': 'standby'},
    'lolth_calibration_change': {'operation': 'add', 'servo_id': 0, 'degrees': 1},
    'lolth_program': {'pose': 'default', 'execute': False, 'servo': None, 'all': False},
    'microphone': {'action': 'off'},
    'speech': {'text': 'Hello Noob.'}, 'camera_detect': {'model': 'object0'},
    'hue_strip': {'action': 'status', 'brightness': None},
    'hue_pattern': {'steps': [{'red': 255, 'green': 20, 'blue': 100, 'brightness': 100, 'seconds': 1}]},
    'projector_cast': {'path': '/home/rose/Pictures/example.jpg'}, 'plug': {'action': 'status'},
}


def main():
    CALLS.mkdir(exist_ok=True)
    for old_name, new_name in PREFIXES.items():
        for suffix in ('.sh', '.json'):
            source = CALLS / (old_name + suffix)
            if source.exists():
                legacy = CALLS.parent / 'disabled_calls' / 'legacy'
                legacy.mkdir(parents=True, exist_ok=True)
                destination = legacy / source.name
                if destination.exists():
                    raise FileExistsError('Legacy wrapper backup already exists: ' + str(destination))
                source.rename(destination)
    for name, (description, properties, timeout) in tools.items():
        if name in DISABLED:
            archive = CALLS.parent / 'disabled_calls'
            archive.mkdir(exist_ok=True)
            for base in {name, PREFIXES.get(name, name)}:
                for suffix in ('.sh', '.json'):
                    source = CALLS / (base + suffix)
                    if source.exists():
                        destination = archive / source.name
                        if destination.exists():
                            raise FileExistsError('Disabled wrapper backup already exists: ' + str(destination))
                        source.rename(destination)
            continue
        for argument, explanation in argument_descriptions.get(name, {}).items():
            properties[argument]['description'] = explanation
        logical_name = name
        name = PREFIXES.get(name, name)
        if name.startswith(('rose_', 'syra_')):
            description = 'Entity: ' + ('Rose' if name.startswith('rose_') else 'Syra') + '. ' + description
        script = CALLS / (name + '.sh')
        script.write_text('#!/bin/sh\n# ' + description + '\n'
            'ROSE_CHAT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/../chatbot" && pwd)" || exit 1\n'
            'case "${1:-}" in --help|-h) exec /usr/bin/python3 "$ROSE_CHAT_DIR/wrapper_help.py" "$0" ;; esac\n'
            'exec "$ROSE_CHAT_DIR/.venv/bin/python" "$ROSE_CHAT_DIR/tool_dispatch.py" ' + name + '\n')
        script.chmod(0o755)
        script.with_suffix('.json').write_text(json.dumps(dict(description=description,
            parameters=object_schema(properties), protocol='json-stdin', timeout=timeout,
            example=examples.get(logical_name, {})), indent=2) + '\n')
    shell = CALLS / 'rose_shell.sh'
    shell.write_text('#!/bin/sh\n# Entity: Rose. Execute commands using the C shell launcher.\n'
        'ROSE_SHELL_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/../shell" && pwd)" || exit 1\n'
        'case "${1:-}" in --help|-h) exec /usr/bin/python3 "$ROSE_SHELL_DIR/../chatbot/wrapper_help.py" "$0" ;; esac\n'
        'exec "$ROSE_SHELL_DIR/rose-shell" "$@"\n')
    shell.chmod(0o755)
    shell.with_suffix('.json').write_text(json.dumps(dict(
        description='Entity: Rose on Syra. Execute /bin/sh commands as the rose Linux user. Returns stdout/stderr and exit status. Never cut Syra power or disclose credentials without an explicit request. Inspect before destructive actions.',
        parameters=object_schema({'command': {'type': 'string', 'minLength': 1, 'maxLength': 8000,
            'description': 'Shell command text, including pipelines/redirections. Executes with existing account permissions; no added root privileges.'}}),
        protocol='command-stdin', timeout=120), indent=2) + '\n')


if __name__ == '__main__':
    main()
