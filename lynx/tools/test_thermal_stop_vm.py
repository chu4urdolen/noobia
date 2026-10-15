"""Verify detached BusyBox stop timer reaches kernel power-off in an ARM VM."""
import gzip,hashlib,json,os,subprocess,sys,time
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';sys.path.insert(0,str(P))
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
from network_userspace import put
from prepare_busybox_diagnostics import pack
def main():
 source=(P/'thermal-stop.sh').read_bytes();require(source.count(b'sleep 90')==1,'Timer differs');accelerated=source.replace(b'sleep 90',b'sleep 1')
 b=read_boot_v4((P/'artifacts/busybox-wifi-ssh-twostage-v19/nord3-busybox-candidate.img').read_bytes());e=read_newc(decompress(b['ramdisk']));put(e,'fixture/thermal-stop.sh',accelerated)
 init=b'''#!/bin/sh
export PATH=/bin:/sbin
BB=/bin/busybox
$BB mount -t proc proc /proc
$BB mount -t sysfs sysfs /sys
$BB mount -t tmpfs tmpfs /dev
$BB mknod -m 600 /dev/console c 5 1
$BB mknod -m 666 /dev/null c 1 3
$BB mknod -m 600 /dev/kmsg c 1 11
exec >/dev/console 2>&1
# The launcher shell exits; the detached timer must survive its parent.
$BB sh -c '/bin/busybox nohup /bin/busybox sh /fixture/thermal-stop.sh > /fixture/timer.log 2>&1 < /dev/null & echo TIMER_LAUNCHER_EXITED'
while :; do $BB sleep 1; done
'''
 put(e,'init',init);out=P/'artifacts'/('emulated-thermal-stop-'+str(time.time_ns()));out.mkdir(mode=0o700);(out/'init-source').write_bytes(init);(out/'Image').write_bytes(gzip.decompress(b['kernel']));(out/'initramfs').write_bytes(pack(e));q=R/'tools/qemu/noble/root';env=dict(os.environ,LD_LIBRARY_PATH=str(q/'usr/lib/x86_64-linux-gnu'),QEMU_MODULE_DIR=str(q/'usr/lib/x86_64-linux-gnu/qemu'),TMPDIR=str(R/'tools/mtk-tmp'))
 cmd=[str(q/'usr/bin/qemu-system-aarch64'),'-L',str(q/'usr/share/qemu'),'-no-user-config','-nodefaults','-machine','virt,gic-version=3','-accel','tcg','-cpu','cortex-a710','-smp','2','-m','1024','-display','none','-monitor','none','-serial','stdio','-nic','none','-no-reboot','-kernel',str(out/'Image'),'-initrd',str(out/'initramfs'),'-append','console=ttyAMA0 rdinit=/init loglevel=7 panic=0'];timedout=False
 try:p=subprocess.run(cmd,env=env,capture_output=True,timeout=25);console=p.stdout+p.stderr;rc=p.returncode
 except subprocess.TimeoutExpired as ex:console=(ex.stdout or b'')+(ex.stderr or b'');rc=None;timedout=True
 (out/'console.log').write_bytes(console);checks={n:s in console for n,s in {'parent_exited':b'TIMER_LAUNCHER_EXITED','timer_ran':b'LYNX_THERMAL_STOP_REQUESTED','kernel_powerdown':b'reboot: Power down'}.items()};result={'passed':rc==0 and not timedout and all(checks.values()),'checks':checks,'source_sha256':hashlib.sha256(source).hexdigest(),'delay_accelerated_from_90_to_1_seconds':True,'phone_contacted':False,'physical_poweroff_proven':False};(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(out/'result.json');print(json.dumps(result,indent=2));require(result['passed'],'Stop timer check failed')
if __name__=='__main__':main()
