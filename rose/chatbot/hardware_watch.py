#!/usr/bin/env python3
"""Reacquire device identities after USB changes; never replay physical actions."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import gi
from gi.repository import Gio, GLib

STATE = Path(os.environ.get('XDG_RUNTIME_DIR', '/run/user/' + str(os.getuid()))) / 'rose-hardware.json'
EXPECTED = {'microphone': ('2886', '001a'), 'comfast_lolth': ('0bda', 'd723'),
    'keyboard_receiver': ('3151', '3020')}
SPEAKER = '54:15:89:73:C2:95'


def devices(root=Path('/sys/bus/usb/devices')):
    found = {}
    for device in root.iterdir():
        try:
            identity = ((device / 'idVendor').read_text().strip(), (device / 'idProduct').read_text().strip())
        except OSError:
            continue
        for name, wanted in EXPECTED.items():
            if identity == wanted:
                found[name] = {'present': True, 'port': device.name,
                    'serial': (device / 'serial').read_text().strip() if (device / 'serial').exists() else ''}
    return {name: found.get(name, {'present': False}) for name in EXPECTED}


def speaker(bus):
    objects = bus.call_sync('org.bluez', '/', 'org.freedesktop.DBus.ObjectManager',
        'GetManagedObjects', None, None, Gio.DBusCallFlags.NONE, 4000, None).unpack()[0]
    for path, interfaces in objects.items():
        properties = interfaces.get('org.bluez.Device1', {})
        if properties.get('Address', '').upper() == SPEAKER and properties.get('Paired'):
            connected = properties.get('Connected', False)
            if not connected:
                try:
                    bus.call_sync('org.bluez', path, 'org.bluez.Device1', 'Connect', None,
                        None, Gio.DBusCallFlags.NONE, 5000, None)
                except GLib.Error:
                    pass
            return connected
    return False


def restore_sink():
    try:
        graph = json.loads(subprocess.check_output(['pw-dump'], timeout=3))
        for node in graph:
            props = node.get('info', {}).get('props', {})
            if props.get('media.class') == 'Audio/Sink' and '54_15_89_73_C2_95' in props.get('node.name', ''):
                subprocess.run(['wpctl', 'set-default', str(node['id'])], timeout=3,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return False


def main():
    previous = None
    last_audio = 0
    bus = None
    while True:
        state = {'usb': devices(), 'checked_at': time.time()}
        if time.monotonic() - last_audio > 15:
            try:
                bus = bus or Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
                state['speaker_connected'] = speaker(bus)
                if state['speaker_connected']:
                    restore_sink()
            except GLib.Error:
                state['speaker_connected'] = False
                bus = None
            last_audio = time.monotonic()
        elif previous:
            state['speaker_connected'] = previous.get('speaker_connected', False)
        with tempfile.NamedTemporaryFile(mode='w', dir=STATE.parent, delete=False) as file:
            json.dump(state, file)
            temporary = Path(file.name)
        temporary.replace(STATE)
        if previous and previous['usb'] != state['usb']:
            print('USB topology changed; stable device identities reacquired', flush=True)
        previous = state
        time.sleep(3)


if __name__ == '__main__':
    main()
