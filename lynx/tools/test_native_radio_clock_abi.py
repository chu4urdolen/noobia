"""Exercise the actual payload reader on a real loop block device in stock-kernel QEMU."""
import gzip,hashlib,json,os,subprocess,sys,time
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';sys.path.insert(0,str(P))
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
from network_userspace import put
from prepare_busybox_diagnostics import pack
SHA='1e51aeff4eae67f50c5bce85986d7f423a14c6274332b99d2e64015288f8b73b'
def main():
    raw=(P/'artifacts/busybox-wifi-ssh-twostage-v12/nord3-busybox-candidate.img').read_bytes();require(hashlib.sha256(raw).hexdigest()==SHA,'Reference changed')
    boot=read_boot_v4(raw);entries=read_newc(decompress(boot['ramdisk']))
    original=entries['init']['data'];start=original.index(b'lynx_read_own_boot_payload() {');end=original.index(b'lynx_wifi_bootstrap_child_unlogged() {',start)
    source=original[start:end];fixture=source.replace(b'/sys/class/block',b'/fixture/block')
    put(entries,'fixture',b'',0o40700);put(entries,'fixture/block',b'',0o40700);put(entries,'fixture/block/loop0',b'',0o40700)
    put(entries,'fixture/block/loop0/uevent',b'PARTNAME=boot_a\nDEVNAME=loop0\n',0o100600)
    put(entries,'fixture/boot.img',raw,0o100600)
    init=b'#!/bin/sh\nexport PATH=/bin:/sbin\nBB=/bin/busybox\n$BB mount -t proc proc /proc\n$BB mount -t sysfs sysfs /sys\n$BB mount -t tmpfs tmpfs /dev\n$BB mknod -m 600 /dev/console c 5 1\n$BB mknod -m 666 /dev/null c 1 3\nexec > /dev/console 2>&1\nfor module in regmap-spmi mt6685-core clkbuf; do\n    $BB insmod "/lib/modules/$module.ko"\n    printf \'RADIO_CLOCK_ABI module=%s exit=%s\\n\' "$module" "$?"\ndone\nif [ -d /sys/module/regmap_spmi ] && [ -d /sys/module/mt6685_core ] && [ -d /sys/module/clkbuf ]; then echo RADIO_CLOCK_ABI_MODULES_PRESENT; fi\n$BB poweroff -f\n'
    put(entries,'init',init)
    out=P/'artifacts'/('emulated-radio-clock-abi-'+str(time.time_ns()));out.mkdir(mode=0o700)
    (out/'Image').write_bytes(gzip.decompress(boot['kernel']));(out/'initramfs').write_bytes((P/'artifacts/stock-cph2493-August-eu-ota/unpacked-vendor-boot/vendor_ramdisk00').read_bytes()+pack(entries));(out/'init-source').write_bytes(init)
    q=R/'tools/qemu/noble/root';env=dict(os.environ,LD_LIBRARY_PATH=str(q/'usr/lib/x86_64-linux-gnu'),QEMU_MODULE_DIR=str(q/'usr/lib/x86_64-linux-gnu/qemu'),TMPDIR=str(R/'tools/mtk-tmp'))
    command=[str(q/'usr/bin/qemu-system-aarch64'),'-L',str(q/'usr/share/qemu'),'-no-user-config','-nodefaults','-machine','virt,gic-version=3','-accel','tcg','-cpu','cortex-a710','-smp','2','-m','2048','-display','none','-monitor','none','-serial','stdio','-nic','none','-no-reboot','-kernel',str(out/'Image'),'-initrd',str(out/'initramfs'),'-append','console=ttyAMA0 rdinit=/init loglevel=7 panic=0']
    try:
        result=subprocess.run(command,env=env,capture_output=True,timeout=120);console=result.stdout+result.stderr;code=result.returncode
    except subprocess.TimeoutExpired as error:console=(error.stdout or b'')+(error.stderr or b'');code=None
    (out/'console.log').write_bytes(console)
    checks={name:('RADIO_CLOCK_ABI module='+name+' exit=0').encode() in console for name in ['regmap-spmi','mt6685-core','clkbuf']}
    checks['modules_present']=b'RADIO_CLOCK_ABI_MODULES_PRESENT' in console
    checks['clean_poweroff']=b'reboot: Power down' in console
    checks['no_exception']=not any(x in console for x in [b'Kernel panic',b'Internal error:',b'CFI failure',b'Unknown symbol'])
    report={'passed':code==0 and all(checks.values()),'checks':checks,'candidate_sha256':SHA,'payload_reader_sha256':hashlib.sha256(source).hexdigest(),'exit_code':code,'phone_contacted':False,'limits':'Stock kernel/ARM64 BusyBox and actual stock supplier module initialization; virtual machine has no matching MTK peripheral nodes. Does not prove physical binding or hardware clock outputs.'}
    path=out/'result.json';path.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'receipt':str(path),**report},indent=2));require(report['passed'],'Native payload test failed; inspect saved console')
if __name__=='__main__':main()
