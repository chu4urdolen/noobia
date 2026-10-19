"""Install the reviewed OpenRC health adoption service in Lynx's Alpine root."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import PROOF, proof_valid, ssh_command


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'linux-port/openrc-lynx-health'
IP = '192.168.100.4'
V19_SHA = '5ce2dbf8a7c132fa7e31f6be70aa76f83afe8c293e2cd5f02251a532486fd851'
ROOT_UUID = '13dc3665-b062-405e-b674-ceae8972fc0f'


def main():
    os.umask(0o077)
    data = SOURCE.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if not data.startswith(b'#!/sbin/openrc-run\n') or len(data) > 16_384:
        raise ValueError('Health service source differs from reviewed shape')
    out = ROOT / 'logs' / ('persistent-openrc-health-install-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'created_ns': time.time_ns(),
              'phone_ip': IP, 'service_sha256': digest,
              'device': '/dev/sdc85', 'boot_image_changed': False,
              'phone_partition_writes': False}

    def save():
        tmp = out / 'result.tmp'
        tmp.write_text(json.dumps(report, indent=2) + '\n')
        tmp.replace(out / 'result.json')

    save()
    try:
        identity = subprocess.run(ssh_command(IP, PROOF), capture_output=True, timeout=15)
        if not proof_valid(identity.stdout.decode(errors='replace'), identity.returncode):
            raise ValueError('Pinned V19 SSH identity refused')
        preflight = '''set -eu
cat /proc/sys/kernel/random/boot_id
/bin/busybox sha256sum /dev/sdc39
cat /run/lynx/health-bootstrap/ready
! grep -Eq '^/dev/sdc85 |^/dev/block/by-name/userdata ' /proc/mounts
/bin/busybox blkid /dev/sdc85'''
        before = subprocess.run(ssh_command(IP, preflight), capture_output=True, timeout=30)
        (out / 'preflight.stdout').write_bytes(before.stdout)
        (out / 'preflight.stderr').write_bytes(before.stderr)
        lines = before.stdout.decode(errors='replace').splitlines()
        if (before.returncode or len(lines) != 4 or
                lines[1] != V19_SHA + '  /dev/sdc39' or lines[2] != 'ready' or
                f'UUID="{ROOT_UUID}"' not in lines[3] or
                'LABEL="LYNXROOT"' not in lines[3] or 'TYPE="ext4"' not in lines[3]):
            raise ValueError('Live boot or Alpine ext4 preflight refused')
        boot_id = lines[0]
        report.update(state='preflight-passed', boot_id=boot_id)
        save()
        command = f'''set -eu
[ "$(cat /proc/sys/kernel/random/boot_id)" = {boot_id} ]
! grep -Eq '^/dev/sdc85 |^/dev/block/by-name/userdata ' /proc/mounts
root=/run/lynx/persistent-openrc-install
mkdir -p "$root"
mounted=0
trap '[ "$mounted" = 0 ] || umount "$root" || true' EXIT
mount -t ext4 -o rw /dev/sdc85 "$root"
mounted=1
[ "$(cat "$root/etc/alpine-release")" = 3.24.2 ]
test -x "$root/sbin/openrc-init"
test -d "$root/etc/init.d"
test -d "$root/etc/runlevels/default"
test ! -e "$root/etc/init.d/lynx-health"
test ! -L "$root/etc/init.d/lynx-health"
test ! -e "$root/etc/runlevels/default/lynx-health"
test ! -L "$root/etc/runlevels/default/lynx-health"
test ! -e "$root/etc/init.d/lynx-health.new"
/bin/busybox cat > "$root/etc/init.d/lynx-health.new"
[ "$(/bin/busybox sha256sum "$root/etc/init.d/lynx-health.new")" = '{digest}  '$root'/etc/init.d/lynx-health.new' ]
chmod 755 "$root/etc/init.d/lynx-health.new"
mv "$root/etc/init.d/lynx-health.new" "$root/etc/init.d/lynx-health"
ln -s ../../init.d/lynx-health "$root/etc/runlevels/default/lynx-health"
sync
umount "$root"
mounted=0
mount -t ext4 -o ro,noload /dev/sdc85 "$root"
mounted=1
[ "$(/bin/busybox sha256sum "$root/etc/init.d/lynx-health")" = '{digest}  '$root'/etc/init.d/lynx-health' ]
[ "$(readlink "$root/etc/runlevels/default/lynx-health")" = ../../init.d/lynx-health ]
echo PERSISTENT_OPENRC_HEALTH_INSTALLED
umount "$root"
mounted=0
trap - EXIT'''
        report.update(state='install-in-progress', phone_partition_writes=True)
        save()
        with SOURCE.open('rb') as source:
            installed = subprocess.run(ssh_command(IP, command), stdin=source,
                                       capture_output=True, timeout=30)
        (out / 'install.stdout').write_bytes(installed.stdout)
        (out / 'install.stderr').write_bytes(installed.stderr)
        if (installed.returncode or
                b'PERSISTENT_OPENRC_HEALTH_INSTALLED\n' not in installed.stdout):
            raise ValueError('OpenRC health install failed or is incomplete')
        post = subprocess.run(ssh_command(IP, '''set -eu
! grep -Eq '^/dev/sdc85 |^/dev/block/by-name/userdata ' /proc/mounts
cat /proc/sys/kernel/random/boot_id
cat /run/lynx/health-bootstrap/ready'''), capture_output=True, timeout=15)
        (out / 'postflight.stdout').write_bytes(post.stdout)
        (out / 'postflight.stderr').write_bytes(post.stderr)
        if post.returncode or post.stdout.decode(errors='replace').splitlines() != [boot_id, 'ready']:
            raise ValueError('Postflight mount or health state differs')
        report['state'] = 'openrc-health-service-installed-and-verified'
    except Exception as error:
        report.update(state='failed-or-incomplete', error=str(error))
    report['finished_ns'] = time.time_ns()
    save()
    print(json.dumps({'state': report['state'], 'result': str(out / 'result.json')}))
    if report['state'] != 'openrc-health-service-installed-and-verified':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
