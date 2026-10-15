"""Actual timing shell under stock kernel/ARM64 BusyBox; clock/reset fixtures."""
import gzip,hashlib,json,os,re,subprocess,sys,time
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';sys.path.insert(0,str(P))
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
from network_userspace import put
from prepare_busybox_diagnostics import pack
SHA='e24e21797997312ec21bae8f07256a3cf17411462ac6c30518543fbb2677dcab'
def main():
    F=P/'artifacts/busybox-wifi-ssh-twostage-v17';raw=(F/'nord3-busybox-candidate.img').read_bytes();require(hashlib.sha256(raw).hexdigest()==SHA,'Image changed')
    boot=read_boot_v4(raw);entries=read_newc(decompress(boot['ramdisk']));source=entries['bin/boot-proof-reboot']['data']
    extra=read_newc(gzip.decompress((F/'supplement.cpio.gz').read_bytes()))
    put(entries,'etc/lynx/power-stack-parser.sh',extra['etc/lynx/power-stack-parser.sh']['data'],0o100644)
    fixture=source.split(b'\nlynx_network_timing_reboot\n')[0].replace(b'/proc/uptime',b'/fixture/uptime').replace(b'/bin/boot-proof-reboot-native',b'/bin/timing-reset').replace(b'BB=/bin/busybox',b'BB=/bin/timing-busybox')
    put(entries,'fixture',b'',0o40700)
    put(entries,'bin/timing-busybox',b'''#!/bin/sh
if [ "$1" = sleep ]; then
    read -r target < /fixture/target || exit 1
    printf '%s.00 0\\n' "$target" > /fixture/uptime
    exit 0
fi
exec /bin/busybox "$@"
''')
    put(entries,'bin/timing-reset',b'''#!/bin/sh
echo NATIVE_TIMING_RESET
exit 1
''')
    init=b'#!/bin/sh\nexport PATH=/bin:/sbin\nBB=/bin/busybox\n$BB mount -t proc proc /proc\n$BB mount -t sysfs sysfs /sys\n$BB mount -t tmpfs tmpfs /dev\n$BB mount -t tmpfs tmpfs /run\n$BB mknod -m 600 /dev/console c 5 1\n$BB mknod -m 600 /dev/kmsg c 1 11\nexec > /dev/console 2>&1\n$BB mkdir -p /run/lynx\n'+fixture+b'\nfor code in $(/bin/busybox seq 0 49); do\n    case "$code" in 9|35) continue ;; esac\n    printf \'10\\n\' > /run/lynx/network-timing-start\n    printf \'30.00 0\\n\' > /fixture/uptime\n    printf \'%s\\n\' "$((10+80+5*code))" > /fixture/target\n    /bin/busybox rm -f /run/lynx/bootstrap-result /run/lynx/worker-result /run/lynx/station-result /run/lynx/station-dmesg /run/lynx/radio-clock-result /run/lynx/wifi-worker-stack-result /run/lynx/wifi-worker-stack\n    if [ "$code" -le 17 ]; then\n        printf \'0\\n\' > /run/lynx/bootstrap-result\n        if [ "$code" = 0 ]; then worker=0\n        elif [ "$code" = 17 ]; then worker=199\n        else worker=$((code+130)); fi\n        printf \'%s\\n\' "$worker" > /run/lynx/worker-result /run/lynx/station-result /run/lynx/station-dmesg /run/lynx/radio-clock-result /run/lynx/wifi-worker-stack-result /run/lynx/wifi-worker-stack\n    elif [ "$code" = 18 ]; then\n        printf \'0\\n\' > /run/lynx/bootstrap-result\n    elif [ "$code" = 19 ]; then\n        printf \'199\\n\' > /run/lynx/bootstrap-result\n    elif [ "$code" -le 23 ]; then\n        printf \'%s\\n\' "$((code+131))" > /run/lynx/bootstrap-result\n    fi\n    if [ "$code" -ge 25 ]; then\n        printf \'0\\n\' > /run/lynx/bootstrap-result\n        if [ "$code" -ge 36 ]; then\n            printf \'135\\n\' > /run/lynx/worker-result\n            printf \'%s\\n\' "$code" > /run/lynx/radio-clock-result /run/lynx/wifi-worker-stack-result /run/lynx/wifi-worker-stack\n        else\n            printf \'139\\n\' > /run/lynx/worker-result\n            status=116\n            printf \'%s\\n\' "$status" > /run/lynx/station-result\n            token=$(/bin/busybox cat /etc/lynx/session-token)\n            printf \'LYNX_STATION_ATTEMPT_BEGIN %s\\n\' "$token" > /run/lynx/station-dmesg\n            echo \'[WIFI-FW] WiFi on/off takes more than 10 seconds\' >> /run/lynx/station-dmesg\n            echo \'WMT turn on WIFI fail!\' >> /run/lynx/station-dmesg\n            result=0\n            case "$code" in\n                25) echo \'mtk_wland_thread_main+0x214/0x450\' ;;\n                26) echo \'wlanProbe+0x100/0x1400\' ;;\n                27) echo \'_request_firmware+0x100/0x400\' ;;\n                28) echo \'conninfra_pwr_on+0x50/0x300\' ;;\n                29) echo \'wait_for_completion+0x20/0x100\' ;;\n                *) echo \'kthread+0x20/0x400\' ;;\n            esac > /run/lynx/wifi-worker-stack\n            case "$code" in 31|32|33) result=$code ;; esac\n            printf \'%s\\n\' "$result" > /run/lynx/wifi-worker-stack-result\n            [ "$code" != 34 ] || echo ordinary > /run/lynx/station-dmesg\n        fi\n    fi\n    if [ "$code" -ge 40 ]; then\n        printf \'154\\n\' > /run/lynx/bootstrap-result\n        printf \'%s\\n\' "$((code-39))" > /run/lynx/payload-step\n    fi\n    echo "NATIVE_TIMING_CASE=$code"\n    lynx_network_timing_reboot\n    echo "NATIVE_TIMING_EXIT=$?"\ndone\nprintf \'0\\n\' > /run/lynx/bootstrap-result\nprintf \'131\\n\' > /run/lynx/worker-result\nprintf \'10\\n\' > /run/lynx/network-timing-start\nprintf \'95.00 0\\n\' > /fixture/uptime\nprintf \'535\\n\' > /fixture/target\necho NATIVE_FAST_TIMING_LATE_SLOT\nlynx_network_timing_reboot\necho "NATIVE_FAST_TIMING_LATE_EXIT=$?"\nprintf \'600.00 0\\n\' > /fixture/uptime\necho NATIVE_FAST_TIMING_TOO_LATE\nlynx_network_timing_reboot\necho "NATIVE_FAST_TIMING_TOO_LATE_EXIT=$?"\nprintf \'bad\\n\' > /run/lynx/network-timing-start\necho NATIVE_TIMING_INVALID_START\nlynx_network_timing_reboot\necho "NATIVE_TIMING_INVALID_EXIT=$?"\nprintf \'10\\n\' > /run/lynx/network-timing-start\nprintf \'bad\\n\' > /fixture/uptime\necho NATIVE_TIMING_INVALID_CLOCK\nlynx_network_timing_reboot\necho "NATIVE_TIMING_INVALID_CLOCK_EXIT=$?"\n/bin/busybox poweroff -f\n'
    put(entries,'init',init);out=P/'artifacts'/('emulated-payload-fast-timing-native-'+str(time.time_ns()));out.mkdir(mode=0o700)
    (out/'Image').write_bytes(gzip.decompress(boot['kernel']));(out/'initramfs').write_bytes(pack(entries));(out/'init-source').write_bytes(init)
    q=R/'tools/qemu/noble/root';env=dict(os.environ,LD_LIBRARY_PATH=str(q/'usr/lib/x86_64-linux-gnu'),QEMU_MODULE_DIR=str(q/'usr/lib/x86_64-linux-gnu/qemu'),TMPDIR=str(R/'tools/mtk-tmp'))
    command=[str(q/'usr/bin/qemu-system-aarch64'),'-L',str(q/'usr/share/qemu'),'-no-user-config','-nodefaults','-machine','virt,gic-version=3','-accel','tcg','-cpu','cortex-a710','-smp','2','-m','1024','-display','none','-monitor','none','-serial','stdio','-nic','none','-no-reboot','-kernel',str(out/'Image'),'-initrd',str(out/'initramfs'),'-append','console=ttyAMA0 rdinit=/init loglevel=7 panic=0 initcall_debug']
    result=subprocess.run(command,env=env,capture_output=True,timeout=60);console=result.stdout+result.stderr;(out/'console.log').write_bytes(console)
    checks={}
    for code in [i for i in range(50) if i not in [9,35]]:
        section=console.split(('NATIVE_TIMING_CASE='+str(code)+'\r\n').encode())[-1].split(b'NATIVE_TIMING_CASE=')[0].split(b'NATIVE_TIMING_INVALID_START')[0].split(b'NATIVE_FAST_TIMING_LATE_SLOT')[0]
        checks[str(code)]=(f'LYNX_NETWORK_TIMING code={code} target={80+5*code}'.encode() in section and b'NATIVE_TIMING_EXIT=1' in section and section.count(b'NATIVE_TIMING_RESET')==1)
    checks['49_resets']=len(re.findall(rb'^NATIVE_TIMING_RESET\r?$',console,re.M))==49
    checks['invalid_start_refused']=b'NATIVE_TIMING_INVALID_EXIT=1' in console
    checks['invalid_clock_refused']=b'NATIVE_TIMING_INVALID_CLOCK_EXIT=1' in console
    late=console.split(b'NATIVE_FAST_TIMING_LATE_SLOT')[-1].split(b'NATIVE_FAST_TIMING_TOO_LATE')[0]
    checks['late_result_uses_separate_slot']=b'LYNX_NETWORK_TIMING code=9 target=525' in late and b'NATIVE_FAST_TIMING_LATE_EXIT=1' in late
    refused=console.split(b'NATIVE_FAST_TIMING_TOO_LATE\r\n')[-1].split(b'NATIVE_TIMING_INVALID_START')[0]
    checks['missed_all_slots_refused']=b'NATIVE_FAST_TIMING_TOO_LATE_EXIT=1' in refused and b'NATIVE_TIMING_RESET' not in refused
    checks['clean_poweroff']=b'reboot: Power down' in console
    checks['no_exception']=not any(x in console for x in [b'Kernel panic',b'Internal error:',b'CFI failure'])
    report={'passed':result.returncode==0 and all(checks.values()),'checks':checks,'candidate_sha256':SHA,'source_sha256':hashlib.sha256(source).hexdigest(),'phone_contacted':False,'limits':'Actual ARM64 BusyBox/stock kernel; clock and reboot are fixtures. Hardware startup and physical reset not exercised.'}
    path=out/'result.json';path.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'report':str(path),**report},indent=2));require(report['passed'],'Native timing test failed')
if __name__=='__main__':main()
