"""Find Lynx by its pinned SSH host key on Noobia's local /24.

Only makes bounded TCP connects and reads public SSH host keys. It neither
authenticates to other hosts nor accepts a changed key at the old address.
"""
import asyncio
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parent.parent
NETWORK = ipaddress.ip_network('192.168.100.0/24')
PORTS = (22, 2222)


async def probe(ip, port, semaphore):
    async with semaphore:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(str(ip), port), timeout=0.8)
            writer.close()
            await writer.wait_closed()
            return str(ip), port
        except (OSError, asyncio.TimeoutError):
            return None


def pinned_key():
    fields = (ROOT / 'secrets/lynx_known_hosts').read_text().split()
    if len(fields) < 3 or fields[0] != 'lynx' or fields[1] != 'ssh-ed25519':
        raise ValueError('Pinned Lynx known_hosts entry differs')
    return fields[1:3]


def main():
    os.umask(0o077)
    out = ROOT / 'logs' / ('v34-pinned-key-discovery-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    report = {'state': 'scanning', 'started_ns': time.time_ns(),
              'network': str(NETWORK), 'ports': PORTS, 'open': [],
              'pinned_matches': [], 'phone_partition_writes': False}
    receipt = out / 'result.json'

    def save():
        temp = receipt.with_suffix('.tmp')
        temp.write_text(json.dumps(report, indent=2) + '\n')
        temp.replace(receipt)

    save()
    expected = pinned_key()
    semaphore = asyncio.Semaphore(64)

    async def scan():
        tasks = [probe(ip, port, semaphore) for ip in NETWORK.hosts() for port in PORTS]
        return await asyncio.gather(*tasks)

    opened = [item for item in asyncio.run(scan()) if item]
    report['open_ports'] = len(opened)
    save()
    for ip, port in opened:
        try:
            result = subprocess.run(['ssh-keyscan', '-T', '2', '-p', str(port),
                                     '-t', 'ed25519', ip], capture_output=True,
                                    text=True, timeout=4)
            keys = [line.split() for line in result.stdout.splitlines()
                    if line and not line.startswith('#')]
            match = any(len(fields) >= 3 and fields[1:3] == expected for fields in keys)
            entry = {'ip': ip, 'port': port, 'pinned_host_key_match': match,
                     'public_key_count': len(keys)}
            report['open'].append(entry)
            if match:
                report['pinned_matches'].append({'ip': ip, 'port': port})
            save()
        except subprocess.TimeoutExpired:
            report['open'].append({'ip': ip, 'port': port, 'keyscan_timeout': True})
            save()
    report.update(state='complete', finished_ns=time.time_ns())
    save()
    print(json.dumps({'state': report['state'], 'pinned_matches': report['pinned_matches'],
                      'open_ports': report['open_ports'], 'result': str(receipt)}))


if __name__ == '__main__':
    main()
