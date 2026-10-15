"""Independently verify startup delta, protected bytes, tested timing and reset guard."""
import argparse,hashlib,json,stat,struct,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';sys.path.insert(0,str(P))
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
from lynx_payload_timing import decode_progress_timing
SHA='9df9229dba14a1b29e17a5bcdb8c34fb813682998a63ff57718ed1bb7f6f9226'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--count',type=int,choices=[34],required=True);parser.parse_args()
    parent=subprocess.run(['python3',str(R/'tools/validate_bootstrap_timing_image.py'),'--count','34'],capture_output=True,text=True,timeout=60);require(parent.returncode==0,'v7 reference invalid: '+parent.stdout+parent.stderr)
    F=P/'artifacts/busybox-payload-timing-v1';V=P/'artifacts/busybox-bootstrap-timing-v1'
    image=(F/'nord3-busybox-candidate.img').read_bytes();reference=(V/'nord3-busybox-candidate.img').read_bytes()
    require(sha(image)==SHA and len(image)==67108864,'Image hash/size differs')
    require(stat.S_IMODE(F.stat().st_mode)==0o700 and stat.S_IMODE((F/'nord3-busybox-candidate.img').stat().st_mode)==0o600,'Private artifact permissions differ')
    b,old=read_boot_v4(image),read_boot_v4(reference);current,previous=read_newc(decompress(b['ramdisk'])),read_newc(decompress(old['ramdisk']))
    require(b['kernel']==old['kernel'] and b['cmdline']==old['cmdline'],'Kernel/cmdline changed')
    require(image[:12]==reference[:12] and image[16:4096]==reference[16:4096],'Unrelated header changed')
    require(set(current)==set(previous),'Archive entries changed')
    for name in previous:
        if name not in ['init','etc/lynx/session-token']:require(current[name]==previous[name],'Unrelated entry changed: '+name)
    runtime=(P/'lynx-payload-timing-runtime.sh').read_bytes()
    expected=previous['init']['data']
    markers=[(1,b"    candidates=''\n"),(2,b'    [ -b "$device" ] || return 1\n'),(3,b'    [ "$($BB blockdev --getsize64 "$device")" = 67108864 ] || return 1\n'),(4,b'    bytes=$($BB cat /etc/lynx/payload-bytes) || return 1\n'),(5,b'    $BB dd if="$device" of=/run/lynx/payload-blocks bs=4096 skip=6144 count="$blocks" || return 1\n'),(6,b'    actual=$($BB sha256sum /run/lynx/payload.cpio.gz) || return 1\n'),(7,b'    $BB gzip -dc /run/lynx/payload.cpio.gz > /run/lynx/payload.cpio || return 1\n')]
    for code,anchor in markers:
        require(expected.count(anchor)==1,'Payload boundary changed')
        expected=expected.replace(anchor,("    printf '%s\\n' "+str(code)+" > /run/lynx/payload-progress || return 1\n").encode()+anchor)
    old_runtime=(P/'lynx-bootstrap-timing-runtime.sh').read_bytes()
    require(expected.count(old_runtime)==1,'Original timing boundary changed')
    expected=expected.replace(old_runtime,runtime)
    require(current['init']['data']==expected==(F/'init-source').read_bytes(),'Unexpected executable init')
    require(b'. /etc/lynx/wifi-runtime.sh' not in current['init']['data'] and b'lynx_wifi_supervise' not in current['init']['data'],'Radio reachable')
    require(runtime.count(b'/bin/boot-proof-reboot')==1 and b"printf 'b'" not in runtime and b"printf 'h'" not in runtime,'Reset scope differs')
    coverage=struct.unpack('!4sIIQQQ28x',reference[-64:])[3];require(image[coverage:]==reference[coverage:],'AVB/footer/payload changed')
    require(4096+((len(b['kernel'])+4095)//4096)*4096+((len(b['ramdisk'])+4095)//4096)*4096<=coverage,'Loaded area overlaps metadata')
    manifest=json.loads((F/'build-validation.json').read_text());require(manifest['candidate_sha256']==SHA and manifest['runtime_sha256']==sha(runtime) and manifest['init_sha256']==sha(current['init']['data']),'Manifest executable hashes differ')
    require(manifest['session_token']==current['etc/lynx/session-token']['data'].decode().strip(),'Boot token differs')
    codes={'0': 'bootstrap completed: own boot_a payload verified/extracted; no radio', '1': 'payload failed: candidate enumeration/uniqueness/device name', '2': 'payload failed: expected block device node absent', '3': 'payload failed: capacity or read-only block ioctl', '4': 'payload failed: size/hash metadata validation', '5': 'payload failed: raw block read or byte trimming', '6': 'payload failed: SHA256 calculation or mismatch', '7': 'payload failed: gzip decompression or cpio extraction', '8': 'other bootstrap failure, deadline or invalid progress'}
    require(manifest['result_codes']==codes and manifest['target_delays_seconds']=={str(i):240+5*i for i in range(9)} and manifest['observation_seconds']==360 and manifest['worker_sample_seconds']==180,'Timing/codebook differs')
    native=sorted((P/'artifacts').glob('emulated-payload-timing-native-*/result.json'));require(native,'Native test missing');n=json.loads(native[-1].read_text())
    require(n['passed'] and n['candidate_sha256']==SHA and n['source_sha256']==sha(runtime),'Native timing test differs')
    guards=sorted((P/'artifacts').glob('emulated-payload-timing-guard-*/result.json'));require(guards,'Exact image guard missing');g=json.loads(guards[-1].read_text())
    require(g['candidate_sha256']==SHA and g['module_checkpoint_failure_guard_observed'] and not g['kernel_reboot_command_observed'],'Reset guard failed')
    loops=sorted((P/'artifacts').glob('emulated-native-payload-step-loop-*/result.json'));require(loops,'Actual block I/O test missing')
    l=json.loads(loops[-1].read_text());reader=expected[expected.index(b'lynx_read_own_boot_payload() {'):expected.index(b'lynx_wifi_bootstrap_child_unlogged() {')]
    require(l['passed'] and l['candidate_sha256']==SHA and l['payload_reader_sha256']==sha(reader),'Actual block reader test differs')
    # Entire timing grid with accepted extremes, mid-slot rejection and no-return refusal.
    tests=0
    for code in range(9):
        for offset in [-2,-1,0,1,2,2.25,2.5]:
            elapsed=21.833501310+240+5*code+offset
            op={'started_monotonic':100.,'elapsed_seconds':.05,'finished_ns':100050000000}
            usb={'observation_complete':True,'fastboot_return_observed':True,'events':[{'usb':[{'identifier':'0e8d:201c'}],'monotonic_seconds':100.05+elapsed,'wall_time_ns':int((100.05+elapsed)*1e9)}]}
            got=decode_progress_timing(op,usb,manifest,21.833501310)
            require(got['timing_module_progress_field']==(code if abs(offset)<=2 else None),'Timing corpus disagrees');tests+=1
    try: decode_progress_timing(op,{'observation_complete':False},manifest,21.833501310)
    except ValueError:tests+=1
    else:raise ValueError('Incomplete trial accepted')
    model=R/'tools/avb-host/avb-boot-model';m=json.loads((P/'docs/avb-boot-model-results.json').read_text());require(sha(model.read_bytes())==m['binary_sha256'],'AVB model changed')
    for unlocked in ['1','0']:
        result=subprocess.run([str(model),str(P/'artifacts/stock-cph2493-August-eu-ota'),str(F/'nord3-busybox-candidate.img'),'0',unlocked],capture_output=True,text=True,timeout=30)
        require(result.returncode==0 and json.loads(result.stdout)['slot_data_returned']==(unlocked=='1'),'Boot policy changed')
    report={'passed':True,'candidate_sha256':SHA,'parent_v7_validation_passed':True,'native_receipt':str(native[-1]),'guard_receipt':str(guards[-1]),'timing_cases':tests,'kernel_metadata_payload_unchanged':True,'radio_started':False,'phone_contacted':False,'limits':'Timing inference requires normal reset evidence, no physical interference and calibrated startup. Guarded controller binding does not by itself prove payload access.'}
    out=P/'docs/payload-timing-validation.json';out.write_text(json.dumps(report,indent=2)+'\n');print(out)
if __name__=='__main__':main()
