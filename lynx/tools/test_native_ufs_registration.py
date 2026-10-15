"""Exact ARM64 BusyBox guard and supervisor, with fixture devices and fake resets."""
import gzip, hashlib, json, os, subprocess, sys, time
from pathlib import Path
R=Path(__file__).resolve().parent.parent; P=R/'linux-port'
sys.path.insert(0,str(P))
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
from network_userspace import put
from prepare_busybox_diagnostics import pack

def main():
    F=P/'artifacts/busybox-ufs-registration-only-v1'
    image=(F/'nord3-busybox-candidate.img').read_bytes()
    require(hashlib.sha256(image).hexdigest()=='034177798aed0cb0210e51eaf563eefc055abe6fcdbde3d272f89003b1880a56','Candidate changed')
    boot=read_boot_v4(image); entries=read_newc(decompress(boot['ramdisk']))
    guard=(P/'ufs-registration-guard.sh').read_bytes()
    fixture_guard=guard.replace(b'/sys/bus/platform/devices',b'/fixture/platform').replace(b'/sys/firmware/devicetree/base',b'/fixture/dt')
    runtime=(P/'lynx-ufs-registration-runtime.sh').read_bytes()
    fixture_runtime=runtime.replace(b'ufs_started+90',b'ufs_started+10').replace(b'120+5*ufs_code',b'12').replace(b'/bin/boot-proof-reboot',b'/bin/fixture-reset')
    put(entries,'bin/fixture-busybox',b'''#!/bin/sh
if [ "$1" = insmod ]; then
    case "$FIXTURE_MODE:$2" in
        fail-base:/lib/modules/blocktag.ko) exit 1 ;;
        fail-ufs:/lib/modules/ufs-mediatek-mod.ko) exit 1 ;;
        pending:/lib/modules/ufs-mediatek-mod.ko) /bin/busybox sleep 20; exit 1 ;;
    esac
    if [ "$2" = /lib/modules/ufs-mediatek-mod.ko ]; then
        [ "$(/bin/busybox cat /fixture/platform/ufs/driver_override)" = lynx-block-ufs-probe ] || exit 1
        echo MAIN_LOAD_GUARDED >> /run/lynx/main-loads
    fi
    exit 0
fi
exec /bin/busybox "$@"
''')
    put(entries,'bin/fixture-reset',b'#!/bin/sh\necho UFS_NATIVE_FAKE_RESET\nexit 1\n')
    init=b'''#!/bin/sh
export PATH=/bin:/sbin
BB=/bin/fixture-busybox
$BB mount -t proc proc /proc
$BB mount -t sysfs sysfs /sys
$BB mount -t tmpfs tmpfs /dev
$BB mount -t tmpfs tmpfs /run
$BB mknod -m 600 /dev/console c 5 1
$BB mknod -m 666 /dev/null c 1 3
exec >/dev/console 2>&1
$BB mkdir -p /run/lynx
log() { printf '%s\n' "$*"; }
. /etc/lynx/diag-stage.sh
'''+fixture_guard+fixture_runtime+b'''
fixture_target() {
    $BB mkdir -p /fixture/platform/ufs /fixture/dt/ufshci@112b0000
    printf 'mediatek,mt8183-ufshci\\000' > /fixture/dt/ufshci@112b0000/compatible
    $BB ln -s /fixture/dt/ufshci@112b0000 /fixture/platform/ufs/of_node
    printf '(null)\n' > /fixture/platform/ufs/driver_override
}
passed=0
for test in valid missing-attr bound wrong-node existing-override duplicate no-target lookalike; do
    $BB rm -rf /fixture
    $BB mkdir -p /fixture/platform /fixture/dt
    expected=74
    case "$test" in
      valid) fixture_target; expected=0 ;;
      missing-attr) fixture_target; $BB rm /fixture/platform/ufs/driver_override ;;
      bound) fixture_target; $BB ln -s /absent /fixture/platform/ufs/driver ;;
      wrong-node) fixture_target; $BB mv /fixture/dt/ufshci@112b0000 /fixture/dt/other; $BB rm /fixture/platform/ufs/of_node; $BB ln -s /fixture/dt/other /fixture/platform/ufs/of_node ;;
      existing-override) fixture_target; printf 'keep\n' >/fixture/platform/ufs/driver_override ;;
      duplicate) fixture_target; $BB mkdir /fixture/platform/second; $BB ln -s /fixture/dt/ufshci@112b0000 /fixture/platform/second/of_node; printf '(null)\n' >/fixture/platform/second/driver_override ;;
      no-target) ;;
      lookalike) fixture_target; printf 'mediatek,mt8183-ufshci-other\\000' >/fixture/dt/ufshci@112b0000/compatible ;;
    esac
    lynx_ufs_registration_guard
    status=$?
    [ "$status" = "$expected" ] || { echo "GUARD_FAILED $test status=$status"; break; }
    good=1
    for attr in /fixture/platform/*/driver_override; do
      [ -f "$attr" ] || continue
      value=$($BB cat "$attr")
      if [ "$expected" = 0 ]; then [ "$value" = lynx-block-ufs-probe ] || good=0
      elif [ "$test" = existing-override ]; then [ "$value" = keep ] || good=0
      else [ "$value" = '(null)' ] || good=0; fi
    done
    [ "$good" = 1 ] || { echo "GUARD_FAILED $test unexpected-write"; break; }
    passed=$((passed+1))
    echo "GUARD_PASSED $test"
done
echo "GUARD_COUNT=$passed"
for mode in success fail-guard fail-base fail-ufs pending; do
    $BB rm -rf /fixture
    $BB rm -f /run/lynx/ufs-registration /run/lynx/stages-bootstrap.hex /run/lynx/stages-bootstrap.state
    fixture_target
    [ "$mode" != fail-guard ] || printf 'keep\n' > /fixture/platform/ufs/driver_override
    export FIXTURE_MODE=$mode
    echo "SUPERVISOR_BEGIN=$mode"
    lynx_ufs_registration
    echo "SUPERVISOR_EXIT=$?"
    $BB cat /run/lynx/boot.log
    echo "HEX_BEGIN=$mode"
    $BB cat /run/lynx/stages-bootstrap.hex
    echo "HEX_END=$mode"
    $BB sleep 13
done
$BB poweroff -f
'''
    put(entries,'init',init)
    out=P/'artifacts'/('emulated-native-ufs-registration-'+str(time.time_ns()));out.mkdir(mode=0o700)
    (out/'Image').write_bytes(gzip.decompress(boot['kernel'])); (out/'initramfs').write_bytes(pack(entries)); (out/'init-source').write_bytes(init)
    q=R/'tools/qemu/noble/root'
    command=[str(q/'usr/bin/qemu-system-aarch64'),'-L',str(q/'usr/share/qemu'),'-no-user-config','-nodefaults','-machine','virt,gic-version=3','-accel','tcg','-cpu','cortex-a710','-smp','2','-m','1024','-display','none','-monitor','none','-serial','stdio','-nic','none','-no-reboot','-kernel',str(out/'Image'),'-initrd',str(out/'initramfs'),'-append','console=ttyAMA0 rdinit=/init loglevel=7 panic=0 initcall_debug']
    env=dict(os.environ,LD_LIBRARY_PATH=str(q/'usr/lib/x86_64-linux-gnu'),QEMU_MODULE_DIR=str(q/'usr/lib/x86_64-linux-gnu/qemu'),TMPDIR=str(R/'tools/mtk-tmp'))
    result=subprocess.run(command,env=env,capture_output=True,timeout=180);raw=result.stdout+result.stderr
    (out/'console.log').write_bytes(raw)
    checks={'eight_guard_cases':b'GUARD_COUNT=8' in raw and b'GUARD_FAILED' not in raw,'five_resets':raw.count(b'UFS_NATIVE_FAKE_RESET')==5,'poweroff':b'reboot: Power down' in raw,'no_exception':not any(x in raw for x in [b'Kernel panic',b'Internal error:',b'CFI failure'])}
    from lynx_decode_stages import decode
    for name,code in [('success',0),('fail-guard',1),('fail-base',4),('fail-ufs',2),('pending',3)]:
        section=raw.split(('SUPERVISOR_BEGIN='+name+'\r\n').encode())[-1].split(b'SUPERVISOR_BEGIN=')[0]
        checks[name]=('UFS_REGISTRATION_FIELD code='+str(code)+' target_delay=12').encode() in section and b'SUPERVISOR_EXIT=1' in section
        capture=section.split(('HEX_BEGIN='+name+'\r\n').encode())[-1].split(('HEX_END='+name).encode())[0]
        (out/(name+'.hex')).write_bytes(capture)
        decoded=decode(capture,entries['etc/lynx/session-token']['data'].decode().strip())
        checks[name+'-hex']=decoded['complete_sequences_and_checksums']
    report=dict(passed=result.returncode==0 and all(checks.values()),checks=checks,candidate_sha256=hashlib.sha256(image).hexdigest(),guard_sha256=hashlib.sha256(guard).hexdigest(),runtime_sha256=hashlib.sha256(runtime).hexdigest(),phone_contacted=False,limits='Real ARM64 BusyBox and stock kernel; fixture matching nodes and fake insmod/reset, shortened timer. Does not prove physical UFS matching or probe safety.')
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(report=str(out/'result.json'),**report),indent=2));require(report['passed'],'Native UFS registration test failed')

if __name__=='__main__':main()
