"""Exercise the actual payload reader on a real loop block device in stock-kernel QEMU."""
import gzip,hashlib,json,os,subprocess,sys,time
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';sys.path.insert(0,str(P))
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
from network_userspace import put
from prepare_busybox_diagnostics import pack
SHA='e24e21797997312ec21bae8f07256a3cf17411462ac6c30518543fbb2677dcab'
def main():
    raw=(P/'artifacts/busybox-wifi-ssh-twostage-v17/nord3-busybox-candidate.img').read_bytes();require(hashlib.sha256(raw).hexdigest()==SHA,'Reference changed')
    boot=read_boot_v4(raw);entries=read_newc(decompress(boot['ramdisk']))
    original=entries['init']['data'];start=original.index(b'lynx_payload_step() {');end=original.index(b'lynx_wifi_bootstrap_child_unlogged() {',start)
    source=original[start:end];fixture=source.replace(b'/sys/class/block',b'/fixture/block')
    put(entries,'fixture',b'',0o40700);put(entries,'fixture/block',b'',0o40700);put(entries,'fixture/block/loop0',b'',0o40700)
    put(entries,'fixture/block/loop0/uevent',b'PARTNAME=boot_a\nDEVNAME=loop0\n',0o100600)
    put(entries,'fixture/boot.img',raw,0o100600)
    put(entries,'bin/payload-busybox',b'#!/bin/sh\ncase "$LYNX_PAYLOAD_FAIL:$1:$2" in\n    3:blockdev:--getsize64) echo 0; exit 0 ;;\n    4:blockdev:--setro|6:dd:*|7:sha256sum:*|8:gzip:*|9:cpio:*) exit 1 ;;\nesac\nexec /bin/busybox "$@"\n')
    init=b'#!/bin/sh\nexport PATH=/bin:/sbin:/usr/bin:/usr/sbin\nBB=/bin/payload-busybox\nstop() { echo PAYLOAD_VM_SETUP_FAILED; $BB poweroff -f; }\n$BB mount -t proc proc /proc || stop\n$BB mount -t sysfs sysfs /sys || stop\n$BB mount -t tmpfs tmpfs /dev || stop\n$BB mount -t tmpfs -o size=128m tmpfs /run || stop\n$BB mknod -m 600 /dev/console c 5 1\n$BB mknod -m 666 /dev/null c 1 3\n$BB mknod -m 600 /dev/loop0 b 7 0\nexec > /dev/console 2>&1\n$BB mkdir -p /run/lynx\nlog() { case "$LYNX_PAYLOAD_FAIL:$1" in 10:BOOT_A_SUPPLEMENT_VERIFIED_AND_EXTRACTED*) return 1 ;; esac; printf \'%s\\n\' "$*"; }\necho PAYLOAD_VM_SETUP_BEGIN\n$BB losetup /dev/loop0 /fixture/boot.img || stop\nprintf \'PAYLOAD_VM_BYTES=%s\\n\' "$($BB blockdev --getsize64 /dev/loop0)"\n'+fixture+b'\necho PAYLOAD_VM_READER_BEGIN\nlynx_read_own_boot_payload\nresult=$?\nprintf \'PAYLOAD_VM_READER_EXIT=%s\\n\' "$result"\nprintf \'PAYLOAD_VM_BLOCK_READONLY=%s\\n\' "$($BB blockdev --getro /dev/loop0)"\nif [ -x /usr/sbin/dropbear ] && [ -x /sbin/wpa_supplicant ] && [ -f /lib/modules/wlan_drv_gen4m_6983.ko ]; then echo PAYLOAD_VM_FILES_PRESENT; fi\nif [ -L /odm/etc ] && [ -f /odm/etc/wifi/wifi.cfg ] && [ -f /vendor/odm/etc/wifi/wifi.cfg ]; then echo PAYLOAD_VM_ODM_ALIAS_RESOLVED; fi\nif [ -d /vendor/firmware ] && [ ! -L /vendor/firmware ] && $BB cmp /lib/firmware/WIFI_RAM_CODE_soc7_0_1_1.bin /vendor/firmware/WIFI_RAM_CODE_soc7_0_1_1.bin; then echo PAYLOAD_VM_FIRMWARE_DIRECTORY_PRESERVED; fi\n$BB df -k /run\noriginal_bytes=$($BB cat /etc/lynx/payload-bytes)\nfor phase in 1 2 3 4 5 6 7 8 9 10; do\n    export LYNX_PAYLOAD_FAIL=$phase\n    if [ "$phase" = 1 ]; then $BB mv /fixture/block/loop0/uevent /fixture/block/loop0/saved; fi\n    if [ "$phase" = 2 ]; then $BB mv /dev/loop0 /dev/loop.saved; fi\n    if [ "$phase" = 5 ]; then echo bad > /etc/lynx/payload-bytes; fi\n    echo "PAYLOAD_FAULT_PHASE=$phase"\n    lynx_read_own_boot_payload\n    rc=$?\n    read -r observed < /run/lynx/payload-step\n    echo "PAYLOAD_FAULT_RESULT=$rc STEP=$observed"\n    if [ "$phase" = 1 ]; then $BB mv /fixture/block/loop0/saved /fixture/block/loop0/uevent; fi\n    if [ "$phase" = 2 ]; then $BB mv /dev/loop.saved /dev/loop0; fi\n    printf \'%s\\n\' "$original_bytes" > /etc/lynx/payload-bytes\ndone\nunset LYNX_PAYLOAD_FAIL\n$BB poweroff -f\n'
    put(entries,'init',init)
    out=P/'artifacts'/('emulated-native-vendor-wifi-v17-loop-'+str(time.time_ns()));out.mkdir(mode=0o700)
    (out/'Image').write_bytes(gzip.decompress(boot['kernel']));(out/'initramfs').write_bytes((P/'artifacts/stock-cph2493-August-eu-ota/unpacked-vendor-boot/vendor_ramdisk00').read_bytes()+pack(entries));(out/'init-source').write_bytes(init)
    q=R/'tools/qemu/noble/root';env=dict(os.environ,LD_LIBRARY_PATH=str(q/'usr/lib/x86_64-linux-gnu'),QEMU_MODULE_DIR=str(q/'usr/lib/x86_64-linux-gnu/qemu'),TMPDIR=str(R/'tools/mtk-tmp'))
    command=[str(q/'usr/bin/qemu-system-aarch64'),'-L',str(q/'usr/share/qemu'),'-no-user-config','-nodefaults','-machine','virt,gic-version=3','-accel','tcg','-cpu','cortex-a710','-smp','2','-m','2048','-display','none','-monitor','none','-serial','stdio','-nic','none','-no-reboot','-kernel',str(out/'Image'),'-initrd',str(out/'initramfs'),'-append','console=ttyAMA0 rdinit=/init loglevel=7 panic=0']
    try:
        result=subprocess.run(command,env=env,capture_output=True,timeout=120);console=result.stdout+result.stderr;code=result.returncode
    except subprocess.TimeoutExpired as error:console=(error.stdout or b'')+(error.stderr or b'');code=None
    (out/'console.log').write_bytes(console)
    checks={'odm_alias_resolved':b'PAYLOAD_VM_ODM_ALIAS_RESOLVED' in console,'firmware_directory_preserved':b'PAYLOAD_VM_FIRMWARE_DIRECTORY_PRESERVED' in console,'real_loop_64MiB':b'PAYLOAD_VM_BYTES=67108864' in console,'payload_read_and_extracted':b'PAYLOAD_VM_READER_EXIT=0' in console and b'BOOT_A_SUPPLEMENT_VERIFIED_AND_EXTRACTED' in console,'block_stayed_readonly':b'PAYLOAD_VM_BLOCK_READONLY=1' in console,'files_present':b'PAYLOAD_VM_FILES_PRESENT' in console,'clean_poweroff':b'reboot: Power down' in console,'no_exception':not any(x in console for x in [b'Kernel panic',b'Internal error:',b'CFI failure'])}
    for phase in range(1,11):
        section=console.split(('PAYLOAD_FAULT_PHASE='+str(phase)+'\r\n').encode())[-1].split(b'PAYLOAD_FAULT_PHASE=')[0]
        checks['fault_'+str(phase)]=('PAYLOAD_FAULT_RESULT=1 STEP='+str(phase)).encode() in section
    report={'passed':code==0 and all(checks.values()),'checks':checks,'candidate_sha256':SHA,'payload_reader_sha256':hashlib.sha256(source).hexdigest(),'exit_code':code,'phone_contacted':False,'limits':'Stock kernel/real ARM64 BusyBox/real loop block I/O; partition metadata is fixture. Does not prove physical UFS reads.'}
    path=out/'result.json';path.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'receipt':str(path),**report},indent=2));require(report['passed'],'Native payload test failed; inspect saved console')
if __name__=='__main__':main()
