#!/usr/bin/env python3
"""Control the previously configured Hue strip using Rose's existing bridge key."""
import argparse
import json
from pathlib import Path
import sys
import urllib.request


def request(config, path, body=None):
    url = f"http://{config['HUE_BRIDGE_IP']}/api/{config['HUE_USERNAME']}/{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method='PUT' if data else 'GET',
                                 headers={'Content-Type': 'application/json'})
    result = json.load(urllib.request.urlopen(req, timeout=5))
    if isinstance(result, list) and any('error' in item for item in result):
        raise RuntimeError('Hue rejected the request')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['status', 'on', 'off', 'toggle'])
    parser.add_argument('--config', type=Path, default=Path(__file__).parent / 'private/hue.conf')
    parser.add_argument('--brightness', type=int, choices=range(1, 255), metavar='1..254')
    args = parser.parse_args()
    config = {}
    for line in args.config.read_text().splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key, value = line.split('=', 1)
            config[key.strip()] = value.strip()
    # Use the previously configured single light; reject groups and ambiguous targets.
    parts = config['HUE_TARGET'].split('/')
    if len(parts) != 3 or parts[0] != 'lights' or parts[2] != 'state' or not parts[1].isdigit():
        raise RuntimeError('Expected a single lights/ID/state target')
    path = f'lights/{parts[1]}'
    light = request(config, path)
    if light.get('modelid') != 'LCL001':
        raise RuntimeError('Configured device is not the identified Hue strip LCL001')
    if args.action != 'status':
        state = light['state']
        if not state.get('reachable'):
            raise RuntimeError('Strip is unreachable')
        on = not state['on'] if args.action == 'toggle' else args.action == 'on'
        body = {'on': on}
        if args.brightness is not None:
            body['bri'] = args.brightness
        request(config, path + '/state', body)
        light = request(config, path)
        if light['state']['on'] != on:
            raise RuntimeError('Strip state did not match the requested state')
    print(json.dumps({'name': light['name'], 'on': light['state']['on'],
                      'reachable': light['state']['reachable'], 'brightness': light['state'].get('bri')}, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # URLs include the credential; do not echo exception strings containing URLs.
        print(f'Hue operation failed ({type(exc).__name__}). Check bridge connectivity and private configuration.', file=sys.stderr)
        sys.exit(1)
