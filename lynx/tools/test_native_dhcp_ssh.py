"""Real ARM64 BusyBox supervisor and stock module in isolated stock-kernel QEMU."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
PROJECT = ROOT / 'linux-port'
sys.path.insert(0, str(PROJECT))
from image_formats import read_boot_v4, read_newc, require
from ramdisk_codec import decompress
from prepare_busybox_diagnostics import pack
from network_userspace import add_network_userspace


def main():
    output = PROJECT / 'artifacts' / ('emulated-native-dhcp-ssh-' + str(time.time_ns()))
    output.mkdir()
    reference = (PROJECT / 'artifacts/busybox-August-boot-proof-bound-guards/nord3-busybox-candidate.img').read_bytes()
    require(hashlib.sha256(reference).hexdigest() == 'a9a72334185a5ddec9b6e3ece6e9e01600582f62c4db7bebc8ce87c4d5c3fe43', 'Minimal reference changed')
    boot = read_boot_v4(reference)
    require(hashlib.sha256(boot['kernel']).hexdigest() == 'cbc9f5dc54b5198ddd1e82d5d7bde96f43cbb383a663726ddd68919b0639d3af', 'Kernel changed')
    entries = read_newc(decompress(boot['ramdisk']))
    require(hashlib.sha256(entries['lib/modules/mtu3.ko']['data']).hexdigest() == 'd3c59fa794a6e02f014dd0de660592bb66c9d7f8eb941c1d1183f8a3322bb467', 'Expected original stock MTU3')
    network_entries=add_network_userspace(entries,vm_client=True)
    init = b'#!/bin/sh\nexport PATH=/bin:/sbin:/usr/bin:/usr/sbin\nBB=/bin/busybox\n$BB mount -t proc proc /proc\n$BB mount -t sysfs sysfs /sys\n$BB mount -t tmpfs tmpfs /dev\n$BB mount -t tmpfs tmpfs /run\n$BB mknod -m 600 /dev/console c 5 1\n$BB mknod -m 666 /dev/null c 1 3\n$BB mknod -m 666 /dev/zero c 1 5\n$BB mknod -m 666 /dev/random c 1 8\n$BB mknod -m 666 /dev/urandom c 1 9\nexec > /dev/console 2>&1\n$BB mdev -s\n$BB ip link set lo up\n/sbin/wpa_supplicant -v || echo LYNX_VM_WPA_FAILED\n/usr/sbin/iw --version || echo LYNX_VM_IW_FAILED\n/usr/bin/dropbearkey -t ed25519 -f /run/server-key > /run/server-public 2>&1 || echo LYNX_VM_KEY_FAILED\n/usr/bin/dropbearkey -t ed25519 -f /run/client-key > /run/client-public 2>&1 || echo LYNX_VM_KEY_FAILED\n/usr/bin/dropbearkey -y -f /run/client-key | $BB grep \'^ssh-ed25519 \' > /root/.ssh/authorized_keys\n$BB chmod 600 /root/.ssh/authorized_keys\n/usr/sbin/dropbear -F -E -s -j -k -p 127.0.0.1:2222 -r /run/server-key > /run/server.log 2>&1 &\n$BB sleep 2\n/usr/bin/dbclient -y -i /run/client-key -p 2222 root@127.0.0.1 \'printf "LYNX_SSH_VM_OK\\n"; uname -r; id\'\ncode=$?\nprintf \'LYNX_VM_SSH_EXIT=%s\\n\' "$code"\n$BB cat /run/server.log\n/bin/boot-proof-reboot\nwhile :; do $BB sleep 60; done\n'
    from network_userspace import put
    hook=(PROJECT/'lynx-dhcp.sh').read_bytes()
    put(entries,'bin/lynx-dhcp-test',hook.replace(b'wlan0|wlan1',b'test0'))
    init=init.replace(b'/sbin/wpa_supplicant -v',b'$BB mkdir -p /run/lynx\n$BB ip link add test0 type veth peer name server0\n$BB ip link set test0 up\n$BB ip link set server0 up\n$BB ip addr add 192.0.2.1/24 dev server0\nprintf \'start 192.0.2.10\\nend 192.0.2.20\\ninterface server0\\nlease_file /run/dhcp.leases\\npidfile /run/dhcpd.pid\\noption subnet 255.255.255.0\\noption router 192.0.2.1\\noption dns 192.0.2.1\\n\' > /run/dhcpd.conf\n$BB udhcpd -f /run/dhcpd.conf > /run/dhcpd.log 2>&1 &\n$BB sleep 1\n$BB udhcpc -f -n -q -t 5 -T 1 -i test0 -s /bin/lynx-dhcp-test\nstatus=$?\nprintf \'LYNX_VM_DHCP_EXIT=%s\\n\' "$status"\n$BB cat /run/lynx/address /run/dhcpd.log /etc/resolv.conf\n'+b'/sbin/wpa_supplicant -v')
    entries['init']['data']=init
    stock = PROJECT / 'artifacts/stock-cph2493-August-eu-ota'
    (output / 'Image').write_bytes(gzip.decompress(boot['kernel']))
    (output / 'initramfs').write_bytes((stock / 'unpacked-vendor-boot/vendor_ramdisk00').read_bytes() + pack(entries))
    (output / 'init-source').write_bytes(init)
    runtime = ROOT / 'tools/qemu/noble/root'
    command = [str(runtime / 'usr/bin/qemu-system-aarch64'), '-L', str(runtime / 'usr/share/qemu'), '-no-user-config', '-nodefaults', '-machine', 'virt,gic-version=3', '-accel', 'tcg', '-cpu', 'cortex-a72', '-smp', '2', '-m', '1024', '-display', 'none', '-monitor', 'none', '-serial', 'stdio', '-nic', 'none', '-no-reboot', '-kernel', str(output / 'Image'), '-initrd', str(output / 'initramfs'), '-append', 'console=ttyAMA0 rdinit=/init loglevel=7 panic=0']
    env = dict(os.environ, LD_LIBRARY_PATH=str(runtime / 'usr/lib/x86_64-linux-gnu'), QEMU_MODULE_DIR=str(runtime / 'usr/lib/x86_64-linux-gnu/qemu'), TMPDIR=str(ROOT / 'tools/mtk-tmp'))
    started = time.monotonic()
    try:
        process = subprocess.run(command, env=env, capture_output=True, timeout=60)
        raw = process.stdout + process.stderr
        code, timed_out = process.returncode, False
    except subprocess.TimeoutExpired as error:
        raw = (error.stdout or b'') + (error.stderr or b'')
        code, timed_out = None, True
    (output / 'console.log').write_bytes(raw)
    passed = b'LYNX_VM_DHCP_EXIT=0' in raw and b'LYNX_DHCP_BOUND interface=test0 address=192.0.2.' in raw and code==0 and not timed_out and b'LYNX_SSH_VM_OK' in raw and b'LYNX_VM_SSH_EXIT=0' in raw and b'wpa_supplicant v2.11' in raw and b'iw version' in raw and b'uid=0(root)' in raw and b'LYNX_VM_KEY_FAILED' not in raw
    result=dict(dhcp_hook_sha256=hashlib.sha256(hook).hexdigest(),passed=passed,phone_contacted=False,exit_code=code,timed_out=timed_out,elapsed_seconds=time.monotonic()-started,command=command,network_entries=network_entries,console_sha256=hashlib.sha256(raw).hexdigest(),kernel_sha256=hashlib.sha256(boot['kernel']).hexdigest(),limits='Actual native ARM64 wpa_supplicant/iw startup and key-authenticated Dropbear SSH over loopback under exact stock kernel. DHCP verified over isolated veth pair; no radio or association verified; not a handset image.')
    (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(passed=passed, report=str(output / 'result.json')), indent=2))
    require(passed, 'Native network userspace VM test failed; see console.log')


if __name__ == '__main__':
    main()
