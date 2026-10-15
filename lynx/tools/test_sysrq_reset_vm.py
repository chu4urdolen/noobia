"""Exercise stock kernel SysRq reset in an isolated ARM64 VM only."""
import gzip,hashlib,json,os,subprocess,sys,time
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';sys.path.insert(0,str(P))
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
from network_userspace import put
from prepare_busybox_diagnostics import pack
image=(P/'artifacts/busybox-module-progress-debug-40-v1/nord3-busybox-candidate.img').read_bytes()
require(hashlib.sha256(image).hexdigest()=='18a5250d0617c03a305381b6aa24e37a0f2681463e441f7771a586df4a2ec540','Reference changed')
boot=read_boot_v4(image);entries=read_newc(decompress(boot['ramdisk']))
init=b'''#!/bin/sh
BB=/bin/busybox
export PATH=/bin:/sbin
$BB mount -t proc proc /proc
$BB mount -t sysfs sysfs /sys
$BB mount -t tmpfs tmpfs /dev
$BB mknod -m 600 /dev/console c 5 1
$BB mknod -m 666 /dev/null c 1 3
exec > /dev/console 2>&1
[ -w /proc/sysrq-trigger ] || { echo SYSRQ_VM_INTERFACE_MISSING; $BB poweroff -f; }
(echo SYSRQ_VM_FAKE_NORMAL_RESET_PENDING; $BB sleep 60) &
$BB sleep 1
echo SYSRQ_VM_REQUESTING_ONE_EMERGENCY_RESET
printf 'b' > /proc/sysrq-trigger
echo SYSRQ_VM_EMERGENCY_RETURNED
$BB poweroff -f
'''
put(entries,'init',init)
out=P/'artifacts'/('emulated-stock-sysrq-reset-'+str(time.time_ns()));out.mkdir(mode=0o700)
(out/'Image').write_bytes(gzip.decompress(boot['kernel']));(out/'initramfs').write_bytes(pack(entries));(out/'init-source').write_bytes(init)
q=R/'tools/qemu/noble/root';cmd=[str(q/'usr/bin/qemu-system-aarch64'),'-L',str(q/'usr/share/qemu'),'-no-user-config','-nodefaults','-machine','virt,gic-version=3','-accel','tcg','-cpu','cortex-a710','-smp','2','-m','1024','-display','none','-monitor','none','-serial','stdio','-nic','none','-no-reboot','-kernel',str(out/'Image'),'-initrd',str(out/'initramfs'),'-append','console=ttyAMA0 rdinit=/init loglevel=7 panic=0']
env=dict(os.environ,LD_LIBRARY_PATH=str(q/'usr/lib/x86_64-linux-gnu'),QEMU_MODULE_DIR=str(q/'usr/lib/x86_64-linux-gnu/qemu'),TMPDIR=str(R/'tools/mtk-tmp'))
try:
    result=subprocess.run(cmd,env=env,capture_output=True,timeout=30);raw=result.stdout+result.stderr;code=result.returncode
except subprocess.TimeoutExpired as e:raw=(e.stdout or b'')+(e.stderr or b'');code=None
(out/'console.log').write_bytes(raw)
checks={'normal_stub_pending':b'SYSRQ_VM_FAKE_NORMAL_RESET_PENDING' in raw,'one_request':raw.count(b'SYSRQ_VM_REQUESTING_ONE_EMERGENCY_RESET')==1,'kernel_reset_handler':b'sysrq: Resetting' in raw,'did_not_return':b'SYSRQ_VM_EMERGENCY_RETURNED' not in raw,'no_exception':not any(s in raw for s in [b'Kernel panic',b'Internal error:',b'CFI failure'])}
report={'passed':code==0 and all(checks.values()),'checks':checks,'exit_code':code,'kernel_sha256':hashlib.sha256(boot['kernel']).hexdigest(),'phone_contacted':False,'hardware_fastboot_destination_proven':False,'limits':'Real stock kernel emergency reset in QEMU, fake pending normal reset. No MediaTek driver binding, real probe hang, reboot-mode preparation or handset destination demonstrated.'}
path=out/'result.json';path.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'report':str(path),**report},indent=2));require(report['passed'],'Stock SysRq VM test failed')
