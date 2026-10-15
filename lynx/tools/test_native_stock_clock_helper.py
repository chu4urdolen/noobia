"""Exact helper ABI plus ARM64 guard/refusal fixtures, entirely inside QEMU."""
import gzip,hashlib,json,os,subprocess,sys,time
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';sys.path.insert(0,str(P))
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
from network_userspace import put
from prepare_busybox_diagnostics import pack
from audit_ufs_reset_supplier import fdt_nodes
def main():
    image=(P/'artifacts/busybox-stock-clock-helper-probe-v1/nord3-busybox-candidate.img').read_bytes();require(hashlib.sha256(image).hexdigest()=='b161edddb4a1a6a2e572f16298397f162d14f2d3e888220e58b576c5c4c0fe76','Candidate changed')
    boot=read_boot_v4(image);entries=read_newc(decompress(boot['ramdisk']));helper=(P/'artifacts/stock-cph2493-August-eu-ota/vendor-ramdisk-unpacked/lib/modules/clk-bringup.ko').read_bytes();require(hashlib.sha256(helper).hexdigest()=='4b62b692837be57cc9aab66136dec5d772840c8f572c37c20c59bda979216823','Helper changed');put(entries,'lib/modules/clk-bringup.ko',helper,0o100644)
    clocks=fdt_nodes((P/'artifacts/stock-runtime-dtb-overlay5/stock-merged.dtb').read_bytes())['/clkitg/bring-up']['clocks'];put(entries,'etc/fixture-clocks',clocks,0o100600)
    source=(P/'stock-clock-helper-guard.sh').read_bytes();fixture=source.replace(b'/sys/module/clk_bringup',b'/fixture/already-loaded').replace(b'/sys/bus/platform/devices',b'/fixture/platform').replace(b'/sys/firmware/devicetree/base',b'/fixture/dt').replace(b'/sys/bus/platform/drivers/bring_up',b'/fixture/drivers/bring_up').replace(b'/sys/kernel/debug',b'/fixture/debug').replace(b'/lib/modules/clk-bringup.ko',b'/fixture/helper.ko')
    put(entries,'bin/fixture-clock-busybox',b'''#!/bin/sh
if [ "$1" = insmod ]; then
    [ "$FIXTURE_CASE" != insert-fail ] || exit 1
    [ "$FIXTURE_CASE" != bind-missing ] || exit 0
    /bin/busybox ln -s /fixture/drivers/bring_up /fixture/platform/helper/driver
    exit 0
fi
exec /bin/busybox "$@"
''')
    init=b'''#!/bin/sh
export PATH=/bin:/sbin
BB=/bin/busybox
$BB mount -t proc proc /proc
$BB mount -t sysfs sysfs /sys
$BB mount -t tmpfs tmpfs /dev
$BB mount -t tmpfs tmpfs /run
$BB mknod -m 600 /dev/console c 5 1
$BB mknod -m 666 /dev/null c 1 3
exec >/dev/console 2>&1
$BB mkdir -p /run/lynx
$BB insmod /lib/modules/clk-bringup.ko
echo "STOCK_CLOCK_REAL_LOAD=$?"
[ -d /sys/module/clk_bringup ] && echo STOCK_CLOCK_REAL_MODULE_PRESENT
[ -d /sys/bus/platform/drivers/bring_up ] && echo STOCK_CLOCK_REAL_DRIVER_PRESENT
BB=/bin/fixture-clock-busybox
log() { printf '%s\n' "$*"; }
. /etc/lynx/diag-stage.sh
lynx_diag_init bootstrap
'''+fixture+b'''
fixture_target() {
    $BB mkdir -p /fixture/platform/helper /fixture/dt/clkitg/bring-up /fixture/drivers/bring_up /fixture/debug/clk/bus_aximem_sel
    printf 'mediatek,clk-bring-up\\000' > /fixture/dt/clkitg/bring-up/compatible
    $BB cp /etc/fixture-clocks /fixture/dt/clkitg/bring-up/clocks
    $BB ln -s /fixture/dt/clkitg/bring-up /fixture/platform/helper/of_node
    $BB cp /lib/modules/clk-bringup.ko /fixture/helper.ko
    printf '1\n' >/fixture/debug/clk/bus_aximem_sel/clk_prepare_count
    printf '1\n' >/fixture/debug/clk/bus_aximem_sel/clk_enable_count
}
passed=0
for test in success wrong-compatible wrong-node bad-clocks bound duplicate no-target bad-module already-loaded insert-fail bind-missing zero-enable bad-counter; do
    $BB rm -rf /fixture
    fixture_target
    expected=10
    case "$test" in
      success) expected=0 ;;
      wrong-compatible) printf 'mediatek,clk-post-ao\\000' >/fixture/dt/clkitg/bring-up/compatible ;;
      wrong-node) $BB mv /fixture/dt/clkitg/bring-up /fixture/dt/clkitg/other; $BB rm /fixture/platform/helper/of_node; $BB ln -s /fixture/dt/clkitg/other /fixture/platform/helper/of_node ;;
      bad-clocks) printf 'wrong\n' >/fixture/dt/clkitg/bring-up/clocks ;;
      bound) $BB ln -s /absent /fixture/platform/helper/driver ;;
      duplicate) $BB mkdir /fixture/platform/second; $BB ln -s /fixture/dt/clkitg/bring-up /fixture/platform/second/of_node ;;
      no-target) $BB rm -r /fixture/platform/helper ;;
      bad-module) printf 'wrong\n' >/fixture/helper.ko ;;
      already-loaded) $BB mkdir /fixture/already-loaded ;;
      insert-fail) expected=11 ;;
      bind-missing) expected=12 ;;
      zero-enable) printf '0\n' >/fixture/debug/clk/bus_aximem_sel/clk_enable_count; expected=13 ;;
      bad-counter) printf 'invalid\n' >/fixture/debug/clk/bus_aximem_sel/clk_prepare_count; expected=13 ;;
    esac
    export FIXTURE_CASE=$test
    lynx_stock_clock_helper_load
    status=$?
    [ "$status" = "$expected" ] || { echo "CLOCK_CASE_FAILED $test status=$status expected=$expected"; break; }
    if [ "$expected" = 10 ] && [ -L /fixture/platform/helper/driver ] && [ "$test" != bound ]; then echo "CLOCK_CASE_FAILED $test unexpected-load"; break; fi
    passed=$((passed+1))
    echo "CLOCK_CASE_PASSED $test"
done
echo "CLOCK_CASE_COUNT=$passed"
echo CLOCK_HEX_BEGIN
$BB cat /run/lynx/stages-bootstrap.hex
echo CLOCK_HEX_END
$BB poweroff -f
'''
    put(entries,'init',init)
    out=P/'artifacts'/('emulated-native-stock-clock-helper-'+str(time.time_ns()));out.mkdir(mode=0o700);(out/'Image').write_bytes(gzip.decompress(boot['kernel']));(out/'initramfs').write_bytes(pack(entries));(out/'init-source').write_bytes(init)
    q=R/'tools/qemu/noble/root';command=[str(q/'usr/bin/qemu-system-aarch64'),'-L',str(q/'usr/share/qemu'),'-no-user-config','-nodefaults','-machine','virt,gic-version=3','-accel','tcg','-cpu','cortex-a710','-smp','2','-m','1024','-display','none','-monitor','none','-serial','stdio','-nic','none','-no-reboot','-kernel',str(out/'Image'),'-initrd',str(out/'initramfs'),'-append','console=ttyAMA0 rdinit=/init loglevel=7 panic=0 tp_printk']
    env=dict(os.environ,LD_LIBRARY_PATH=str(q/'usr/lib/x86_64-linux-gnu'),QEMU_MODULE_DIR=str(q/'usr/lib/x86_64-linux-gnu/qemu'),TMPDIR=str(R/'tools/mtk-tmp'))
    result=subprocess.run(command,env=env,capture_output=True,timeout=60);raw=result.stdout+result.stderr;(out/'console.log').write_bytes(raw)
    from lynx_decode_stages import decode
    capture=raw.split(b'CLOCK_HEX_BEGIN\r\n')[-1].split(b'CLOCK_HEX_END')[0];(out/'stages.hex').write_bytes(capture);decoded=decode(capture,entries['etc/lynx/session-token']['data'].decode().strip())
    checks=dict(real_module_loaded=b'STOCK_CLOCK_REAL_LOAD=0' in raw and b'STOCK_CLOCK_REAL_MODULE_PRESENT' in raw and b'STOCK_CLOCK_REAL_DRIVER_PRESENT' in raw,thirteen_cases=b'CLOCK_CASE_COUNT=13' in raw and b'CLOCK_CASE_FAILED' not in raw,valid_own_hex=decoded['complete_sequences_and_checksums'],poweroff=b'reboot: Power down' in raw,no_exception=not any(s in raw for s in [b'Kernel panic',b'Internal error:',b'CFI failure']))
    report=dict(passed=result.returncode==0 and all(checks.values()),checks=checks,candidate_sha256=hashlib.sha256(image).hexdigest(),source_sha256=hashlib.sha256(source).hexdigest(),phone_contacted=False,limits='Exact stock helper initialization/registration in QEMU without MTK matching node, real ARM64 BusyBox guard and framework-counter fixtures. Does not prove physical clock enabling or UFS probe success.')
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(report=str(out/'result.json'),**report),indent=2));require(report['passed'],'Native stock clock helper test failed')
if __name__=='__main__':main()
