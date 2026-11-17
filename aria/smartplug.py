#!/usr/bin/env python3
"""Local plug discovery and explicit on/off/toggle control from private configuration."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
import urllib.request


def check_power_action(config, action, allow_power_cut=False):
    if config.get('powers_syra') and action in ('off', 'toggle') and not allow_power_cut:
        raise RuntimeError('This plug powers Syra. Off/toggle is blocked; --allow-power-cut is required for a deliberate, explicitly requested power cut.')


def http(host, path):
    return json.load(urllib.request.urlopen(f'http://{host}/{path}', timeout=5))


async def discover():
    from kasa import Discover
    import tinytuya
    result = []
    devices = await Discover.discover(target='192.168.100.255', discovery_timeout=5)
    for host, device in devices.items():
        try:
            await device.update()
            result.append({'backend': 'kasa', 'host': host, 'name': device.alias,
                           'model': device.model, 'type': str(device.device_type)})
        except Exception:
            result.append({'backend': 'kasa', 'host': host, 'authentication_required': True})
        finally:
            await device.disconnect()
    tuya = await asyncio.to_thread(tinytuya.deviceScan, verbose=False, maxretry=2)
    for device in tuya.values():
        result.append({'backend': 'tuya', 'host': device.get('ip'), 'device_id': device.get('gwId'),
                       'version': device.get('version'), 'local_key_required': True})
    return result


async def kasa_control(config, action):
    from kasa import Discover, Credentials, DeviceType
    credentials = Credentials(config['username'], config['password']) if config.get('username') else None
    device = await Discover.discover_single(config['host'], credentials=credentials)
    if device is None:
        raise RuntimeError('Configured plug was not found')
    try:
        await device.update()
        if device.device_type != DeviceType.Plug:
            raise RuntimeError('Configured target is not a single smart plug')
        requested = None
        if action != 'status':
            requested = not device.is_on if action == 'toggle' else action == 'on'
            await (device.turn_on() if requested else device.turn_off())
            await device.update()
            if device.is_on != requested:
                raise RuntimeError('Relay did not reach requested state')
        return {'name': device.alias, 'model': device.model, 'on': device.is_on}
    finally:
        await device.disconnect()


def shelly_control(config, action):
    host = config['host']
    switch = int(config.get('switch_id', 0))
    if int(config.get('generation', 2)) == 1:
        path = f'relay/{switch}'
        state = http(host, path)
        on = state['ison']
        requested = not on if action == 'toggle' else action == 'on'
        if action != 'status':
            state = http(host, path + '?turn=' + ('on' if requested else 'off'))
            if state['ison'] != requested:
                raise RuntimeError('Relay did not reach requested state')
        return {'host': host, 'on': state['ison']}
    state = http(host, f'rpc/Switch.GetStatus?id={switch}')
    requested = not state['output'] if action == 'toggle' else action == 'on'
    if action != 'status':
        http(host, f'rpc/Switch.Set?id={switch}&on=' + str(requested).lower())
        state = http(host, f'rpc/Switch.GetStatus?id={switch}')
        if state['output'] != requested:
            raise RuntimeError('Relay did not reach requested state')
    return {'host': host, 'on': state['output']}


def tuya_control(config, action):
    import tinytuya
    device = tinytuya.OutletDevice(config['device_id'], config['host'], config['local_key'])
    device.set_version(float(config.get('version', '3.3')))
    device.set_socketTimeout(5)
    switch = str(config.get('switch_dps', '1'))
    try:
        state = device.status()
        on = state.get('dps', {}).get(switch)
        if not isinstance(on, bool):
            raise RuntimeError('No boolean relay state; check credentials and switch_dps')
        requested = not on if action == 'toggle' else action == 'on'
        if action != 'status':
            device.set_status(requested, int(switch))
            state = device.status()
            if state.get('dps', {}).get(switch) != requested:
                raise RuntimeError('Relay did not reach requested state')
        return {'host': config['host'], 'on': state['dps'][switch]}
    finally:
        device.close()


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['discover', 'status', 'on', 'off', 'toggle'])
    parser.add_argument('--config', type=Path, default=Path(__file__).parent / 'private/smartplug.json')
    parser.add_argument('--allow-power-cut', action='store_true', help='Explicitly allow off/toggle for the plug powering Syra; do not use during setup')
    args = parser.parse_args()
    if args.action == 'on' and Path(__file__).with_name('syra_power.py').exists():
        # Nexus: every turn-on path revokes a delayed cut under the same lock.
        from syra_power import Power
        result = await asyncio.to_thread(Power(config=args.config).on)
        print(json.dumps(result, indent=2))
        return
    if args.action == 'discover':
        result = await discover()
    else:
        if not args.config.exists():
            parser.error('No plug configured yet. Identify its brand/model and host; see README.md.')
        config = json.loads(args.config.read_text())
        check_power_action(config, args.action, args.allow_power_cut)
        backend = config['backend']
        if backend == 'kasa':
            result = await kasa_control(config, args.action)
        elif backend == 'shelly':
            result = await asyncio.to_thread(shelly_control, config, args.action)
        elif backend == 'tuya':
            missing = [key for key in ('device_id', 'local_key', 'version') if not config.get(key)]
            if missing:
                parser.error('Tuya configuration missing: ' + ', '.join(missing) + '. No relay command was sent.')
            result = await asyncio.to_thread(tuya_control, config, args.action)
        else:
            parser.error('Supported backends: kasa, shelly, tuya')
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as exc:
        detail = str(exc) if isinstance(exc, RuntimeError) else f'{type(exc).__name__}; check its network and private configuration'
        print(f'Plug operation blocked or failed: {detail}', file=sys.stderr)
        sys.exit(1)
