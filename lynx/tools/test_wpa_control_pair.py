"""Exercise the exact embedded WPA client/server under the stock ARM kernel.

No NIC, handset contact, or real credentials. Preserve complete console output.
"""
import gzip,json,os,subprocess,sys,time,hashlib
from pathlib import Path
R=Path(__file__).resolve().parent.parent; P=R/'linux-port'
sys.path.insert(0,str(P))
from image_formats import read_boot_v4,read_newc
from ramdisk_codec import decompress
from network_userspace import put
from prepare_busybox_diagnostics import pack
F=P/'artifacts/busybox-wifi-ssh-twostage-v18'
out=P/'artifacts'/('emulated-wpa-control-pair-'+str(time.time_ns()));out.mkdir(mode=0o700)
b=read_boot_v4((F/'nord3-busybox-candidate.img').read_bytes())
e=read_newc(decompress(b['ramdisk']))
x=read_newc(gzip.decompress((F/'supplement.cpio.gz').read_bytes()))
for name,entry in x.items():
 if name in ['sbin/wpa_supplicant','sbin/wpa_cli'] or name in ['lib','usr','usr/lib'] or name.startswith(('lib/','usr/lib/')):e[name]=entry
put(e,'etc/wpa-test.conf',b'ctrl_interface=/run/wpa_supplicant\nap_scan=0\n',0o100600)
put(e,'etc/wpa-launch.sh',(P/'wpa-launch.sh').read_bytes(),0o100644)
init=b'''#!/bin/sh
export PATH=/bin:/sbin
BB=/bin/busybox
$BB mount -t proc proc /proc
$BB mount -t sysfs sysfs /sys
$BB mount -t tmpfs tmpfs /dev
$BB mknod -m 600 /dev/console c 5 1
$BB mknod -m 666 /dev/null c 1 3
exec >/dev/console 2>&1
$BB mdev -s
$BB mount -t tmpfs tmpfs /run
$BB mkdir -p /run/wpa_supplicant /run/lynx
echo PAIR_RUNTIME
$BB ls -ld /tmp /dev/urandom /run/wpa_supplicant
/sbin/wpa_supplicant -h
/sbin/wpa_cli -v
$BB ip link set lo up
for driver in wired; do
 echo PAIR_DRIVER=$driver
 . /etc/wpa-launch.sh
 lynx_start_supplicant lo "$driver" /etc/wpa-test.conf
 echo PAIR_START_RC=$?
 $BB sleep 1
 $BB timeout 3 /sbin/wpa_cli -p /run/wpa_supplicant -i lo status
 echo PAIR_STATUS_RC=$?
 $BB timeout 3 /sbin/wpa_cli -p /run/wpa_supplicant -i lo ping
 echo PAIR_PING_RC=$?
 $BB ls -la /run/wpa_supplicant /tmp
 $BB ps
 $BB cat /run/lynx/wpa.log
 $BB timeout 3 /sbin/wpa_cli -p /run/wpa_supplicant -i lo terminate
 $BB sleep 1
done
wait "$lynx_wpa_pid"
lynx_start_supplicant lo unsupported-driver /etc/wpa-test.conf
if [ "$?" != 0 ]; then echo PAIR_BAD_DRIVER_REFUSED; fi
if [ -s /run/lynx/wpa.log ]; then echo PAIR_LOG_CAPTURED; fi
echo PAIR_DONE
$BB poweroff -f
'''
put(e,'init',init);(out/'init-source').write_bytes(init)
(out/'Image').write_bytes(gzip.decompress(b['kernel']));(out/'initramfs').write_bytes(pack(e))
q=R/'tools/qemu/noble/root'
env=dict(os.environ,LD_LIBRARY_PATH=str(q/'usr/lib/x86_64-linux-gnu'),QEMU_MODULE_DIR=str(q/'usr/lib/x86_64-linux-gnu/qemu'),TMPDIR=str(R/'tools/mtk-tmp'))
cmd=[str(q/'usr/bin/qemu-system-aarch64'),'-L',str(q/'usr/share/qemu'),'-no-user-config','-nodefaults','-machine','virt,gic-version=3','-accel','tcg','-cpu','cortex-a710','-smp','2','-m','1024','-display','none','-monitor','none','-serial','stdio','-nic','none','-no-reboot','-kernel',str(out/'Image'),'-initrd',str(out/'initramfs'),'-append','console=ttyAMA0 rdinit=/init loglevel=7 panic=0']
started=time.time();timedout=False
try:
 p=subprocess.run(cmd,env=env,capture_output=True,timeout=55);console=p.stdout+p.stderr;rc=p.returncode
except subprocess.TimeoutExpired as ex:
 console=(ex.stdout or b'')+(ex.stderr or b'');rc=None;timedout=True
(out/'console.log').write_bytes(console)
report={'elapsed_seconds':time.time()-started,'returncode':rc,'timed_out':timedout,'completed':b'PAIR_DONE' in console,'control_pong':b'PONG' in console,'status_reply':b'wpa_state=' in console,'launch_success':b'PAIR_START_RC=0' in console,'bad_driver_refused':b'PAIR_BAD_DRIVER_REFUSED' in console,'log_captured':b'PAIR_LOG_CAPTURED' in console,'launch_source_sha256':hashlib.sha256((P/'wpa-launch.sh').read_bytes()).hexdigest(),'phone_contacted':False,'network_attached':False,'binary_sha256':{n:hashlib.sha256(e[n]['data']).hexdigest() for n in ['sbin/wpa_supplicant','sbin/wpa_cli']},'limits':'Loopback wired driver only; no physical Wi-Fi proof.'}
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(out/'result.json');print(json.dumps(report,indent=2))
