"""Independently validate bounded completion requests and fast diagnostic slots."""
import gzip,hashlib,json,stat,struct,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';sys.path.insert(0,str(P))
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
from lynx_fast_wifi_timing import decode_progress_timing
SHA='c08d19beb54ef6400912651539d6ce9f510632a94d04180f30b88114d48768f2'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
    parent=json.loads((P/'docs/wifi-v14-image-validation.json').read_text())
    require(parent['passed'] and parent['candidate_sha256']=='5bc287a9fea447edfe83eeb284d8371ea0ac093f3a17f74e3db66bb171cedded','Validated parent receipt missing')
    idle=json.loads((P/'docs/wifi-worker-idle-audit.json').read_text());require(idle['passed'] and idle['idle_return_offset']==228,'Worker idle audit missing')
    F=P/'artifacts/busybox-wifi-ssh-twostage-v15';V=P/'artifacts/busybox-wifi-ssh-twostage-v14';raw=(F/'nord3-busybox-candidate.img').read_bytes();old=(V/'nord3-busybox-candidate.img').read_bytes()
    require(sha(raw)==SHA and sha(old)==parent['candidate_sha256'] and len(raw)==len(old)==67108864,'Image changed');require(stat.S_IMODE(F.stat().st_mode)==0o700 and stat.S_IMODE((F/'nord3-busybox-candidate.img').stat().st_mode)==0o600,'Permissions changed')
    b,o=read_boot_v4(raw),read_boot_v4(old);e,p=read_newc(decompress(b['ramdisk'])),read_newc(decompress(o['ramdisk']))
    require(b['kernel']==o['kernel'] and b['cmdline']==o['cmdline'] and raw[:12]==old[:12] and raw[16:4096]==old[16:4096],'Kernel/header changed');require(set(e)==set(p),'Ramdisk entry set changed')
    for n in p:
        if n not in ['bin/boot-proof-reboot','etc/lynx/session-token','etc/lynx/payload-bytes','etc/lynx/payload-sha256']:require(e[n]==p[n],'Unrelated ramdisk change: '+n)
    fast=b'''    nt_target=$((120+5*nt_code))
    [ "$nt_code" != 9 ] || nt_target=525
    lynx_network_timing_clock || return 1
    if [ "$nt_seconds" -ge "$((nt_start+nt_target-3))" ]; then
        nt_code=9
        nt_target=525
    fi
    [ "$nt_seconds" -lt "$((nt_start+nt_target-3))" ] || return 1
'''
    prior=p['bin/boot-proof-reboot']['data'];anchor=b'    nt_target=$((480+5*nt_code))\n';timing=e['bin/boot-proof-reboot']['data'];require(prior.count(anchor)==1 and timing==prior.replace(anchor,fast)==(F/'timing-runtime-source').read_bytes(),'Timing delta differs')
    payload=(F/'supplement.cpio.gz').read_bytes();prev=(V/'supplement.cpio.gz').read_bytes();x,y=read_newc(gzip.decompress(payload)),read_newc(gzip.decompress(prev))
    require(set(x)-set(y)=={'etc/lynx/wifi-async-ready.sh','etc/lynx/wifi-station-async.sh'} and not set(y)-set(x),'Payload entry set differs')
    for n in y:
        if n!='etc/lynx/wifi-runtime.sh':require(x[n]==y[n],'Unrelated firmware/module/credential change: '+n)
    ready=(P/'wifi-async-ready.sh').read_bytes();station=(P/'wifi-station-async.sh').read_bytes()
    require(sha(x['lib/modules/wmt_chrdev_wifi_connac2.ko']['data'])==idle['worker_module_sha256'] and sha(x['lib/modules/wlan_drv_gen4m_6983.ko']['data'])==idle['wlan_module_sha256'],'Audited worker/driver differs')
    for name,data in [('wifi-async-ready.sh',ready),('wifi-station-async.sh',station)]:require(x['etc/lynx/'+name]['data']==data==(F/name).read_bytes(),'Runtime source differs')
    wifi=y['etc/lynx/wifi-runtime.sh']['data'];start=wifi.index(b'    station_token=');end=wifi.index(b'    lynx_stage WLAN_INTERFACE_WAIT\n',start)
    expected=wifi[:start]+b'    . /etc/lynx/wifi-station-async.sh || return 139\n    lynx_wifi_station_request || return 139\n'+wifi[end:]
    require(x['etc/lynx/wifi-runtime.sh']['data']==expected==(F/'wifi-runtime.sh').read_bytes(),'Worker delta differs')
    m=json.loads((F/'build-validation.json').read_text());grid={str(n):525 if n==9 else 120+5*n for n in range(40)}
    require(m['candidate_sha256']==SHA and m['timing_runtime_sha256']==sha(timing) and m['async_ready_sha256']==sha(ready) and m['station_request_sha256']==sha(station) and m['init_sha256']==sha(e['init']['data']),'Manifest differs')
    require(m['target_delays_seconds']==grid and m['observation_seconds']==660 and m['session_token']==e['etc/lynx/session-token']['data'].decode().strip(),'Timing/token differ')
    require(e['etc/lynx/payload-sha256']['data']==(sha(payload)+'\n').encode() and e['etc/lynx/payload-bytes']['data']==(str(len(payload))+'\n').encode() and m['supplement_sha256']==sha(payload),'Payload metadata differs')
    coverage=struct.unpack('!4sIIQQQ28x',old[-64:])[3];off=25165824
    require(raw[off:off+len(payload)]==payload and raw[coverage:off]==old[coverage:off] and raw[off+max(len(payload),len(prev)):]==old[off+max(len(payload),len(prev)):],'Protected bytes changed')
    require(4096+((len(b['kernel'])+4095)//4096)*4096+((len(b['ramdisk'])+4095)//4096)*4096<=coverage,'Metadata overlap')
    receipts={}
    for prefix in ['emulated-fast-wifi-timing-native-','emulated-native-vendor-wifi-v15-loop-','emulated-wifi-v15-image-']:
        files=sorted((P/'artifacts').glob(prefix+'*/result.json'));require(files,'Native test missing');r=json.loads(files[-1].read_text());require(r['candidate_sha256']==SHA,'Native image differs')
        if prefix=='emulated-wifi-v15-image-':require(r['module_checkpoint_failure_guard_observed'] and not r['kernel_reboot_command_observed'],'Reset guard failed')
        else:require(r['passed'] and all(r['checks'].values()),'Native test failed')
        if prefix=='emulated-fast-wifi-timing-native-':require(r['source_sha256']==sha(timing) and r['checks']['late_result_uses_separate_slot'] and r['checks']['missed_all_slots_refused'],'Fast timing controls differ')
        receipts[prefix]=str(files[-1])
    for prefix,source in [('wifi-async-ready-',ready),('wifi-station-async-',station)]:
        f=sorted((R/'tools/test-artifacts').glob(prefix+'*/result.json'))[-1];r=json.loads(f.read_text());require(r['passed'] and r['source_sha256']==sha(source),'Runtime controls differ')
        if prefix=='wifi-async-ready-':require(len(r['cases'])>=20 and all(r['native_checks'].values()) and r['kernel_sha256']==sha(b['kernel']),'Native readiness controls missing')
        receipts[prefix]=str(f)
    for code in range(40):
        for delta in [-2,-1,0,1,2,2.1,2.5]:
            elapsed=21.833501310+grid[str(code)]+delta;operation={'started_monotonic':100.,'elapsed_seconds':.05,'finished_ns':100050000000};usb={'observation_complete':True,'fastboot_return_observed':True,'events':[{'usb':[{'identifier':'0e8d:201c'}],'monotonic_seconds':100.05+elapsed,'wall_time_ns':int((100.05+elapsed)*1e9)}]};got=decode_progress_timing(operation,usb,m,21.833501310);require(got['timing_module_progress_field']==(code if abs(delta)<=2 else None),'Decoder corpus failed')
    c=subprocess.run(['python3',str(R/'tools/lynx_wifi_v15_contact.py'),'--self-test'],capture_output=True,text=True,timeout=20);require(c.returncode==0,'Identity checks failed')
    wrapper=(R/'tools/lynx_boot_a_wifi_v15_trial.py').read_text();require(SHA in wrapper and 'time.monotonic()+660' in wrapper and 'lynx_fast_wifi_timing' in wrapper,'Trial bounds/decoder differ')
    model=R/'tools/avb-host/avb-boot-model'
    for unlocked in ['1','0']:
        c=subprocess.run([str(model),str(P/'artifacts/stock-cph2493-August-eu-ota'),str(F/'nord3-busybox-candidate.img'),'0',unlocked],capture_output=True,text=True,timeout=30);require(c.returncode==0 and json.loads(c.stdout)['slot_data_returned']==(unlocked=='1'),'Boot policy differs')
    out=P/'docs/wifi-v15-image-validation.json';out.write_text(json.dumps({'passed':True,'candidate_sha256':SHA,'receipts':receipts,'timing_cases':280,'phone_contacted':False,'limits':'At most one evidence-gated completion request after the initial timeout. Raw snapshots remain RAM-only until SSH retrieval. Early slots require a 3s margin; late detail is deliberately replaced by slot9. Legacy timing source comment about all slots following 420s is superseded by this explicit runtime deadline guard.'},indent=2)+'\n');print(out)
if __name__=='__main__':main()
