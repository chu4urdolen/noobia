#!/usr/bin/env python3
"""One-time Syra administrator setup: COMFAST Lolth profile and scoped poweroff."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

PROFILE = 'Lolth COMFAST'
MAC = '40:a5:ef:70:7d:cb'


def run(*command, check=True):
    return subprocess.run(command, capture_output=True, text=True, check=check, timeout=30)


def main():
    if os.geteuid() != 0:
        raise SystemExit('Administrator authentication is required')
    backup = Path('/var/backups') / ('noobia-rose-agent-' + time.strftime('%Y%m%d-%H%M%S'))
    backup.mkdir(mode=0o700)
    rule = Path('/etc/sudoers.d/noobia-rose-poweroff')
    if rule.exists():
        shutil.copy2(rule, backup / rule.name)
    candidate = backup / 'poweroff.candidate'
    candidate.write_text('# Noobia: only the explicit Syra poweroff command.\n'
                         'rose ALL=(root) NOPASSWD: /usr/bin/systemctl poweroff\n')
    candidate.chmod(0o440)
    run('/usr/sbin/visudo', '-cf', str(candidate))
    shutil.copyfile(candidate, rule)
    rule.chmod(0o440)
    os.chown(rule, 0, 0)
    existing = run('/usr/bin/nmcli', '-g', 'connection.id', 'connection', 'show', PROFILE, check=False)
    if existing.returncode:
        run('/usr/bin/nmcli', 'connection', 'add', 'type', 'wifi', 'ifname', '*',
            'con-name', PROFILE, 'ssid', 'Robot - EC36')
    run('/usr/bin/nmcli', 'connection', 'modify', PROFILE,
        'connection.interface-name', '', '802-11-wireless.mac-address', MAC,
        'connection.autoconnect', 'yes', 'connection.autoconnect-priority', '999',
        'connection.autoconnect-retries', '0',
        '802-11-wireless-security.key-mgmt', 'wpa-psk',
        '802-11-wireless-security.psk', '12345678',
        'ipv4.method', 'auto', 'ipv4.never-default', 'yes', 'ipv4.ignore-auto-dns', 'yes',
        'ipv6.method', 'disabled')
    interfaces = [p.name for p in Path('/sys/class/net').iterdir()
                  if (p / 'address').exists() and (p / 'address').read_text().strip().lower() == MAC]
    connected = False
    if interfaces:
        result = run('/usr/bin/nmcli', '--wait', '8', 'connection', 'up', PROFILE,
                     'ifname', interfaces[0], check=False)
        connected = result.returncode == 0
    print(json.dumps({'shutdown_permission': 'only systemctl poweroff',
        'profile': PROFILE, 'dedicated_mac': MAC, 'interface': interfaces[0] if interfaces else None,
        'connected': connected, 'never_default_route': True, 'backup': str(backup)}), flush=True)


if __name__ == '__main__':
    main()
