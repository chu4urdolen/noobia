"""Prove stock kernel procfs stack access under its actual ARM64 BusyBox."""
import gzip,hashlib,json,os,subprocess,sys,time
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';sys.path.insert(0,str(P))
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
from network_userspace import put
from prepare_busybox_diagnostics import pack
F=P/'artifacts/busybox-wifi-ssh-twostage-v13'
raw=(F/'nord3-busybox-candidate.img').read_bytes();require(hashlib.sha256(raw).hexdigest()=='3b7d7962c8526e01b60f953f5f6b660e10cc6d599f7539d290f03857147165bb','Reference changed')
b=read_boot_v4(raw);e=read_newc(decompress(b['ramdisk']))
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
$BB sleep 30 &
child=$!
$BB sleep 1
$BB timeout 2 $BB head -c 16384 /proc/$child/stack > /run/stack
rc=$?
echo PROC_STACK_EXIT=$rc
$BB cat /run/stack
if [ "$rc" = 0 ] && $BB grep -Eq '(schedule|hrtimer|nanosleep)' /run/stack; then echo NATIVE_PROC_STACK_CONFIRMED; fi
kill "$child"
$BB poweroff -f
'''
put(e,'init',init);out=P/'artifacts'/('emulated-native-proc-stack-'+str(time.time_ns()));out.mkdir(mode=0o700)
(out/'Image').write_bytes(gzip.decompress(b['kernel']));(out/'initramfs').write_bytes(pack(e));(out/'init-source').write_bytes(init)
q=R/'tools/qemu/noble/root';env=dict(os.environ,LD_LIBRARY_PATH=str(q/'usr/lib/x86_64-linux-gnu'),QEMU_MODULE_DIR=str(q/'usr/lib/x86_64-linux-gnu/qemu'),TMPDIR=str(R/'tools/mtk-tmp'))
command=[str(q/'usr/bin/qemu-system-aarch64'),'-L',str(q/'usr/share/qemu'),'-no-user-config','-nodefaults','-machine','virt,gic-version=3','-accel','tcg','-cpu','cortex-a710','-smp','2','-m','1024','-display','none','-monitor','none','-serial','stdio','-nic','none','-no-reboot','-kernel',str(out/'Image'),'-initrd',str(out/'initramfs'),'-append','console=ttyAMA0 rdinit=/init loglevel=7 panic=0']
p=subprocess.run(command,env=env,capture_output=True,timeout=60);console=p.stdout+p.stderr;(out/'console.log').write_bytes(console)
checks={'readable_symbolic_stack':b'NATIVE_PROC_STACK_CONFIRMED' in console,'clean_poweroff':b'reboot: Power down' in console,'no_exception':not any(x in console for x in [b'Kernel panic',b'Internal error:',b'CFI failure'])}
report={'passed':p.returncode==0 and all(checks.values()),'checks':checks,'kernel_sha256':hashlib.sha256(b['kernel']).hexdigest(),'phone_contacted':False,'limits':'Stock kernel and BusyBox; sleeping userspace task in QEMU, not the physical Wi-Fi worker.'}
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(out/'result.json');require(report['passed'],'Native procfs stack access failed')
