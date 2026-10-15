"""Check actual BusyBox firmware hooks/help and netlink daemon under stock kernel."""
import gzip,hashlib,json,os,subprocess,sys,time
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';sys.path.insert(0,str(P))
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
from network_userspace import put
from prepare_busybox_diagnostics import pack
b=read_boot_v4((P/'artifacts/busybox-wifi-ssh-twostage-v15/nord3-busybox-candidate.img').read_bytes());e=read_newc(decompress(b['ramdisk']));bb=e['bin/busybox']['data']
init=b'''#!/bin/sh
export PATH=/bin:/sbin
BB=/bin/busybox
$BB mount -t proc proc /proc
$BB mount -t sysfs sysfs /sys
$BB mount -t tmpfs tmpfs /dev
$BB mount -t tmpfs tmpfs /run
$BB mknod -m 600 /dev/console c 5 1
$BB mknod -m 666 /dev/null c 1 3
exec > /dev/console 2>&1
$BB mdev --help
$BB mdev -df -v > /run/mdev.log 2>&1 &
daemon=$!
$BB sleep 1
if kill -0 "$daemon"; then echo NATIVE_MDEV_DAEMON_ALIVE; kill "$daemon"; wait "$daemon"; fi
$BB cat /run/mdev.log
$BB poweroff -f
'''
put(e,'init',init);out=P/'artifacts'/('emulated-native-mdev-daemon-'+str(time.time_ns()));out.mkdir(mode=0o700);(out/'Image').write_bytes(gzip.decompress(b['kernel']));(out/'initramfs').write_bytes(pack(e));(out/'init-source').write_bytes(init)
q=R/'tools/qemu/noble/root';env=dict(os.environ,LD_LIBRARY_PATH=str(q/'usr/lib/x86_64-linux-gnu'),QEMU_MODULE_DIR=str(q/'usr/lib/x86_64-linux-gnu/qemu'),TMPDIR=str(R/'tools/mtk-tmp'))
command=[str(q/'usr/bin/qemu-system-aarch64'),'-L',str(q/'usr/share/qemu'),'-no-user-config','-nodefaults','-machine','virt,gic-version=3','-accel','tcg','-cpu','cortex-a710','-smp','2','-m','1024','-display','none','-monitor','none','-serial','stdio','-nic','none','-no-reboot','-kernel',str(out/'Image'),'-initrd',str(out/'initramfs'),'-append','console=ttyAMA0 rdinit=/init loglevel=7 panic=0']
p=subprocess.run(command,env=env,capture_output=True,timeout=60);console=p.stdout+p.stderr;(out/'console.log').write_bytes(console)
checks={'daemon_alive':b'NATIVE_MDEV_DAEMON_ALIVE' in console,'netlink_help':b'netlink' in console.lower() or b'daemon' in console.lower(),'firmware_path_literal':b'/lib/firmware' in bb,'firmware_event_literal':b'FIRMWARE' in bb,'clean_poweroff':b'reboot: Power down' in console,'no_exception':not any(s in console for s in [b'Kernel panic',b'Internal error:',b'CFI failure'])}
report={'passed':p.returncode==0 and all(checks.values()),'checks':checks,'busybox_sha256':hashlib.sha256(bb).hexdigest(),'kernel_sha256':hashlib.sha256(b['kernel']).hexdigest(),'phone_contacted':False,'limits':'Actual stock ARM kernel/BusyBox daemon, no simulated firmware request or physical Wi-Fi. Literal presence alone does not prove all firmware-loader paths.'}
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(out/'result.json');require(report['passed'],'mdev capability/daemon checks failed')
