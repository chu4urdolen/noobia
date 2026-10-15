"""Run every ordered profile decision with stock ARM64 BusyBox and kernel."""
import gzip,hashlib,json,os,subprocess,sys,time
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
P=ROOT/'linux-port';F=P/'artifacts/busybox-binding-profile-v1'
sys.path.insert(0,str(P))
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
from prepare_busybox_diagnostics import pack
from network_userspace import put


def main():
    out=P/'artifacts'/('emulated-native-binding-profile-'+str(time.time_ns()));out.mkdir()
    image=(F/'nord3-busybox-candidate.img').read_bytes()
    require(hashlib.sha256(image).hexdigest()=='571fc62e9b6c4ba99ea3bc4c4c327fb147d405fccac073305ffd978fc101c7b0','Profile image changed')
    boot=read_boot_v4(image);entries=read_newc(decompress(boot['ramdisk']))
    profile=(P/'lynx-binding-profile.sh').read_bytes()
    require(profile in entries['init']['data'],'Compiled profile differs')
    fixture=profile.replace(b'/proc/cmdline',b'/run/profile/cmdline').replace(b'/sys/bus/platform',b'/run/profile/bus/platform').replace(b'/sys/class/regulator',b'/run/profile/regulator')
    init=b'''#!/bin/sh
BB=/bin/busybox
export PATH=/bin:/sbin
$BB mount -t proc proc /proc
$BB mount -t sysfs sysfs /sys
$BB mount -t tmpfs tmpfs /dev
$BB mount -t tmpfs tmpfs /run
$BB mknod -m 600 /dev/console c 5 1
$BB mknod -m 666 /dev/null c 1 3
exec > /dev/console 2>&1
'''+fixture+b'''
for expected in 1 2 3 4 5 6 7; do
    $BB rm -rf /run/profile
    $BB mkdir -p /run/profile/bus/platform/devices /run/profile/bus/platform/drivers
    printf 'rdinit=/init\n' > /run/profile/cmdline
    if [ "$expected" -ge 2 ]; then printf 'rdinit=/init fw_devlink=permissive\n' > /run/profile/cmdline; fi
    if [ "$expected" -ge 3 ]; then $BB mkdir -p /run/profile/bus/platform/drivers/ufshcd-mtk; fi
    if [ "$expected" -ge 4 ]; then
        $BB mkdir -p /run/profile/bus/platform/devices/ufs /run/profile/tree/ufshci@112b0000
        $BB ln -s /run/profile/tree/ufshci@112b0000 /run/profile/bus/platform/devices/ufs/of_node
    fi
    if [ "$expected" -ge 5 ]; then
        $BB mkdir -p /run/profile/bus/platform/devices/reset /run/profile/tree/syscon@10001000/reset-controller /run/profile/bus/platform/drivers/ti-syscon-reset
        $BB ln -s /run/profile/tree/syscon@10001000/reset-controller /run/profile/bus/platform/devices/reset/of_node
        $BB ln -s /run/profile/bus/platform/drivers/ti-syscon-reset /run/profile/bus/platform/devices/reset/driver
    fi
    if [ "$expected" -ge 6 ]; then
        $BB mkdir -p /run/profile/regulator/regulator0
        printf 'MT6363-VEMC\n' > /run/profile/regulator/regulator0/name
        printf '1\n' > /run/profile/bus/platform/devices/ufs/waiting_for_supplier
    fi
    if [ "$expected" = 7 ]; then printf '0\n' > /run/profile/bus/platform/devices/ufs/waiting_for_supplier; fi
    lynx_binding_profile
    printf 'PROFILE_EXPECTED_%s_GOT_%s\n' "$expected" "$?"
done
printf 'notfw_devlink=permissive\n' > /run/profile/cmdline
lynx_binding_profile
printf 'PROFILE_LOOKALIKE_GOT_%s\n' "$?"
echo PROFILE_NATIVE_TEST_FINISHED
$BB poweroff -f
while :; do $BB sleep 60; done
'''
    put(entries,'init',init)
    (out/'Image').write_bytes(gzip.decompress(boot['kernel']));(out/'initramfs').write_bytes(pack(entries));(out/'init-source').write_bytes(init)
    runtime=ROOT/'tools/qemu/noble/root'
    command=[str(runtime/'usr/bin/qemu-system-aarch64'),'-L',str(runtime/'usr/share/qemu'),'-no-user-config','-nodefaults','-machine','virt,gic-version=3','-accel','tcg','-cpu','cortex-a72','-smp','2','-m','1024','-display','none','-monitor','none','-serial','stdio','-nic','none','-no-reboot','-kernel',str(out/'Image'),'-initrd',str(out/'initramfs'),'-append','console=ttyAMA0 rdinit=/init loglevel=7 panic=0']
    env=dict(os.environ,LD_LIBRARY_PATH=str(runtime/'usr/lib/x86_64-linux-gnu'),QEMU_MODULE_DIR=str(runtime/'usr/lib/x86_64-linux-gnu/qemu'),TMPDIR=str(ROOT/'tools/mtk-tmp'))
    started=time.monotonic()
    try:
        result=subprocess.run(command,env=env,capture_output=True,timeout=45);raw=result.stdout+result.stderr;code=result.returncode
    except subprocess.TimeoutExpired as error:raw=(error.stdout or b'')+(error.stderr or b'');code=None
    (out/'console.log').write_bytes(raw)
    checks={str(n):('PROFILE_EXPECTED_'+str(n)+'_GOT_'+str(n)).encode() in raw for n in range(1,8)}
    checks['lookalike_refused']=b'PROFILE_LOOKALIKE_GOT_1' in raw
    passed=code==0 and all(checks.values())
    (out/'result.json').write_text(json.dumps({'passed':passed,'checks':checks,'profile_source_sha256':hashlib.sha256(profile).hexdigest(),'candidate_sha256':hashlib.sha256(image).hexdigest(),'phone_contacted':False,'elapsed_seconds':time.monotonic()-started,'limits':'Real stock-kernel ARM64 profile logic with synthetic read-only sysfs/cmdline fixtures. No physical device binding or timing inference verified.'},indent=2)+'\n')
    print(json.dumps({'passed':passed,'report':str(out/'result.json'),'checks':checks},indent=2));require(passed,'Native profile logic failed')


if __name__=='__main__':main()
