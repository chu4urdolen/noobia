#!/usr/bin/python3
"""Apply the verified Noobia addresses, preserving credentials and backup files."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time

if os.getuid() != 0:
    raise SystemExit('Administrator authentication is required for /etc/noobia-council.')
host = socket.gethostname().lower()
if host not in ('nexus', 'syra'):
    raise SystemExit('This address repair is scoped to Nexus and Syra.')
root = Path('/etc/noobia-council')
backup = Path('/var/backups') / ('noobia-council-addresses-' + time.strftime('%Y%m%d-%H%M%S'))
backup.mkdir(mode=0o700)

def replace(path, text):
    original = path.stat()
    shutil.copy2(path, backup / path.name)
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as output:
        output.write(text)
        output.flush()
        os.fsync(output.fileno())
        os.fchmod(output.fileno(), original.st_mode & 0o777)
        os.fchown(output.fileno(), original.st_uid, original.st_gid)
        temporary = output.name
    os.replace(temporary, path)

contacts_path = root / 'contacts.json'
data = json.loads(contacts_path.read_text())
contacts = data if isinstance(data, list) else data['contacts']
for contact in contacts:
    if contact['name'] in ('Noob', 'Aria'):
        contact['host'] = '192.168.100.106'
    elif contact['name'] == 'Argus':
        contact['host'] = '192.168.100.105'
replace(contacts_path, json.dumps(data, indent=2) + '\n')
config_path = root / 'service.conf'
lines = []
for line in config_path.read_text().splitlines():
    if '=' in line and not line.lstrip().startswith('#'):
        key, value = line.split('=', 1)
        if host == 'syra' and key in ('hub_host', 'bridge_host', 'web_hub_host') and value == '192.168.100.6':
            line = key + '=192.168.100.106'
        if host == 'nexus' and key == 'desired_ip':
            line = 'desired_ip=192.168.100.106'
        if host == 'nexus' and key == 'mac':
            line = 'mac=40:a5:ef:5f:66:f1'
    lines.append(line)
replace(config_path, '\n'.join(lines) + '\n')
services = ['noobia-council.service', 'noobia-council-web.service']
services.append('noobia-council-codex-bridge@rose.service' if host == 'syra' else 'noobia-council-codex-bridge@aria.service')
for service in services:
    if subprocess.run(['systemctl', 'is-active', '--quiet', service]).returncode == 0:
        subprocess.run(['systemctl', 'restart', service], check=True)
print(f'Updated {host} Council addresses; credentials preserved. Backup: {backup}')
