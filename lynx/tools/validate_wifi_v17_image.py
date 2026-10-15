"""Verify RAM-only payload markers, unchanged service payload and fast slot mapping."""
import hashlib,json,stat,struct,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';sys.path.insert(0,str(P))
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
from lynx_payload_fast_timing import decode_progress_timing
SHA='e24e21797997312ec21bae8f07256a3cf17411462ac6c30518543fbb2677dcab'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
    parent=json.loads((P/'docs/wifi-v16-image-validation.json').read_text());require(parent['passed'] and parent['candidate_sha256']=='73311e9613a002a5bf3d3d4c4b5057840b7a427a06e1aff18a186e27e68614f6','Parent validation missing')
    F=P/'artifacts/busybox-wifi-ssh-twostage-v17';V=P/'artifacts/busybox-wifi-ssh-twostage-v16';raw=(F/'nord3-busybox-candidate.img').read_bytes();old=(V/'nord3-busybox-candidate.img').read_bytes();require(sha(raw)==SHA and sha(old)==parent['candidate_sha256'] and len(raw)==len(old)==67108864,'Image differs');require(stat.S_IMODE(F.stat().st_mode)==0o700 and stat.S_IMODE((F/'nord3-busybox-candidate.img').stat().st_mode)==0o600,'Permissions differ')
    b,o=read_boot_v4(raw),read_boot_v4(old);e,p=read_newc(decompress(b['ramdisk'])),read_newc(decompress(o['ramdisk']));require(b['kernel']==o['kernel'] and b['cmdline']==o['cmdline'] and raw[:12]==old[:12] and raw[16:4096]==old[16:4096],'Kernel/header changed');require(set(e)==set(p),'First-stage entry set changed')
    for n in p:
        if n not in ['init','bin/boot-proof-reboot','etc/lynx/session-token']:require(e[n]==p[n],'Unrelated first-stage change: '+n)
    init=p['init']['data'];anchor=b'lynx_read_own_boot_payload() {\n';require(init.count(anchor)==1,'Reader anchor differs')
    init=init.replace(anchor,b'''lynx_payload_step() {
    printf '%s\\n' "$1" > /run/lynx/payload-step
}
'''+anchor+b'    lynx_payload_step 1 || return 1\n')
    anchors=[b'    device=/dev/$1\n',b'    [ "$($BB blockdev --getsize64 "$device")" = 67108864 ]',b'    $BB blockdev --setro "$device"',b'    bytes=$($BB cat /etc/lynx/payload-bytes)',b'    blocks=$(((bytes+4095)/4096))',b'    actual=$($BB sha256sum /run/lynx/payload.cpio.gz)',b'    $BB gzip -dc /run/lynx/payload.cpio.gz',b'    (cd / && $BB cpio -idmu < /run/lynx/payload.cpio)',b'    log "BOOT_A_SUPPLEMENT_VERIFIED_AND_EXTRACTED']
    for step,anchor in enumerate(anchors,2):require(init.count(anchor)==1,'Reader step differs');init=init.replace(anchor,('    lynx_payload_step '+str(step)+' || return 1\n').encode()+anchor)
    require(e['init']['data']==init==(F/'init-source').read_bytes(),'Init delta differs')
    timing=p['bin/boot-proof-reboot']['data'];anchor=b'            151|152|153|154) nt_code=$((nt_boot-131)) ;;\n';require(timing.count(anchor)==1,'Result mapping differs')
    timing=timing.replace(anchor,b'''            154)
                nt_code=23
                if IFS= read -r nt_payload < /run/lynx/payload-step; then
                    case "$nt_payload" in 1|2|3|4|5|6|7|8|9|10) nt_code=$((39+nt_payload)) ;; esac
                fi ;;
            151|152|153) nt_code=$((nt_boot-131)) ;;
''').replace(b'nt_target=$((120+5*nt_code))',b'nt_target=$((80+5*nt_code))');require(e['bin/boot-proof-reboot']['data']==timing==(F/'timing-runtime-source').read_bytes(),'Timing delta differs')
    coverage=struct.unpack('!4sIIQQQ28x',old[-64:])[3];require(raw[coverage:]==old[coverage:],'Payload/metadata/footer changed');require((F/'supplement.cpio.gz').read_bytes()==(V/'supplement.cpio.gz').read_bytes(),'Supplement changed');require(4096+((len(b['kernel'])+4095)//4096)*4096+((len(b['ramdisk'])+4095)//4096)*4096<=coverage,'Metadata overlap')
    m=json.loads((F/'build-validation.json').read_text());grid={str(n):525 if n==9 else 80+5*n for n in range(50)};require(m['candidate_sha256']==SHA and m['init_sha256']==sha(init) and m['timing_runtime_sha256']==sha(timing) and m['session_token']==e['etc/lynx/session-token']['data'].decode().strip(),'Manifest differs');require(m['target_delays_seconds']==grid and m['observation_seconds']==660,'Timing grid differs')
    receipts={}
    for prefix in ['emulated-payload-fast-timing-native-','emulated-native-vendor-wifi-v17-loop-','emulated-wifi-v17-image-']:
        files=sorted((P/'artifacts').glob(prefix+'*/result.json'));require(files,'Native check missing');r=json.loads(files[-1].read_text());require(r['candidate_sha256']==SHA,'Test candidate differs')
        if prefix=='emulated-wifi-v17-image-':require(r['module_checkpoint_failure_guard_observed'] and not r['kernel_reboot_command_observed'],'Reset guard failed')
        else:require(r['passed'] and all(r['checks'].values()),'Native check failed')
        if prefix=='emulated-payload-fast-timing-native-':require(r['source_sha256']==sha(timing) and r['checks']['49_resets'],'Timing test source differs')
        if prefix=='emulated-native-vendor-wifi-v17-loop-':require(all(r['checks']['fault_'+str(n)] for n in range(1,11)),'Fault injection cases missing')
        receipts[prefix]=str(files[-1])
    for code in range(50):
        for delta in [-2,-1,0,1,2,2.1,2.5]:
            elapsed=21.833501310+grid[str(code)]+delta;operation={'started_monotonic':100.,'elapsed_seconds':.05,'finished_ns':100050000000};usb={'observation_complete':True,'fastboot_return_observed':True,'events':[{'usb':[{'identifier':'0e8d:201c'}],'monotonic_seconds':100.05+elapsed,'wall_time_ns':int((100.05+elapsed)*1e9)}]};got=decode_progress_timing(operation,usb,m,21.833501310);require(got['timing_module_progress_field']==(code if abs(delta)<=2 else None),'Decoder corpus failed')
    c=subprocess.run(['python3',str(R/'tools/lynx_wifi_v17_contact.py'),'--self-test'],capture_output=True,text=True,timeout=20);require(c.returncode==0,'Identity proof failed');wrapper=(R/'tools/lynx_boot_a_wifi_v17_trial.py').read_text();require(SHA in wrapper and 'time.monotonic()+660' in wrapper and 'lynx_payload_fast_timing' in wrapper,'Trial bounds/decoder differ')
    model=R/'tools/avb-host/avb-boot-model'
    for unlocked in ['1','0']:
        c=subprocess.run([str(model),str(P/'artifacts/stock-cph2493-August-eu-ota'),str(F/'nord3-busybox-candidate.img'),'0',unlocked],capture_output=True,text=True,timeout=30);require(c.returncode==0 and json.loads(c.stdout)['slot_data_returned']==(unlocked=='1'),'Boot policy differs')
    out=P/'docs/wifi-v17-image-validation.json';out.write_text(json.dumps({'passed':True,'candidate_sha256':SHA,'receipts':receipts,'timing_cases':350,'phone_contacted':False,'limits':'RAM-only reader markers; physical storage failure cause not yet known. Stock firmware-event service unchanged and not physically proved. Late results lose detail by design; reset evidence/physical non-interference/calibration remain required.'},indent=2)+'\n');print(out)
if __name__=='__main__':main()
