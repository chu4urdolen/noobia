"""Validate the direct timing wrapper against the fully reviewed corrected Wi-Fi image."""
import argparse,hashlib,json,stat,struct,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';sys.path.insert(0,str(P))
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
from lynx_network_failure_timing import decode_progress_timing
SHA='4aad96c499317fa7f6d46371657a8e8bb93043b99de6627f801c5508f40a1033'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
    argparse.ArgumentParser().parse_args()
    parent=subprocess.run(['python3',str(R/'tools/validate_wifi_v10_image.py')],capture_output=True,text=True,timeout=60);require(parent.returncode==0,'Corrected payload reference invalid: '+parent.stdout+parent.stderr)
    F=P/'artifacts/busybox-wifi-ssh-twostage-v11';V=P/'artifacts/busybox-wifi-ssh-twostage-v10'
    image=(F/'nord3-busybox-candidate.img').read_bytes();old=(V/'nord3-busybox-candidate.img').read_bytes();require(sha(image)==SHA and len(image)==67108864,'Pinned image differs')
    require(stat.S_IMODE(F.stat().st_mode)==0o700 and stat.S_IMODE((F/'nord3-busybox-candidate.img').stat().st_mode)==0o600,'Private image permissions differ')
    boot,previous=read_boot_v4(image),read_boot_v4(old);entries,prior=read_newc(decompress(boot['ramdisk'])),read_newc(decompress(previous['ramdisk']))
    require(boot['kernel']==previous['kernel'] and boot['cmdline']==previous['cmdline'],'Kernel/cmdline changed')
    require(image[:12]==old[:12] and image[16:4096]==old[16:4096],'Unrelated header changed')
    require(set(entries)-set(prior)=={'bin/boot-proof-reboot-native'} and not set(prior)-set(entries),'First-stage files differ')
    for name in prior:
        if name not in ['init','etc/lynx/session-token','bin/boot-proof-reboot']:require(entries[name]==prior[name],'Unrelated module/key/config changed: '+name)
    native=entries['bin/boot-proof-reboot-native'];require(native==prior['bin/boot-proof-reboot'] and native['data'][:4]==b'\x7fELF','Native helper changed')
    runtime=(P/'lynx-network-failure-timing.sh').read_bytes()
    require(entries['bin/boot-proof-reboot']['data']==runtime==(F/'timing-runtime-source').read_bytes() and entries['bin/boot-proof-reboot']['mode']==0o100755,'Timing wrapper differs')
    require(runtime.count(b'/bin/boot-proof-reboot-native')==1 and b"printf 'b'" not in runtime and b"printf 'h'" not in runtime,'Reset scope differs')
    anchor=b"\nlog 'WIFI_TWO_STAGE_BOOTSTRAP_BEGIN'\n"
    startup=b'''
IFS=' ' read -r nt_initial_uptime nt_initial_unused < /proc/uptime || stop
nt_initial_seconds=MARKER{nt_initial_uptime%%.*}
case "$nt_initial_seconds" in ''|*[!0-9]*) stop ;; esac
printf '%s\\n' "$nt_initial_seconds" > /run/lynx/network-timing-start || stop
'''.replace(b'MARKER',b'$')
    require(prior['init']['data'].count(anchor)==1,'Anchor differs')
    require(entries['init']['data']==prior['init']['data'].replace(anchor,startup+anchor)==(F/'init-source').read_bytes(),'Unexpected startup code delta')
    coverage=struct.unpack('!4sIIQQQ28x',old[-64:])[3];require(image[coverage:]==old[coverage:],'AVB/footer/payload changed')
    require((F/'supplement.cpio.gz').read_bytes()==(V/'supplement.cpio.gz').read_bytes(),'Supplement changed')
    require(4096+((len(boot['kernel'])+4095)//4096)*4096+((len(boot['ramdisk'])+4095)//4096)*4096<=coverage,'Loaded metadata overlap')
    manifest=json.loads((F/'build-validation.json').read_text())
    require(manifest['init_sha256']==sha(entries['init']['data']) and manifest['candidate_sha256']==SHA and manifest['timing_runtime_sha256']==sha(runtime) and manifest['native_reboot_helper_sha256']==sha(native['data']),'Manifest executable hashes differ')
    require(manifest['session_token']==entries['etc/lynx/session-token']['data'].decode().strip(),'Token differs')
    labels=['Wi-Fi worker returned0 but pinned host did not confirm','base driver worker131','storage driver worker132','device scan worker133','factory calibration worker134','radio module worker135','device scan worker136','chip ioctl worker137','calibration submission worker138','station power worker139','WLAN interface worker140','interface up worker141','WPA startup worker142','WPA association worker143','DHCP worker144','address worker145','Dropbear startup worker146','other Wi-Fi worker status','Wi-Fi worker result unavailable/deadline','other bootstrap failure','bootstrap base151','bootstrap storage152','bootstrap partition153','bootstrap payload154','bootstrap result unavailable/deadline']
    require(manifest['result_codes']=={str(i):v for i,v in enumerate(labels)} and manifest['target_delays_seconds']=={str(i):480+5*i for i in range(25)} and manifest['observation_seconds']==720,'Failure timing geometry/codebook differs')
    requirements=[('emulated-network-failure-timing-native-',True),('emulated-native-vendor-wifi-v11-loop-',True),('emulated-wifi-v11-journals-',True),('emulated-wifi-v11-image-',False)]
    receipts={}
    for prefix,passed in requirements:
        paths=sorted((P/'artifacts').glob(prefix+'*/result.json'));require(paths,'Missing test: '+prefix);r=json.loads(paths[-1].read_text());require(r['candidate_sha256']==SHA,'Tested image differs')
        if passed:require(r['passed'] and all(r['checks'].values()),'Native test failed: '+prefix)
        else:require(r['module_checkpoint_failure_guard_observed'] and not r['kernel_reboot_command_observed'],'Exact reset guard failed')
        if prefix=='emulated-network-failure-timing-native-':require(r['source_sha256']==sha(runtime),'Native timing source differs')
        receipts[prefix]=str(paths[-1])
    cases=0
    for code in range(25):
        for offset in [-2,-1,0,1,2,2.25,2.5]:
            elapsed=21.833501310+480+5*code+offset
            op={'started_monotonic':100.,'elapsed_seconds':.05,'finished_ns':100050000000}
            usb={'observation_complete':True,'fastboot_return_observed':True,'events':[{'usb':[{'identifier':'0e8d:201c'}],'monotonic_seconds':100.05+elapsed,'wall_time_ns':int((100.05+elapsed)*1e9)}]}
            got=decode_progress_timing(op,usb,manifest,21.833501310);require(got['timing_module_progress_field']==(code if abs(offset)<=2 else None),'Timing corpus disagrees');cases+=1
    try:decode_progress_timing(op,{'observation_complete':False},manifest,21.833501310)
    except ValueError:cases+=1
    else:raise ValueError('Incomplete trial accepted')
    trial=(R/'tools/lynx_boot_a_wifi_v11_trial.py').read_text()
    require('up to 720 seconds' in trial and 'time.monotonic()+720' in trial,'Host observer bound differs')
    check=subprocess.run(['python3',str(R/'tools/lynx_wifi_v11_contact.py'),'--self-test'],capture_output=True,text=True,timeout=20);require(check.returncode==0,'Pinned identity tests failed')
    model=R/'tools/avb-host/avb-boot-model';m=json.loads((P/'docs/avb-boot-model-results.json').read_text());require(sha(model.read_bytes())==m['binary_sha256'],'AVB model changed')
    for unlocked in ['1','0']:
        result=subprocess.run([str(model),str(P/'artifacts/stock-cph2493-August-eu-ota'),str(F/'nord3-busybox-candidate.img'),'0',unlocked],capture_output=True,text=True,timeout=30);require(result.returncode==0 and json.loads(result.stdout)['slot_data_returned']==(unlocked=='1'),'Boot policy changed')
    out=P/'docs/wifi-v11-image-validation.json';out.write_text(json.dumps({'passed':True,'candidate_sha256':SHA,'native_receipts':receipts,'timing_cases':cases,'parent_v10_validation_passed':True,'kernel_modules_payload_credentials_unchanged':True,'phone_contacted':False,'limits':'Native fixtures validate timing classification; physical Wi-Fi and startup timing inference still require hardware evidence.'},indent=2)+'\n');print(out)
if __name__=='__main__':main()
