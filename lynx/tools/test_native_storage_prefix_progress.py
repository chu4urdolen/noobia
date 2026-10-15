"""Exercise checkpoint runtime in ARM64 BusyBox; fake insmod/reset, real uptime."""
import argparse,gzip,hashlib,json,os,re,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;P=ROOT/'linux-port'
sys.path.insert(0,str(P))
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
from network_userspace import put
from prepare_busybox_diagnostics import pack
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--count',type=int,choices=[40],required=True);args=parser.parse_args()
    F=P/'artifacts'/('busybox-module-progress-debug-'+str(args.count)+'-v1');image=(F/'nord3-busybox-candidate.img').read_bytes()
    require(hashlib.sha256(image).hexdigest()=={0:'465fa84fd647dc04298565db906bcbad3794166d247900bd2246d24702a521d2',28:'9b5e9ff94c5c441e945ebc3bf714b253d2f8bcfbfcc91182b8d9baf54aeab0e4',32:'2468d6b65d4f3cd06927db51b9e077708e363a9ecdd112c568203cc4a3eea6dd',34:'6070a324cbbfc8a1262b94ae111e3a6b3a4cb330e66af54d2363a3e2c5b7edad',40:'18a5250d0617c03a305381b6aa24e37a0f2681463e441f7771a586df4a2ec540'}[args.count],'Candidate changed')
    boot=read_boot_v4(image);entries=read_newc(decompress(boot['ramdisk']))
    source=(P/'lynx-storage-prefix-progress-runtime.sh').read_bytes()
    fixture=source.replace(b'progress_started+90',b'progress_started+10').replace(b'120+2*progress_code',b'20').replace(b'/bin/boot-proof-reboot',b'/bin/progress-reset')
    put(entries,'bin/progress-busybox',b'''#!/bin/sh
if [ "$1" = insmod ]; then
    if [ -f /run/fail-clock ] && [ "$2" = /lib/modules/blocktag.ko ]; then exit 1; fi
    exit 0
fi
exec /bin/busybox "$@"
''')
    put(entries,'bin/progress-reset',b'''#!/bin/sh
echo PROGRESS_NATIVE_FAKE_RESET
exit 1
''')
    init=b'''#!/bin/sh
export PATH=/bin:/sbin
BB=/bin/progress-busybox
$BB mount -t proc proc /proc
$BB mount -t sysfs sysfs /sys
$BB mount -t tmpfs tmpfs /dev
$BB mount -t tmpfs tmpfs /run
$BB mknod -m 600 /dev/console c 5 1
$BB mknod -m 666 /dev/null c 1 3
exec > /dev/console 2>&1
$BB mkdir -p /run/lynx
log() { printf '%s\\n' "$*"; }
. /etc/lynx/diag-stage.sh
'''+fixture+b'''
echo NATIVE_PROGRESS_SUCCESS_BEGIN
lynx_module_progress
printf 'NATIVE_PROGRESS_SUCCESS_EXIT=%s\\n' "$?"
echo NATIVE_SUCCESS_HEX_BEGIN
$BB cat /run/lynx/stages-bootstrap.hex
echo NATIVE_SUCCESS_HEX_END
$BB cat /run/lynx/boot.log
$BB rm /run/lynx/module-progress
$BB touch /run/fail-clock
echo NATIVE_PROGRESS_FAILURE_BEGIN
lynx_module_progress
printf 'NATIVE_PROGRESS_FAILURE_EXIT=%s\\n' "$?"
echo NATIVE_FAILURE_HEX_BEGIN
$BB cat /run/lynx/stages-bootstrap.hex
echo NATIVE_FAILURE_HEX_END
$BB cat /run/lynx/boot.log
$BB poweroff -f
'''
    put(entries,'init',init)
    out=P/'artifacts'/('emulated-native-storage-prefix-progress-'+str(args.count)+'-'+str(time.time_ns()));out.mkdir(mode=0o700)
    (out/'Image').write_bytes(gzip.decompress(boot['kernel']));(out/'initramfs').write_bytes(pack(entries));(out/'init-source').write_bytes(init)
    q=ROOT/'tools/qemu/noble/root'
    command=[str(q/'usr/bin/qemu-system-aarch64'),'-L',str(q/'usr/share/qemu'),'-no-user-config','-nodefaults','-machine','virt,gic-version=3','-accel','tcg','-cpu','cortex-a710','-smp','2','-m','1024','-display','none','-monitor','none','-serial','stdio','-nic','none','-no-reboot','-kernel',str(out/'Image'),'-initrd',str(out/'initramfs'),'-append','console=ttyAMA0 rdinit=/init loglevel=7 panic=0 initcall_debug']
    env=dict(os.environ,LD_LIBRARY_PATH=str(q/'usr/lib/x86_64-linux-gnu'),QEMU_MODULE_DIR=str(q/'usr/lib/x86_64-linux-gnu/qemu'),TMPDIR=str(ROOT/'tools/mtk-tmp'))
    started=time.monotonic()
    try:
        result=subprocess.run(command,env=env,capture_output=True,timeout=60);raw=result.stdout+result.stderr;code=result.returncode
    except subprocess.TimeoutExpired as error:raw=(error.stdout or b'')+(error.stderr or b'');code=None
    (out/'console.log').write_bytes(raw)
    checks={'prefix_success':b'MODULE_PROGRESS_FIELD code=0 target_delay=20' in raw,
            'controller_failure':(('MODULE_PROGRESS_FIELD code='+('120')+' target_delay=20').encode() in raw),
            'success_returns_one':b'NATIVE_PROGRESS_SUCCESS_EXIT=1' in raw,
            'failure_returns_one':b'NATIVE_PROGRESS_FAILURE_EXIT=1' in raw,
            'exactly_two_fake_resets':len(re.findall(rb'^PROGRESS_NATIVE_FAKE_RESET\r?$',raw,re.M))==2,
            'clean_poweroff':b'reboot: Power down' in raw,
            'no_exception':not any(marker in raw for marker in [b'Kernel panic',b'Internal error:',b'CFI failure'])}
    from lynx_decode_stages import decode
    hex_receipts={};token=entries['etc/lynx/session-token']['data'].decode().strip()
    for name in ['SUCCESS','FAILURE']:
        begin=('NATIVE_'+name+'_HEX_BEGIN\r\n').encode();end=('NATIVE_'+name+'_HEX_END').encode()
        capture=raw.split(begin)[-1].split(end)[0] if begin in raw else b''
        decoded=decode(capture,token);hex_receipts[name]=decoded
        (out/(name.lower()+'.hex')).write_bytes(capture)
        checks['native_hex_'+name]=decoded['complete_sequences_and_checksums'] and all(record['stage_hex']=='0x0200' for record in decoded['records'])
    report={'passed':code==0 and all(checks.values()),'checks':checks,'prefix_count':args.count,'hex_receipts':hex_receipts,'source_sha256':hashlib.sha256(source).hexdigest(),'candidate_sha256':hashlib.sha256(image).hexdigest(),'kernel_sha256':hashlib.sha256(boot['kernel']).hexdigest(),'elapsed_seconds':time.monotonic()-started,'phone_contacted':False,'limits':'Real stock kernel/ARM64 BusyBox and uptime, with sample shortened to10s and timer20s; fake insmod/reset. No physical driver binding, hardware reset or native storage proof.'}
    path=out/'result.json';path.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'report':str(path),'passed':report['passed'],'checks':checks},indent=2));require(report['passed'],'Native progress control failed')
if __name__=='__main__':main()
