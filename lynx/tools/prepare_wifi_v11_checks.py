"""Prepare separate tests/contact/trial for direct Wi-Fi result timing."""
from pathlib import Path
R=Path(__file__).resolve().parent.parent;T=R/'tools'
OLD='bd0f541c93507b296865699e7c972c9468600bdc516e2bfed234dbb12497606f';NEW='4aad96c499317fa7f6d46371657a8e8bb93043b99de6627f801c5508f40a1033'
def update(s):return s.replace(OLD,NEW).replace('busybox-wifi-ssh-twostage-v10','busybox-wifi-ssh-twostage-v11').replace('wifi-v10-','wifi-v11-')
def save(name,s):
    out=T/name;assert not out.exists(),out;compile(s,str(out),'exec');out.write_text(s)
for name in ['test_wifi_v10_journals.py','test_wifi_v10_image_vm.py','lynx_wifi_v10_contact.py']:
    save(name.replace('_v10','_v11'),update((T/name).read_text()))
save('test_native_vendor_wifi_v11_loop.py',update((T/'test_native_vendor_payload_odm_fixed_loop.py').read_text()).replace('emulated-native-vendor-payload-odm-fixed-loop-','emulated-native-vendor-wifi-v11-loop-'))
decoder=(T/'lynx_bootstrap_timing.py').read_text().replace('range(8)','range(25)').replace('240+5','480+5').replace('-240-5','-480-5').replace('No radio started.','Radio trial; interpret result only after normal reset evidence.')
save('lynx_network_failure_timing.py',decoder)
s=update((T/'lynx_boot_a_wifi_v10_trial.py').read_text()).replace('validate_wifi_v10_image','validate_wifi_v11_image')
s=s.replace('from lynx_trial_observer import USBObserver','from lynx_trial_observer import USBObserver\nfrom lynx_network_failure_timing import decode_progress_timing')
s=s.replace('up to 600 seconds','up to 720 seconds').replace('time.monotonic()+600','time.monotonic()+720')
anchor="        report['fastboot_return_observed']=observer.returned.is_set()\n"
assert s.count(anchor)==1
s=s.replace(anchor,anchor+"""        if observer.returned.is_set():
            manifest=json.loads((LINUX.parent/'build-validation.json').read_text())
            baseline=json.loads((PROJECT/'docs/progress-debug-calibration.json').read_text())['baseline_seconds']
            report.update(decode_progress_timing(report['operations'][-1],json.loads(observer_path.read_text()),manifest,baseline))
""")
save('lynx_boot_a_wifi_v11_trial.py',s)
# Reuse only the tested QEMU scaffold; preserve original timing test.
s=(T/'test_bootstrap_timing_runtime.py').read_text().replace('a9c233c6aefbae80e2e9cd1fabbb1dcda8cdac3119d9ea58bc5e95b73c96802a',NEW).replace('busybox-bootstrap-timing-v1','busybox-wifi-ssh-twostage-v11').replace('lynx-bootstrap-timing-runtime.sh','lynx-network-failure-timing.sh').replace('emulated-bootstrap-timing-native-','emulated-network-failure-timing-native-')
start=s.index('    fixture=');end=s.index("    put(entries,'fixture'",start)
s=s[:start]+"""    fixture=source.split(b'\\nlynx_network_timing_reboot\\n')[0].replace(b'/proc/uptime',b'/fixture/uptime').replace(b'/bin/boot-proof-reboot-native',b'/bin/timing-reset').replace(b'BB=/bin/busybox',b'BB=/bin/timing-busybox')
"""+s[end:]
start=s.index('    init=b');end=s.index("    put(entries,'init',init)",start)
head=b'''#!/bin/sh
export PATH=/bin:/sbin
BB=/bin/busybox
$BB mount -t proc proc /proc
$BB mount -t sysfs sysfs /sys
$BB mount -t tmpfs tmpfs /dev
$BB mount -t tmpfs tmpfs /run
$BB mknod -m 600 /dev/console c 5 1
$BB mknod -m 600 /dev/kmsg c 1 11
exec > /dev/console 2>&1
$BB mkdir -p /run/lynx
'''
tail=b'''
for code in $(/bin/busybox seq 0 24); do
    printf '10\\n' > /run/lynx/network-timing-start
    printf '430.00 0\\n' > /fixture/uptime
    printf '%s\\n' "$((10+480+5*code))" > /fixture/target
    /bin/busybox rm -f /run/lynx/bootstrap-result /run/lynx/worker-result
    if [ "$code" -le 17 ]; then
        printf '0\\n' > /run/lynx/bootstrap-result
        if [ "$code" = 0 ]; then worker=0
        elif [ "$code" = 17 ]; then worker=199
        else worker=$((code+130)); fi
        printf '%s\\n' "$worker" > /run/lynx/worker-result
    elif [ "$code" = 18 ]; then
        printf '0\\n' > /run/lynx/bootstrap-result
    elif [ "$code" = 19 ]; then
        printf '199\\n' > /run/lynx/bootstrap-result
    elif [ "$code" -le 23 ]; then
        printf '%s\\n' "$((code+131))" > /run/lynx/bootstrap-result
    fi
    echo "NATIVE_TIMING_CASE=$code"
    lynx_network_timing_reboot
    echo "NATIVE_TIMING_EXIT=$?"
done
printf 'bad\\n' > /run/lynx/network-timing-start
echo NATIVE_TIMING_INVALID_START
lynx_network_timing_reboot
echo "NATIVE_TIMING_INVALID_EXIT=$?"
printf '10\\n' > /run/lynx/network-timing-start
printf 'bad\\n' > /fixture/uptime
echo NATIVE_TIMING_INVALID_CLOCK
lynx_network_timing_reboot
echo "NATIVE_TIMING_INVALID_CLOCK_EXIT=$?"
/bin/busybox poweroff -f
'''
s=s[:start]+'    init='+repr(head)+'+fixture+'+repr(tail)+'\n'+s[end:]
start=s.index('    checks={}');end=s.index('    report=',start)
s=s[:start]+"""    checks={}
    for code in range(25):
        section=console.split(('NATIVE_TIMING_CASE='+str(code)+'\\r\\n').encode())[-1].split(b'NATIVE_TIMING_CASE=')[0].split(b'NATIVE_TIMING_INVALID_START')[0]
        checks[str(code)]=(f'LYNX_NETWORK_TIMING code={code} target={480+5*code}'.encode() in section and b'NATIVE_TIMING_EXIT=1' in section and section.count(b'NATIVE_TIMING_RESET')==1)
    checks['25_resets']=len(re.findall(rb'^NATIVE_TIMING_RESET\\r?$',console,re.M))==25
    checks['invalid_start_refused']=b'NATIVE_TIMING_INVALID_EXIT=1' in console
    checks['invalid_clock_refused']=b'NATIVE_TIMING_INVALID_CLOCK_EXIT=1' in console
    checks['clean_poweroff']=b'reboot: Power down' in console
    checks['no_exception']=not any(x in console for x in [b'Kernel panic',b'Internal error:',b'CFI failure'])
"""+s[end:]
save('test_native_network_failure_timing.py',s)
print('Separate direct-result timing tests and pinned network tools prepared.')
