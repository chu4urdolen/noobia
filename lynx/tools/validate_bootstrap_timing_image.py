"""Independently verify startup delta, protected bytes, tested timing and reset guard."""
import argparse,hashlib,json,stat,struct,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';sys.path.insert(0,str(P))
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
from lynx_bootstrap_timing import decode_progress_timing
SHA='a9c233c6aefbae80e2e9cd1fabbb1dcda8cdac3119d9ea58bc5e95b73c96802a'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--count',type=int,choices=[34],required=True);parser.parse_args()
    parent=subprocess.run(['python3',str(R/'tools/validate_wifi_v7_image.py')],capture_output=True,text=True,timeout=60);require(parent.returncode==0,'v7 reference invalid: '+parent.stdout+parent.stderr)
    F=P/'artifacts/busybox-bootstrap-timing-v1';V=P/'artifacts/busybox-wifi-ssh-twostage-v7'
    image=(F/'nord3-busybox-candidate.img').read_bytes();reference=(V/'nord3-busybox-candidate.img').read_bytes()
    require(sha(image)==SHA and len(image)==67108864,'Image hash/size differs')
    require(stat.S_IMODE(F.stat().st_mode)==0o700 and stat.S_IMODE((F/'nord3-busybox-candidate.img').stat().st_mode)==0o600,'Private artifact permissions differ')
    b,old=read_boot_v4(image),read_boot_v4(reference);current,previous=read_newc(decompress(b['ramdisk'])),read_newc(decompress(old['ramdisk']))
    require(b['kernel']==old['kernel'] and b['cmdline']==old['cmdline'],'Kernel/cmdline changed')
    require(image[:12]==reference[:12] and image[16:4096]==reference[16:4096],'Unrelated header changed')
    require(set(current)==set(previous),'Archive entries changed')
    for name in previous:
        if name not in ['init','etc/lynx/session-token']:require(current[name]==previous[name],'Unrelated entry changed: '+name)
    runtime=(P/'lynx-bootstrap-timing-runtime.sh').read_bytes();prefix=previous['init']['data'].split(b"\nlog 'WIFI_TWO_STAGE_BOOTSTRAP_BEGIN'\n")[0]
    require(prefix.count(b'    /bin/boot-proof-reboot\n')==1,'Original bootstrap reset boundary changed')
    prefix=prefix.replace(b'    /bin/boot-proof-reboot\n',b'    lynx_bootstrap_timing_return\n')
    tail=b'''\nlynx_bootstrap_timing_clock || stop
printf '%s\n' "$bt_seconds" > /run/lynx/bootstrap-timing-start || stop
log 'WIFI_TWO_STAGE_BOOTSTRAP_BEGIN'
lynx_wifi_bootstrap || stop
log 'BOOTSTRAP_TIMING_PAYLOAD_READY; RADIO_NOT_STARTED'
lynx_bootstrap_timing_return
stop
'''
    require(current['init']['data']==prefix+b'\n'+runtime+tail==(F/'init-source').read_bytes(),'Unexpected executable init')
    require(b'. /etc/lynx/wifi-runtime.sh' not in current['init']['data'] and b'lynx_wifi_supervise' not in current['init']['data'],'Radio reachable')
    require(runtime.count(b'/bin/boot-proof-reboot')==1 and b"printf 'b'" not in runtime and b"printf 'h'" not in runtime,'Reset scope differs')
    coverage=struct.unpack('!4sIIQQQ28x',reference[-64:])[3];require(image[coverage:]==reference[coverage:],'AVB/footer/payload changed')
    require(4096+((len(b['kernel'])+4095)//4096)*4096+((len(b['ramdisk'])+4095)//4096)*4096<=coverage,'Loaded area overlaps metadata')
    manifest=json.loads((F/'build-validation.json').read_text());require(manifest['candidate_sha256']==SHA and manifest['runtime_sha256']==sha(runtime) and manifest['init_sha256']==sha(current['init']['data']),'Manifest executable hashes differ')
    require(manifest['session_token']==current['etc/lynx/session-token']['data'].decode().strip(),'Boot token differs')
    codes={'0':'bootstrap completed: own boot_a payload verified and extracted; radio not started','1':'bootstrap failed: base drivers (151)','2':'bootstrap failed: storage drivers or guards (152)','3':'bootstrap failed: partition discovery (153)','4':'bootstrap failed: own boot_a payload (154)','5':'bootstrap failed: other numeric status','6':'bootstrap result unavailable/deadline','7':'bootstrap result malformed'}
    require(manifest['result_codes']==codes and manifest['target_delays_seconds']=={str(i):240+5*i for i in range(8)} and manifest['observation_seconds']==360 and manifest['worker_sample_seconds']==180,'Timing/codebook differs')
    native=sorted((P/'artifacts').glob('emulated-bootstrap-timing-native-*/result.json'));require(native,'Native test missing');n=json.loads(native[-1].read_text())
    require(n['passed'] and n['candidate_sha256']==SHA and n['source_sha256']==sha(runtime),'Native timing test differs')
    guards=sorted((P/'artifacts').glob('emulated-bootstrap-timing-guard-*/result.json'));require(guards,'Exact image guard missing');g=json.loads(guards[-1].read_text())
    require(g['candidate_sha256']==SHA and g['module_checkpoint_failure_guard_observed'] and not g['kernel_reboot_command_observed'],'Reset guard failed')
    # Entire timing grid with accepted extremes, mid-slot rejection and no-return refusal.
    tests=0
    for code in range(8):
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
    out=P/'docs/bootstrap-timing-validation.json';out.write_text(json.dumps(report,indent=2)+'\n');print(out)
if __name__=='__main__':main()
