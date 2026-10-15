"""Prepare an independent validator for the narrowly instrumented payload image."""
from pathlib import Path
R=Path(__file__).resolve().parent.parent;T=R/'tools'
s=(T/'validate_bootstrap_timing_image.py').read_text()
s=s.replace('a9c233c6aefbae80e2e9cd1fabbb1dcda8cdac3119d9ea58bc5e95b73c96802a','9df9229dba14a1b29e17a5bcdb8c34fb813682998a63ff57718ed1bb7f6f9226').replace('lynx_bootstrap_timing','lynx_payload_timing')
s=s.replace("R/'tools/validate_wifi_v7_image.py')","R/'tools/validate_bootstrap_timing_image.py'),'--count','34'")
s=s.replace("F=P/'artifacts/busybox-bootstrap-timing-v1';V=P/'artifacts/busybox-wifi-ssh-twostage-v7'","F=P/'artifacts/busybox-payload-timing-v1';V=P/'artifacts/busybox-bootstrap-timing-v1'")
start=s.index('    runtime=');end=s.index("    require(b'. /etc/lynx/wifi-runtime.sh'",start)
block=r'''    runtime=(P/'lynx-payload-timing-runtime.sh').read_bytes()
    expected=previous['init']['data']
    markers=[(1,b"    candidates=''\n"),(2,b'    [ -b "$device" ] || return 1\n'),(3,b'    [ "$($BB blockdev --getsize64 "$device")" = 67108864 ] || return 1\n'),(4,b'    bytes=$($BB cat /etc/lynx/payload-bytes) || return 1\n'),(5,b'    $BB dd if="$device" of=/run/lynx/payload-blocks bs=4096 skip=6144 count="$blocks" || return 1\n'),(6,b'    actual=$($BB sha256sum /run/lynx/payload.cpio.gz) || return 1\n'),(7,b'    $BB gzip -dc /run/lynx/payload.cpio.gz > /run/lynx/payload.cpio || return 1\n')]
    for code,anchor in markers:
        require(expected.count(anchor)==1,'Payload boundary changed')
        expected=expected.replace(anchor,("    printf '%s\\n' "+str(code)+" > /run/lynx/payload-progress || return 1\n").encode()+anchor)
    old_runtime=(P/'lynx-bootstrap-timing-runtime.sh').read_bytes()
    require(expected.count(old_runtime)==1,'Original timing boundary changed')
    expected=expected.replace(old_runtime,runtime)
    require(current['init']['data']==expected==(F/'init-source').read_bytes(),'Unexpected executable init')
'''
s=s[:start]+block+s[end:]
start=s.index('    codes=');end=s.index('    require(manifest[',start)
codes={'0':'bootstrap completed: own boot_a payload verified/extracted; no radio','1':'payload failed: candidate enumeration/uniqueness/device name','2':'payload failed: expected block device node absent','3':'payload failed: capacity or read-only block ioctl','4':'payload failed: size/hash metadata validation','5':'payload failed: raw block read or byte trimming','6':'payload failed: SHA256 calculation or mismatch','7':'payload failed: gzip decompression or cpio extraction','8':'other bootstrap failure, deadline or invalid progress'}
s=s[:start]+'    codes='+repr(codes)+'\n'+s[end:]
s=s.replace('range(8)','range(9)').replace('emulated-bootstrap-timing-native-','emulated-payload-timing-native-').replace('emulated-bootstrap-timing-guard-','emulated-payload-timing-guard-').replace('bootstrap-timing-validation.json','payload-timing-validation.json')
needle='    # Entire timing grid'
extra=r'''    loops=sorted((P/'artifacts').glob('emulated-native-payload-step-loop-*/result.json'));require(loops,'Actual block I/O test missing')
    l=json.loads(loops[-1].read_text());reader=expected[expected.index(b'lynx_read_own_boot_payload() {'):expected.index(b'lynx_wifi_bootstrap_child_unlogged() {')]
    require(l['passed'] and l['candidate_sha256']==SHA and l['payload_reader_sha256']==sha(reader),'Actual block reader test differs')
'''
s=s.replace(needle,extra+needle)
out=T/'validate_payload_timing_image.py';assert not out.exists();compile(s,str(out),'exec');out.write_text(s);print(out)
