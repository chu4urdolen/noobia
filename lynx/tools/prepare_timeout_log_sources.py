"""Preserve prior diagnostics while preparing a timeout-context experiment."""
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
P=ROOT/'linux-port';T=ROOT/'tools'

def save(path,text):
    assert not path.exists(), 'Preserve previous artifact: '+str(path)
    path.write_text(text)

def main():
    runtime=(P/'lynx-platform-errno-runtime.sh').read_text()
    marker='                        log "PLATFORM_ERRNO_FIELD'
    assert runtime.count(marker)==1
    runtime=runtime.replace(marker,'''                        if [ "$probe_code" = 110 ] && [ "$trace_platform_ret" = -110 ] && [ "$trace_health" = 1 ]; then
                            if [ -s /run/lynx/kernel-dmesg.log ] && $BB awk -v expected_device="$live_ufs_name" -v expected_domain=ufs0 -f /etc/lynx/classify-timeout-logs.awk /run/lynx/kernel-dmesg.log > /run/lynx/timeout-log-result; then
                                if IFS=' ' read -r probe_code < /run/lynx/timeout-log-result; then
                                    case "$probe_code" in ''|*[!0-9]*) probe_code=126 ;; esac
                                    [ "$probe_code" -le 63 ] || probe_code=126
                                else probe_code=126; fi
                            else probe_code=126; fi
                        elif [ "$probe_code" -lt 124 ]; then
                            probe_code=124
                        fi
'''+marker,1)
    runtime=runtime.replace('PLATFORM_ERRNO_FIELD','TIMEOUT_LOG_FIELD').replace('ERRNO_FIELD','TIMEOUT_CONTEXT')
    save(P/'lynx-timeout-log-runtime.sh',runtime)
    native=(T/'test_native_driver_trace.py').read_text()
    marker="    put(entries,'init',init)"
    assert native.count(marker)==1
    injection='''    log_source=(P/'lynx-classify-timeout-logs.awk').read_bytes()
    put(entries,'bin/classify-timeout-logs.awk',log_source,0o100644)
    fixtures=sorted((ROOT/'tools/test-artifacts').glob('timeout-log-classifier-*/result.json'))
    log_report=json.loads(fixtures[-1].read_text())
    require(log_report['passed'] and log_report['source_sha256']==hashlib.sha256(log_source).hexdigest(),'Log fixtures differ')
    log_cases=log_report['cases'];commands=b''
    for case in log_cases:
        put(entries,'etc/test-logs/'+case['case'],Path(case['fixture']).read_bytes(),0o100644)
        commands+=("printf 'LOG_CASE_"+case['case']+"='; $BB awk -v expected_device=112b0000.ufshci -v expected_domain=ufs0 -f /bin/classify-timeout-logs.awk /etc/test-logs/"+case['case']+"\\n").encode()
    # VM only: inject synthetic printk then read the real kernel ring via dmesg.
    commands+=b"$BB mknod -m 600 /dev/kmsg c 1 11\\nprintf '<3>scpsys: Failed to power on mtcmos ufs0(-110)\\\\n' > /dev/kmsg\\n$BB dmesg > /run/log-fixture-dmesg\\nprintf 'LOG_KMSG_FIXTURE='; $BB awk -v expected_device=112b0000.ufshci -v expected_domain=ufs0 -f /bin/classify-timeout-logs.awk /run/log-fixture-dmesg\\n"
    init=init.replace(b'echo TRACE_TEST_FINISHED\\n',commands+b'echo TRACE_TEST_FINISHED\\n',1)
'''
    native=native.replace(marker,injection+marker,1)
    marker="    passed=code==0 and all(checks.values())"
    native=native.replace(marker,"    for case in log_cases:\n        checks['log_'+case['case']]=bool(re.search(('LOG_CASE_'+case['case']+'='+str(case['expected_code'])+r'\\r?\\n').encode(),raw))\n    checks['vm_synthetic_kmsg_roundtrip']=b'LOG_KMSG_FIXTURE=33' in raw\n"+marker,1)
    native=native.replace("'passed':passed,'checks':checks", "'log_classifier_sha256':hashlib.sha256(log_source).hexdigest(),'vm_only_synthetic_kmsg':True,'passed':passed,'checks':checks",1)
    native=native.replace("emulated-native-driver-trace-","emulated-native-timeout-logs-")
    save(T/'test_native_timeout_logs.py',native)
    builder=(P/'prepare_platform_errno_image.py').read_text()
    builder=builder.replace('busybox-platform-probe-v1','busybox-platform-errno-v1').replace("OUT=P/'artifacts/busybox-platform-errno-v1'","OUT=P/'artifacts/busybox-timeout-log-v1'")
    builder=builder.replace('aff51e9e74094d95fa0e2addbf3671326869a07eda2104f09b28821f8b07f56f','8856714bafaabc6869ab58fa46194babcd055afd22b88ba93d3d0bf02901afaa')
    builder=builder.replace('lynx-platform-errno-runtime.sh','lynx-timeout-log-runtime.sh')
    marker="    token=secrets.token_hex(16)"
    builder=builder.replace(marker,"    put(entries,'etc/lynx/classify-timeout-logs.awk',(P/'lynx-classify-timeout-logs.awk').read_bytes(),0o100644)\n"+marker,1)
    start=builder.index('    codes=');end=builder.index('    report=',start)
    builder=builder[:start]+'''    codes={str(n):'kernel timeout log mask '+str(n) for n in range(64)}
    codes.update({str(n):'reserved; refuse interpretation' for n in range(64,124)})
    codes.update({'124':'live target/completed return unavailable or no longer -110',
                  '125':'fresh PID trace health absent','126':'trace/log setup/capture/correlation unavailable','127':'bootstrap worker deadline'})
'''+builder[end:]
    builder=builder.replace("baseline_reference_seconds=21.9", "log_classifier_sha256=hashlib.sha256((P/'lynx-classify-timeout-logs.awk').read_bytes()).hexdigest(),\n                  baseline_reference_seconds=21.9")
    save(P/'prepare_timeout_log_image.py',builder)
    ignore=P/'.gitignore'
    with ignore.open('a') as f:f.write('\nartifacts/busybox-timeout-log-*/\n')
    print('Prepared sources and VM-only test; no phone contacted.')

if __name__=='__main__':main()
