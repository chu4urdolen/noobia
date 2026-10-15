"""Prove selected dynamic trace events reach printk in the exact stock kernel."""
import gzip,hashlib,json,os,subprocess,sys,time
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port'
sys.path.insert(0,str(P))
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
from network_userspace import put
from prepare_busybox_diagnostics import pack
def main():
    image=(P/'artifacts/busybox-ufs-registration-only-v1/nord3-busybox-candidate.img').read_bytes()
    require(hashlib.sha256(image).hexdigest()=='034177798aed0cb0210e51eaf563eefc055abe6fcdbde3d272f89003b1880a56','Reference changed')
    boot=read_boot_v4(image);entries=read_newc(decompress(boot['ramdisk']))
    init=b'''#!/bin/sh
BB=/bin/busybox
export PATH=/bin:/sbin
$BB mount -t proc proc /proc
$BB mount -t sysfs sysfs /sys
$BB mount -t tmpfs tmpfs /dev
$BB mount -t tmpfs tmpfs /run
$BB mknod -m 600 /dev/console c 5 1
$BB mknod -m 666 /dev/null c 1 3
exec >/dev/console 2>&1
$BB mkdir -p /run/trace
$BB mount -t tracefs tracefs /run/trace
printf '%s\n' 'p:lynx_printk/lynx_printk_marker __arm64_sys_getpid' >> /run/trace/kprobe_events
echo "PRINTK_PROBE_ADD=$?"
printf '1\n' > /run/trace/events/lynx_printk/lynx_printk_marker/enable
echo "PRINTK_PROBE_ENABLE=$?"
$BB sh -c 'echo "PRINTK_TRIGGER_PID=$$"'
printf '0\n' > /run/trace/events/lynx_printk/lynx_printk_marker/enable
$BB dmesg > /run/printk.log
echo PRINTK_CAPTURE_BEGIN
$BB cat /run/printk.log
echo PRINTK_CAPTURE_END
$BB poweroff -f
'''
    put(entries,'init',init)
    out=P/'artifacts'/('emulated-native-trace-printk-'+str(time.time_ns()));out.mkdir(mode=0o700)
    (out/'Image').write_bytes(gzip.decompress(boot['kernel']));(out/'initramfs').write_bytes(pack(entries));(out/'init-source').write_bytes(init)
    q=R/'tools/qemu/noble/root'
    command=[str(q/'usr/bin/qemu-system-aarch64'),'-L',str(q/'usr/share/qemu'),'-no-user-config','-nodefaults','-machine','virt,gic-version=3','-accel','tcg','-cpu','cortex-a710','-smp','2','-m','1024','-display','none','-monitor','none','-serial','stdio','-nic','none','-no-reboot','-kernel',str(out/'Image'),'-initrd',str(out/'initramfs'),'-append','console=ttyAMA0 rdinit=/init loglevel=7 panic=0 tp_printk']
    env=dict(os.environ,LD_LIBRARY_PATH=str(q/'usr/lib/x86_64-linux-gnu'),QEMU_MODULE_DIR=str(q/'usr/lib/x86_64-linux-gnu/qemu'),TMPDIR=str(R/'tools/mtk-tmp'))
    result=subprocess.run(command,env=env,capture_output=True,timeout=45);raw=result.stdout+result.stderr
    (out/'console.log').write_bytes(raw)
    capture=raw.split(b'PRINTK_CAPTURE_BEGIN\r\n')[-1].split(b'PRINTK_CAPTURE_END')[0]
    (out/'printk-capture.log').write_bytes(capture)
    checks=dict(probe_added=b'PRINTK_PROBE_ADD=0' in raw,probe_enabled=b'PRINTK_PROBE_ENABLE=0' in raw,event_in_dmesg=b'lynx_printk_marker: (' in capture,poweroff=b'reboot: Power down' in raw,no_exception=not any(x in raw for x in [b'Kernel panic',b'Internal error:',b'CFI failure']))
    report=dict(passed=result.returncode==0 and all(checks.values()),checks=checks,kernel_sha256=hashlib.sha256(boot['kernel']).hexdigest(),phone_contacted=False,command=command,limits='Exact stock kernel proves tp_printk for a known syscall probe in QEMU. Does not prove physical UFS symbol instrumentation, execution or persistence to phone pstore.')
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(report=str(out/'result.json'),**report),indent=2));require(report['passed'],'Native trace printk test failed')
if __name__=='__main__':main()
