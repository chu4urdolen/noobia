"""Independent WPA diagnostic delta and prioritized timing verification."""
import gzip,hashlib,json,stat,struct,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';sys.path.insert(0,str(P))
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
from lynx_wpa_timing import decode_progress_timing
SHA='62bfed751f3793f63132d2ca3181a5aa869f4f5ce6efcb640abbcaecc9ba4f40'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
    parent=json.loads((P/'docs/wifi-v17-image-validation.json').read_text());require(parent['passed'] and parent['candidate_sha256']=='e24e21797997312ec21bae8f07256a3cf17411462ac6c30518543fbb2677dcab','Parent validation differs')
    F=P/'artifacts/busybox-wifi-ssh-twostage-v18';V=P/'artifacts/busybox-wifi-ssh-twostage-v17';raw=(F/'nord3-busybox-candidate.img').read_bytes();old=(V/'nord3-busybox-candidate.img').read_bytes();require(sha(raw)==SHA and sha(old)==parent['candidate_sha256'] and len(raw)==len(old)==67108864,'Image differs');require(stat.S_IMODE(F.stat().st_mode)==0o700 and stat.S_IMODE((F/'nord3-busybox-candidate.img').stat().st_mode)==0o600,'Permissions differ')
    b,o=read_boot_v4(raw),read_boot_v4(old);e,p=read_newc(decompress(b['ramdisk'])),read_newc(decompress(o['ramdisk']));require(b['kernel']==o['kernel'] and b['cmdline']==o['cmdline'] and raw[:12]==old[:12] and raw[16:4096]==old[16:4096],'Kernel/header changed');require(set(e)==set(p),'Entry set differs')
    for n in p:
        if n not in ['bin/boot-proof-reboot','etc/lynx/session-token','etc/lynx/payload-bytes','etc/lynx/payload-sha256']:require(e[n]==p[n],'Unrelated first-stage change: '+n)
    timing=p['bin/boot-proof-reboot']['data'];anchor=b'                            elif [ "$nt_worker" = 135 ]; then\n';require(timing.count(anchor)==1,'Worker mapping differs');timing=timing.replace(anchor,b'''                            elif [ "$nt_worker" = 143 ]; then
                                nt_code=59
                                if IFS= read -r nt_wpa < /run/lynx/wpa-failure-code; then
                                    case "$nt_wpa" in 50|51|52|53|54|55|56|57|58|59) nt_code=$nt_wpa ;; esac
                                fi
'''+anchor)
    anchor=b'    nt_target=$((80+5*nt_code))\n    [ "$nt_code" != 9 ] || nt_target=525\n';require(timing.count(anchor)==1,'Timing boundary differs');timing=timing.replace(anchor,b'''    case "$nt_code" in
        9) nt_target=525 ;;
        50|51|52|53|54|55|56|57|58|59) nt_target=$((160+5*(nt_code-50))) ;;
        40|41|42|43|44|45|46|47|48|49) nt_target=$((210+5*(nt_code-40))) ;;
        25|26|27|28|29|30|31|32|33|34|35|36|37|38|39) nt_target=$((260+5*(nt_code-25))) ;;
        *) nt_target=$((335+5*nt_code)) ;;
    esac
''');require(e['bin/boot-proof-reboot']['data']==timing==(F/'timing-runtime-source').read_bytes(),'Timing executable differs')
    payload=(F/'supplement.cpio.gz').read_bytes();prev=(V/'supplement.cpio.gz').read_bytes();x,y=read_newc(gzip.decompress(payload)),read_newc(gzip.decompress(prev));require(set(x)-set(y)=={'etc/lynx/wpa-diagnostics.sh','etc/lynx/wpa-target-ssid'} and not set(y)-set(x),'Supplement entry set differs')
    for n in y:
        if n!='etc/lynx/wifi-runtime.sh':require(x[n]==y[n],'Unrelated module/firmware/credential/startup change: '+n)
    diag=(P/'wpa-diagnostics.sh').read_bytes();require(x['etc/lynx/wpa-diagnostics.sh']['data']==diag==(F/'wpa-diagnostics.sh').read_bytes() and x['etc/lynx/wpa-target-ssid']['data']==b'Noobia\n','Diagnostic/target differs')
    wifi=y['etc/lynx/wifi-runtime.sh']['data'];anchor=b'    [ "$connected" = 1 ] || return 143\n';require(wifi.count(anchor)==1,'Association boundary differs');wifi=wifi.replace(anchor,b'''    if [ "$connected" != 1 ]; then
        . /etc/lynx/wpa-diagnostics.sh || return 143
        lynx_wpa_snapshot || return 143
        [ "$nt_wpa" = 51 ] || return 143
    fi
''').replace(b'/sbin/wpa_supplicant -B -D',b'/sbin/wpa_supplicant -B -d -D');require(x['etc/lynx/wifi-runtime.sh']['data']==wifi==(F/'wifi-runtime.sh').read_bytes(),'Worker executable differs')
    m=json.loads((F/'build-validation.json').read_text());grid={str(n):525 if n==9 else 160+5*(n-50) if n>=50 else 210+5*(n-40) if n>=40 else 260+5*(n-25) if n>=25 else 335+5*n for n in range(60)};require(m['candidate_sha256']==SHA and m['timing_runtime_sha256']==sha(timing) and m['wpa_diagnostics_sha256']==sha(diag) and m['init_sha256']==sha(e['init']['data']),'Manifest differs');require(m['target_delays_seconds']==grid and m['observation_seconds']==660,'Timing bounds differ');require(m['session_token']==e['etc/lynx/session-token']['data'].decode().strip() and m['supplement_sha256']==sha(payload) and e['etc/lynx/payload-sha256']['data']==(sha(payload)+'\n').encode() and e['etc/lynx/payload-bytes']['data']==(str(len(payload))+'\n').encode(),'Metadata differs')
    coverage=struct.unpack('!4sIIQQQ28x',old[-64:])[3];off=25165824;require(raw[off:off+len(payload)]==payload and raw[coverage:off]==old[coverage:off] and raw[off+max(len(payload),len(prev)):]==old[off+max(len(payload),len(prev)):],'Protected bytes changed');require(4096+((len(b['kernel'])+4095)//4096)*4096+((len(b['ramdisk'])+4095)//4096)*4096<=coverage,'Metadata overlap')
    receipts={}
    for prefix in ['emulated-wpa-timing-native-','emulated-native-vendor-wifi-v18-loop-','emulated-wifi-v18-image-']:
        files=sorted((P/'artifacts').glob(prefix+'*/result.json'));require(files,'Native check missing');r=json.loads(files[-1].read_text());require(r['candidate_sha256']==SHA,'Native candidate differs')
        if prefix=='emulated-wifi-v18-image-':require(r['module_checkpoint_failure_guard_observed'] and not r['kernel_reboot_command_observed'],'Reset guard failed')
        else:require(r['passed'] and all(r['checks'].values()),'Native check failed')
        if prefix=='emulated-wpa-timing-native-':require(r['source_sha256']==sha(timing) and r['checks']['58_resets'],'Timing tests differ')
        receipts[prefix]=str(files[-1])
    f=sorted((R/'tools/test-artifacts').glob('wpa-diagnostics-*/result.json'))[-1];r=json.loads(f.read_text());require(r['passed'] and r['source_sha256']==sha(diag) and r['kernel_sha256']==sha(b['kernel']) and r['host_cases']>=24 and all(r['checks'].values()),'WPA controls differ');receipts['wpa_cases']=str(f)
    for code in range(60):
        for delta in [-2,-1,0,1,2,2.1,2.5]:
            elapsed=21.833501310+grid[str(code)]+delta;operation={'started_monotonic':100.,'elapsed_seconds':.05,'finished_ns':100050000000};usb={'observation_complete':True,'fastboot_return_observed':True,'events':[{'usb':[{'identifier':'0e8d:201c'}],'monotonic_seconds':100.05+elapsed,'wall_time_ns':int((100.05+elapsed)*1e9)}]};got=decode_progress_timing(operation,usb,m,21.833501310);require(got['timing_module_progress_field']==(code if abs(delta)<=2 else None),'Timing decoder failed')
    c=subprocess.run(['python3',str(R/'tools/lynx_wifi_v18_contact.py'),'--self-test'],capture_output=True,text=True,timeout=20);require(c.returncode==0,'Identity proof failed');wrapper=(R/'tools/lynx_boot_a_wifi_v18_trial.py').read_text();require(SHA in wrapper and 'time.monotonic()+660' in wrapper and 'lynx_wpa_timing' in wrapper,'Trial policy differs')
    model=R/'tools/avb-host/avb-boot-model'
    for unlocked in ['1','0']:
        c=subprocess.run([str(model),str(P/'artifacts/stock-cph2493-August-eu-ota'),str(F/'nord3-busybox-candidate.img'),'0',unlocked],capture_output=True,text=True,timeout=30);require(c.returncode==0 and json.loads(c.stdout)['slot_data_returned']==(unlocked=='1'),'Boot policy differs')
    out=P/'docs/wifi-v18-image-validation.json';out.write_text(json.dumps({'passed':True,'candidate_sha256':SHA,'receipts':receipts,'timing_cases':420,'phone_contacted':False,'limits':'Current WPA status/cached scan, not active scan or independent association proof. Logs and snapshots remain private RAM until authenticated retrieval. Legacy13/35 not normally produced; late completed snapshot51 continues DHCP. Late-slot/calibration limits unchanged.'},indent=2)+'\n');print(out)
if __name__=='__main__':main()
