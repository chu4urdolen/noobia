"""Test standard return tracing and verified device-name fetch on the stock kernel."""
import argparse,gzip,hashlib,json,os,re,subprocess,sys,time
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent;P=ROOT/'linux-port'
sys.path.insert(0,str(P))
from image_formats import read_boot_v4,read_newc,require
from prepare_busybox_diagnostics import pack
from network_userspace import put
from ramdisk_codec import decompress


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--cpu',choices=['cortex-a72','cortex-a76','cortex-a710','max','max,pauth=off','max,sve=off','max,pauth=off,sve=off'],default='cortex-a72');parser.add_argument('--baseline',action='store_true')
    parser.add_argument('--load-reset-module',action='store_true');parser.add_argument('--deferred-reset-probe',action='store_true');parser.add_argument('--collector-v2',action='store_true');parser.add_argument('--collector-v3',action='store_true');parser.add_argument('--collector-core',action='store_true');parser.add_argument('--collector-platform',action='store_true');parser.add_argument('--platform-v2',action='store_true');parser.add_argument('--core-classifier',action='store_true');parser.add_argument('--platform-classifier',action='store_true');parser.add_argument('--errno-classifier',action='store_true');args=parser.parse_args()
    if args.errno_classifier:args.platform_classifier=True
    if args.platform_classifier:
        require(args.collector_platform and args.platform_v2,'Platform classifier requires corrected platform collector')
        args.core_classifier=True
    require(not args.platform_v2 or args.collector_platform,'Platform v2 requires platform collector')
    require(sum([args.collector_v2,args.collector_v3,args.collector_core,args.collector_platform])<=1,'Select one collector')
    if args.collector_platform: args.collector_core=True
    if args.collector_core: args.collector_v3=True
    require(not args.deferred_reset_probe or args.load_reset_module,'Deferred probe requires module-loading test')
    require(not (args.baseline and args.load_reset_module),'Baseline and module-loading test are separate')
    out=P/'artifacts'/('emulated-native-initcall-debug-'+args.cpu+('-module-load' if args.load_reset_module else '')+'-'+str(time.time_ns()));out.mkdir()
    image=(P/'artifacts/busybox-binding-profile-v1/nord3-busybox-candidate.img').read_bytes()
    require(hashlib.sha256(image).hexdigest()=='571fc62e9b6c4ba99ea3bc4c4c327fb147d405fccac073305ffd978fc101c7b0','Reference changed')
    boot=read_boot_v4(image);entries=read_newc(decompress(boot['ramdisk']))
    source=(P/'artifacts/busybox-probe-trace-v2/collector-source.sh' if args.collector_v2 else P/'lynx-driver-trace.sh').read_bytes()
    classifier=(P/'lynx-classify-driver-trace-v2.awk' if args.collector_v2 else P/'lynx-classify-driver-trace.awk').read_bytes()
    if args.collector_v3:
        source=(P/'artifacts/busybox-probe-trace-v3/collector-source.sh').read_bytes()
        classifier=(P/'lynx-classify-driver-trace-v3.awk').read_bytes()
    if args.collector_core:
        source=(P/'lynx-driver-trace-core-v1.sh').read_bytes()
    if args.collector_platform:
        source=(P/('lynx-driver-trace-platform-v2.sh' if args.platform_v2 else 'lynx-driver-trace-platform-v1.sh')).read_bytes()
    if args.core_classifier:
        require(args.collector_core and args.deferred_reset_probe,'Core classifier requires the core collector and actual module return fixture')
        classifier=(P/'lynx-classify-core-trace.awk').read_bytes()
    if args.platform_classifier:
        classifier=(P/'lynx-classify-platform-trace.awk').read_bytes()
    if args.errno_classifier:
        classifier=(P/'lynx-classify-platform-errno.awk').read_bytes()
    put(entries,'bin/classify-driver-trace.awk',classifier,0o100644)
    init=b'''#!/bin/sh
BB=/bin/busybox
export PATH=/bin:/sbin
$BB mount -t proc proc /proc
$BB mount -t sysfs sysfs /sys
$BB mount -t tmpfs tmpfs /dev
$BB mount -t tmpfs tmpfs /run
$BB mknod -m 600 /dev/console c 5 1
$BB mknod -m 666 /dev/null c 1 3
$BB mknod -m 666 /dev/zero c 1 5
exec > /dev/console 2>&1
echo TRACE_VM_INIT_ENTERED
$BB mkdir -p /run/lynx
'''+source+b'''
lynx_driver_trace_setup
printf 'TRACE_SETUP_EXIT=%s\n' "$?"
# VM-only extra probes: prove actual retval capture and device-name formatting.
printf '%s\n' 'r32:lynx_ufs/test_pid __arm64_sys_getpid ret=$retval:s32' >> "$trace_root/kprobe_events"
printf 'TRACE_PID_ADD_EXIT=%s\n' "$?"
printf '%s\n' 'p:lynx_ufs/test_device device_add name=+0(+0($arg1)):string' >> "$trace_root/kprobe_events"
printf 'TRACE_DEVICE_ADD_EXIT=%s\n' "$?"
printf '%s\n' 'r32:lynx_ufs/test_open __arm64_sys_openat ret=$retval:s32' >> "$trace_root/kprobe_events"
printf 'TRACE_OPEN_ADD_EXIT=%s\n' "$?"
printf '1\n' > "$trace_instance/events/lynx_ufs/test_pid/enable"
printf '1\n' > "$trace_instance/events/lynx_ufs/test_device/enable"
printf '1\n' > "$trace_instance/events/lynx_ufs/test_open/enable"
$BB sh -c 'printf "TRACED_PID=%s\\n" "$$"'
$BB cat /run/deliberately-absent-trace-fixture
# A new loop device backed by a RAM file; QEMU has no attached disks.
$BB mknod /dev/loop16 b 7 16
$BB dd if=/dev/zero of=/run/trace-loop bs=4096 count=1
$BB losetup /dev/loop16 /run/trace-loop
printf 'TRACE_RAM_LOOP_ATTACH_EXIT=%s\n' "$?"
lynx_driver_trace_capture
printf 'TRACE_CAPTURE_EXIT=%s\n' "$?"
printf 'TRACE_FILE_MODE=%s\n' "$($BB stat -c %a /run/lynx/driver-trace.log)"
echo TRACE_CAPTURE_BEGIN
$BB cat /run/lynx/driver-trace.log
echo TRACE_CAPTURE_END
# A VM-only relabelled real ENOENT record tests the same signed event formatter.
$BB grep 'test_open:.*ret=-2' /run/lynx/driver-trace.log | $BB sed 's/test_open:/init_return:/' > /run/lynx/classifier-fixture.log
$BB awk -f /bin/classify-driver-trace.awk /run/lynx/classifier-fixture.log > /run/lynx/classifier-result
printf 'TRACE_NEGATIVE_CLASSIFIER='; $BB cat /run/lynx/classifier-result
echo TRACE_TEST_FINISHED
$BB poweroff -f
while :; do $BB sleep 60; done
'''
    if args.baseline:
        boundary=init.index(b'lynx_driver_trace_setup\n')
        init=init[:boundary]+b'echo TRACE_BASELINE_COMPLETE\n$BB poweroff -f\nwhile :; do $BB sleep 60; done\n'
    if args.collector_v2 or args.collector_v3:
        init=init.replace(b"$BB sed 's/test_open:/init_return:/'",b"$BB sed 's/test_open:/mtk_probe_return:/'",1)
        init=init.replace(b'$BB awk -f /bin/classify-driver-trace.awk',b'$BB grep health_pid: /run/lynx/driver-trace.log >> /run/lynx/classifier-fixture.log\n$BB awk -v expected_pid="$($BB cat /run/lynx/trace-health-pid)" -f /bin/classify-driver-trace.awk',1)
    if args.load_reset_module:
        reset=(P/'artifacts/stock-cph2493-August-eu-ota/vendor-ramdisk-unpacked/lib/modules/reset-ti-syscon.ko').read_bytes()
        require(hashlib.sha256(reset).hexdigest()=='98c8b506aacb757dc8ef94df2fffe36789c7a64ad2311ffdae263d86d2fe98c8','Stock reset module changed')
        put(entries,'lib/modules/reset-ti-syscon.ko',reset,0o100644)
        marker=b'# VM-only extra probes:'
        module_test=b'''$BB insmod /lib/modules/reset-ti-syscon.ko
printf 'TRACE_MODULE_LOAD_EXIT=%s\\n' "$?"
[ -d /sys/module/reset_ti_syscon ] && echo TRACE_MODULE_PRESENT
[ -d /sys/bus/platform/drivers/ti-syscon-reset ] && echo TRACE_MODULE_DRIVER_REGISTERED
'''
        if args.deferred_reset_probe:
            module_test=b'''printf '%s\\n' 'r32:lynx_ufs/test_module_init reset_ti_syscon:init_module ret=$retval:s32' >> "$trace_root/kprobe_events"
printf 'TRACE_DEFERRED_ADD_EXIT=%s\\n' "$?"
printf '1\\n' > "$trace_instance/events/lynx_ufs/test_module_init/enable"
printf 'TRACE_DEFERRED_ENABLE_EXIT=%s\\n' "$?"
'''+module_test
        require(marker in init,'Missing insertion point')
        init=init.replace(marker,module_test+marker,1)
    semantic_cases=[]
    if args.core_classifier:
        pattern='platform-errno-classifier-*/result.json' if args.errno_classifier else ('platform-trace-classifier-*/result.json' if args.platform_classifier else 'core-trace-classifier-*/result.json')
        receipts=sorted((ROOT/'tools/test-artifacts').glob(pattern))
        require(receipts,'Core semantics fixtures missing')
        receipt=json.loads(receipts[-1].read_text())
        require(receipt['passed'] and receipt['source_sha256']==hashlib.sha256(classifier).hexdigest(),'Core fixtures source differs')
        semantic_cases=receipt['cases']
        commands=b'''$BB grep 'test_module_init:.*ret=0' /run/lynx/driver-trace.log | $BB sed 's/test_module_init:/mtk_probe_return:/' > /run/lynx/classifier-zero.log
$BB grep health_pid: /run/lynx/driver-trace.log >> /run/lynx/classifier-zero.log
printf 'TRACE_ZERO_CLASSIFIER='; $BB awk -v expected_pid="$($BB cat /run/lynx/trace-health-pid)" -f /bin/classify-driver-trace.awk /run/lynx/classifier-zero.log
'''
        for case in semantic_cases:
            name=case['case'];put(entries,'etc/test-core/'+name,Path(case['fixture']).read_bytes(),0o100644)
            device_arg=(f" -v expected_device='{case['expected_device']}'" if args.errno_classifier else '')
            commands+=(f"printf 'CORE_CASE_{name}='; $BB awk -v expected_pid=123 -v registration_failed={case['registration_failed']}{device_arg} -f /bin/classify-driver-trace.awk /etc/test-core/{name}\n").encode()
        init=init.replace(b'echo TRACE_TEST_FINISHED\n',commands+b'echo TRACE_TEST_FINISHED\n',1)
    if args.platform_classifier:
        negative=b"$BB grep 'test_open:.*ret=-2' /run/lynx/driver-trace.log | $BB sed 's/test_open:/mtk_probe_return:/' > /run/lynx/classifier-fixture.log"
        zero=b"$BB grep 'test_module_init:.*ret=0' /run/lynx/driver-trace.log | $BB sed 's/test_module_init:/mtk_probe_return:/' > /run/lynx/classifier-zero.log"
        require(init.count(negative)==1 and init.count(zero)==1,'Native real return fixtures changed')
        # VM-only synthetic pairing around actual signed kernel return records.
        init=init.replace(negative,br'''$BB grep 'test_open:.*ret=-2' /run/lynx/driver-trace.log | $BB awk '{ sub(/^[^[]*/, "fixture-234 "); sub(/test_open:/,"dma_return:"); print "fixture-234 [000] 1.0: dma_enter: (fixture) name=\"112b0000.ufshci\""; print }' > /run/lynx/classifier-fixture.log''',1)
        init=init.replace(zero,br'''$BB grep 'test_module_init:.*ret=0' /run/lynx/driver-trace.log | $BB awk '{ sub(/^[^[]*/, "fixture-234 "); sub(/test_module_init:/,"platform_return:"); print "fixture-234 [000] 1.0: platform_enter: (fixture) name=\"112b0000.ufshci\""; print }' > /run/lynx/classifier-zero.log''',1)
    live_name_source=None
    if args.errno_classifier:
        init=init.replace(b'sub(/test_open:/,"dma_return:")',b'sub(/test_open:/,"platform_return:")',1).replace(b'1.0: dma_enter: (fixture)',b'1.0: platform_enter: (fixture)',1)
        init=init.replace(b'$BB awk -v expected_pid="$($BB cat',b'$BB awk -v expected_device=112b0000.ufshci -v expected_pid="$($BB cat')
        live_name_source=(P/'lynx-live-ufs-name.sh').read_bytes()
        helper=live_name_source.replace(b'/sys/bus/platform/devices',b'/run/live-devices')
        commands=helper+b'''
$BB mkdir -p /run/live-devices /run/live-tree/ufshci@112b0000
lynx_live_ufs_name; printf 'LIVE_EMPTY_EXIT=%s\\n' "$?"
$BB mkdir /run/live-devices/bootdevice
$BB ln -s /run/live-tree/ufshci@112b0000 /run/live-devices/bootdevice/of_node
lynx_live_ufs_name; printf 'LIVE_ALIAS_EXIT=%s_NAME=%s\\n' "$?" "$live_ufs_name"
$BB mkdir /run/live-devices/second-controller
$BB ln -s /run/live-tree/ufshci@112b0000 /run/live-devices/second-controller/of_node
lynx_live_ufs_name; printf 'LIVE_DUPLICATE_EXIT=%s\\n' "$?"
'''
        init=init.replace(b'echo TRACE_TEST_FINISHED\n',commands+b'echo TRACE_TEST_FINISHED\n',1)
    clock_names=['mrdump.ko','aee_aed.ko','clk-common.ko']+json.loads((P/'docs/scpsys-clock-suppliers.json').read_text())['missing_supplier_modules']
    clock_hashes={};commands=b''
    for name in clock_names:
        data=(P/'artifacts/stock-cph2493-August-eu-ota/vendor-ramdisk-unpacked/lib/modules'/name).read_bytes()
        put(entries,'lib/modules/'+name,data,0o100644);clock_hashes[name]=hashlib.sha256(data).hexdigest()
        commands+=(f"$BB insmod /lib/modules/{name}\nprintf 'CLOCK_LOAD_{name}=%s\\n' \"$?\"\n").encode()
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
echo CLOCK_VM_INIT_ENTERED
'''+commands+b'''
echo CLOCK_VM_FINISHED
$BB poweroff -f
'''
    put(entries,'init',init)
    (out/'Image').write_bytes(gzip.decompress(boot['kernel']));(out/'initramfs').write_bytes(pack(entries));(out/'init-source').write_bytes(init)
    runtime=ROOT/'tools/qemu/noble/root'
    command=[str(runtime/'usr/bin/qemu-system-aarch64'),'-L',str(runtime/'usr/share/qemu'),'-no-user-config','-nodefaults','-machine','virt,gic-version=3','-accel','tcg','-cpu',args.cpu,'-smp','2','-m','1024','-display','none','-monitor','none','-serial','stdio','-nic','none','-no-reboot','-kernel',str(out/'Image'),'-initrd',str(out/'initramfs'),'-append','console=ttyAMA0 rdinit=/init loglevel=7 panic=0 initcall_debug']
    env=dict(os.environ,LD_LIBRARY_PATH=str(runtime/'usr/lib/x86_64-linux-gnu'),QEMU_MODULE_DIR=str(runtime/'usr/lib/x86_64-linux-gnu/qemu'),TMPDIR=str(ROOT/'tools/mtk-tmp'))
    started=time.monotonic()
    try:
        result=subprocess.run(command,env=env,capture_output=True,timeout=45);raw=result.stdout+result.stderr;code=result.returncode
    except subprocess.TimeoutExpired as error:raw=(error.stdout or b'')+(error.stderr or b'');code=None
    (out/'console.log').write_bytes(raw)
    capture=raw.split(b'TRACE_CAPTURE_BEGIN\r\n')[-1].split(b'TRACE_CAPTURE_END')[0]
    (out/'driver-trace.log').write_bytes(capture)
    pid=re.search(rb'TRACED_PID=(\d+)',raw)
    checks={'setup':b'TRACE_SETUP_EXIT=0' in raw,'pid_probe_added':b'TRACE_PID_ADD_EXIT=0' in raw,
            'device_probe_added':b'TRACE_DEVICE_ADD_EXIT=0' in raw,'ram_loop':b'TRACE_RAM_LOOP_ATTACH_EXIT=0' in raw,
            'capture':b'TRACE_CAPTURE_EXIT=0' in raw,'private_mode':b'TRACE_FILE_MODE=600' in raw,
            'actual_pid_return':bool(pid and re.search(rb'test_pid:.*ret='+pid.group(1)+rb'(?:\s|$)',capture)),
            'actual_device_name':b'name="loop16"' in capture,
            'negative_errno':bool(re.search(rb'test_open:.*ret=-2(?:\s|$)',capture)),
            'native_classifier':bool(re.search((rb'TRACE_NEGATIVE_CLASSIFIER=7 [1-9][0-9]* -2 ' if args.collector_v2 or args.collector_v3 else rb'TRACE_NEGATIVE_CLASSIFIER=4 [1-9][0-9]* -2 '),raw))}
    checks['init_entered']=b'TRACE_VM_INIT_ENTERED' in raw
    if args.collector_platform:
        checks['actual_platform_driver_name']=b'match_enter:' in capture and b'driver="ti-syscon-reset"' in capture
    if args.core_classifier:
        checks['native_classifier']=b'TRACE_NEGATIVE_CLASSIFIER=7 unknown unknown unknown -2' in raw
        checks['actual_zero_classifier']=b'TRACE_ZERO_CLASSIFIER=2 unknown unknown unknown 0' in raw
        for case in semantic_cases:
            checks['core_'+case['case']]=bool(re.search(('CORE_CASE_'+case['case']+'='+str(case['expected_code'])+' ').encode(),raw))
    if args.platform_classifier:
        checks['native_classifier']=b'TRACE_NEGATIVE_CLASSIFIER=3 unknown -2 unknown ' in raw
        checks['actual_zero_classifier']=b'TRACE_ZERO_CLASSIFIER=7 unknown unknown 0 ' in raw
    if args.errno_classifier:
        checks['native_classifier']=b'TRACE_NEGATIVE_CLASSIFIER=2 -2 ' in raw
        checks['actual_zero_classifier']=b'TRACE_ZERO_CLASSIFIER=0 0 ' in raw
        checks.update(live_empty_refused=b'LIVE_EMPTY_EXIT=1' in raw,live_alias_resolved=b'LIVE_ALIAS_EXIT=0_NAME=bootdevice' in raw,live_duplicate_refused=b'LIVE_DUPLICATE_EXIT=1' in raw)
    checks['clean_poweroff']=b'reboot: Power down' in raw
    checks['no_kernel_exception']=not any(marker in raw for marker in [b'Kernel panic',b'Internal error:',b'CFI failure'])
    if args.baseline:checks={'baseline_completed':b'TRACE_BASELINE_COMPLETE' in raw,'clean_poweroff':checks['clean_poweroff'],'no_kernel_exception':checks['no_kernel_exception']}
    if args.load_reset_module:
        checks.update(module_loaded=b'TRACE_MODULE_LOAD_EXIT=0' in raw,module_present=b'TRACE_MODULE_PRESENT' in raw,module_driver_registered=b'TRACE_MODULE_DRIVER_REGISTERED' in raw)
    if args.deferred_reset_probe:
        checks.update(deferred_added=b'TRACE_DEFERRED_ADD_EXIT=0' in raw,deferred_enabled=b'TRACE_DEFERRED_ENABLE_EXIT=0' in raw,deferred_actual_return=bool(re.search(rb'test_module_init:.*ret=0(?:\s|$)',capture)))
    checks={'init_entered':b'CLOCK_VM_INIT_ENTERED' in raw,'finished':b'CLOCK_VM_FINISHED' in raw,'clean_poweroff':b'reboot: Power down' in raw,'no_kernel_exception':not any(m in raw for m in [b'Kernel panic',b'Internal error:',b'CFI failure'])}
    for name in clock_names:
        checks['clock_load_'+name]=('CLOCK_LOAD_'+name+'=0').encode() in raw
    checks['stock_initcall_start_logged']=bool(re.search(rb'calling  .*clk_mt6983_cam.* @ ',raw))
    checks['stock_initcall_return_logged']=bool(re.search(rb'initcall .*clk_mt6983_cam.*returned 0 after ',raw))
    passed=code==0 and all(checks.values())
    report={'clock_module_sha256':clock_hashes,'passed':passed,'checks':checks,'cpu_model':args.cpu,'source_sha256':hashlib.sha256(source).hexdigest(),'classifier_sha256':hashlib.sha256(classifier).hexdigest(),
            'kernel_sha256':hashlib.sha256(boot['kernel']).hexdigest(),'phone_contacted':False,'elapsed_seconds':time.monotonic()-started,'exit_code':code,'raw_bytes':len(raw),'baseline_only':args.baseline,
            'module_loading_under_trace':args.load_reset_module,
            'deferred_reset_probe':args.deferred_reset_probe,
            'collector_v2':args.collector_v2,
            'collector_v3':args.collector_v3,
            'collector_core':args.collector_core,
            'collector_platform':args.collector_platform,
            'platform_v2':args.platform_v2,
            'core_classifier':args.core_classifier,
            'platform_classifier':args.platform_classifier,
            'errno_classifier':args.errno_classifier,
            'live_name_source_sha256':hashlib.sha256(live_name_source).hexdigest() if live_name_source else None,
            'limits':'Real stock-kernel ARM64 tracing and RAM loop device. No physical MediaTek probe or persistent retrieval demonstrated.'}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'passed':passed,'report':str(out/'result.json'),'checks':checks},indent=2));require(passed,'Stock-kernel tracing test failed')


if __name__=='__main__':main()
