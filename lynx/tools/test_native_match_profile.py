"""Run the live matching checks in exact-stock-kernel ARM64 fixtures."""
import gzip,hashlib,json,os,subprocess,sys,time
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent;P=ROOT/'linux-port';F=P/'artifacts/busybox-match-profile-v1'
sys.path.insert(0,str(P))
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
from prepare_busybox_diagnostics import pack
from network_userspace import put


def main():
    out=P/'artifacts'/('emulated-native-match-profile-'+str(time.time_ns()));out.mkdir()
    image=(F/'nord3-busybox-candidate.img').read_bytes();manifest=json.loads((F/'build-validation.json').read_text())
    require(hashlib.sha256(image).hexdigest()==manifest['candidate_sha256'],'Profile image changed')
    boot=read_boot_v4(image);entries=read_newc(decompress(boot['ramdisk']))
    profile=(P/'lynx-match-profile.sh').read_bytes();require(profile in entries['init']['data'],'Compiled profile differs')
    fixture=profile.replace(b'/sys/bus/platform',b'/run/profile/bus/platform').replace(b'/sys/kernel/debug',b'/run/profile/debug')
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
$BB mkdir -p /run/lynx
'''+fixture+b'''
for scenario in 1 2 3 4 5 6 7 null multi other-bound lookalike unreadable-autoprobe missing-override; do
    $BB rm -rf /run/profile
    $BB mkdir -p /run/profile/bus/platform/drivers/ufshcd-mtk /run/profile/bus/platform/devices/112b0000.ufshci /run/profile/tree/ufshci@112b0000 /run/profile/debug
    match_fixture=/run/profile/bus/platform/devices/112b0000.ufshci
    $BB ln -s /run/profile/tree/ufshci@112b0000 "$match_fixture/of_node"
    printf '\\n' > "$match_fixture/driver_override"
    printf 'mediatek,mt8183-ufshci\\000' > "$match_fixture/of_node/compatible"
    printf '1\\n' > /run/profile/bus/platform/drivers_autoprobe
    printf 'unrelated\\tsupplier missing\\n' > /run/profile/debug/devices_deferred
    expected=$scenario
    case "$scenario" in
        1) $BB rmdir /run/profile/bus/platform/drivers/ufshcd-mtk ;;
        2) $BB ln -s /run/profile/bus/platform/drivers/ufshcd-mtk "$match_fixture/driver" ;;
        3) printf 'wrong-driver\\n' > "$match_fixture/driver_override" ;;
        4) printf 'mediatek,wrong-ufshci\\000' > "$match_fixture/of_node/compatible" ;;
        5) printf '0\\n' > /run/profile/bus/platform/drivers_autoprobe ;;
        6) printf '112b0000.ufshci\\tsupplier unavailable\\n' > /run/profile/debug/devices_deferred ;;
        7) ;;
        null) expected=7; printf '(null)\\n' > "$match_fixture/driver_override" ;;
        multi) expected=7; printf 'vendor,other\\000mediatek,mt8183-ufshci\\000' > "$match_fixture/of_node/compatible" ;;
        other-bound) expected=3; $BB ln -s /run/profile/bus/platform/drivers/other-driver "$match_fixture/driver" ;;
        lookalike) expected=4; printf 'mediatek,mt8183-ufshci-lookalike\\000' > "$match_fixture/of_node/compatible" ;;
        unreadable-autoprobe) expected=1; $BB rm /run/profile/bus/platform/drivers_autoprobe ;;
        missing-override) expected=1; $BB rm "$match_fixture/driver_override" ;;
    esac
    lynx_match_profile
    printf 'MATCH_CASE_%s_EXPECTED_%s_GOT_%s\\n' "$scenario" "$expected" "$?"
done
echo MATCH_TEST_FINISHED
$BB poweroff -f
while :; do $BB sleep 60; done
'''
    put(entries,'init',init)
    (out/'Image').write_bytes(gzip.decompress(boot['kernel']));(out/'initramfs').write_bytes(pack(entries));(out/'init-source').write_bytes(init)
    runtime=ROOT/'tools/qemu/noble/root'
    command=[str(runtime/'usr/bin/qemu-system-aarch64'),'-L',str(runtime/'usr/share/qemu'),'-no-user-config','-nodefaults','-machine','virt,gic-version=3','-accel','tcg','-cpu','cortex-a710','-smp','2','-m','1024','-display','none','-monitor','none','-serial','stdio','-nic','none','-no-reboot','-kernel',str(out/'Image'),'-initrd',str(out/'initramfs'),'-append','console=ttyAMA0 rdinit=/init loglevel=7 panic=0']
    env=dict(os.environ,LD_LIBRARY_PATH=str(runtime/'usr/lib/x86_64-linux-gnu'),QEMU_MODULE_DIR=str(runtime/'usr/lib/x86_64-linux-gnu/qemu'),TMPDIR=str(ROOT/'tools/mtk-tmp'))
    started=time.monotonic()
    try:
        result=subprocess.run(command,env=env,capture_output=True,timeout=45);raw=result.stdout+result.stderr;code=result.returncode
    except subprocess.TimeoutExpired as error:raw=(error.stdout or b'')+(error.stderr or b'');code=None
    (out/'console.log').write_bytes(raw)
    cases={str(n):n for n in range(1,8)};cases.update(null=7,multi=7,**{'other-bound':3,'lookalike':4,'unreadable-autoprobe':1,'missing-override':1})
    checks={name:(f'MATCH_CASE_{name}_EXPECTED_{n}_GOT_{n}').encode() in raw for name,n in cases.items()}
    checks['clean_poweroff']=b'reboot: Power down' in raw;checks['no_kernel_exception']=not any(x in raw for x in [b'Kernel panic',b'Internal error:',b'CFI failure'])
    passed=code==0 and all(checks.values())
    report={'passed':passed,'checks':checks,'profile_source_sha256':hashlib.sha256(profile).hexdigest(),'candidate_sha256':hashlib.sha256(image).hexdigest(),'phone_contacted':False,'elapsed_seconds':time.monotonic()-started,'limits':'ARM64 read-only live-profile logic with synthetic sysfs/debugfs. No physical device matching demonstrated.'}
    path=out/'result.json';path.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'passed':passed,'report':str(path),'checks':checks},indent=2));require(passed,'Native matching profile failed')


if __name__=='__main__':main()
