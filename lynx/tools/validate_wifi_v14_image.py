"""Independent validation of V14's procfs-only diagnostic delta."""
import gzip,hashlib,json,stat,struct,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';sys.path.insert(0,str(P))
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
SHA='5bc287a9fea447edfe83eeb284d8371ea0ac093f3a17f74e3db66bb171cedded'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
    for script in ['validate_wifi_v13_image.py','audit_wifi_worker_wait.py']:
        c=subprocess.run(['python3',str(R/'tools'/script)],capture_output=True,text=True,timeout=60);require(c.returncode==0,'Parent/audit failed: '+c.stdout+c.stderr)
    F=P/'artifacts/busybox-wifi-ssh-twostage-v14';V=P/'artifacts/busybox-wifi-ssh-twostage-v13';raw=(F/'nord3-busybox-candidate.img').read_bytes();old=(V/'nord3-busybox-candidate.img').read_bytes()
    require(sha(raw)==SHA and len(raw)==len(old)==67108864,'Image changed')
    require(stat.S_IMODE(F.stat().st_mode)==0o700 and stat.S_IMODE((F/'nord3-busybox-candidate.img').stat().st_mode)==0o600,'Permissions changed')
    b,o=read_boot_v4(raw),read_boot_v4(old);e,p=read_newc(decompress(b['ramdisk'])),read_newc(decompress(o['ramdisk']))
    require(b['kernel']==o['kernel'] and b['cmdline']==o['cmdline'] and raw[:12]==old[:12] and raw[16:4096]==old[16:4096],'Kernel/header changed')
    require(set(e)==set(p),'First-stage entry set changed')
    for n in p:
        if n not in ['bin/boot-proof-reboot','etc/lynx/session-token','etc/lynx/payload-bytes','etc/lynx/payload-sha256']:require(e[n]==p[n],'Unrelated first-stage change: '+n)
    prior=(V/'power-failure-parser.sh').read_bytes();timing=e['bin/boot-proof-reboot']['data']
    stub=b'''# Parser lives in the verified supplemental RAM archive.
lynx_station_failure_code() {
    nt_station_code=34
    . /etc/lynx/power-stack-parser.sh || return 0
    lynx_stack_failure_code
}
'''
    require(p['bin/boot-proof-reboot']['data'].count(prior)==1 and timing==p['bin/boot-proof-reboot']['data'].replace(prior,stub)==(F/'timing-runtime-source').read_bytes(),'Unexpected timing delta')
    payload=(F/'supplement.cpio.gz').read_bytes();prev=(V/'supplement.cpio.gz').read_bytes();x,y=read_newc(gzip.decompress(payload)),read_newc(gzip.decompress(prev))
    require(set(x)-set(y)=={'etc/lynx/power-stack-parser.sh','etc/lynx/wifi-worker-stack.sh'} and not set(y)-set(x),'Supplementary entry set changed')
    for n in y:
        if n!='etc/lynx/wifi-runtime.sh':require(x[n]==y[n],'Unrelated firmware/module/credential change: '+n)
    capture=(P/'wifi-worker-stack.sh').read_bytes();stackparser=(P/'power-stack-parser.sh').read_bytes();parser=prior.replace(b'lynx_station_failure_code()',b'lynx_power_failure_code()')+stackparser
    require(x['etc/lynx/power-stack-parser.sh']['data']==parser==(F/'power-stack-parser.sh').read_bytes(),'Parser changed')
    require(x['etc/lynx/wifi-worker-stack.sh']['data']==capture==(F/'wifi-worker-stack.sh').read_bytes(),'Capture changed')
    anchor=b'        $BB dmesg | $BB tail -c 1048576 > /run/lynx/station-dmesg\n';wifi=y['etc/lynx/wifi-runtime.sh']['data'];require(wifi.count(anchor)==1,'Capture boundary changed')
    wifi=wifi.replace(anchor,anchor+b'        if . /etc/lynx/wifi-worker-stack.sh; then lynx_capture_wifi_worker_stack; fi\n')
    require(x['etc/lynx/wifi-runtime.sh']['data']==wifi==(F/'wifi-runtime.sh').read_bytes() and wifi.count(b'/bin/lynx-wifi-control --station')==1,'Startup/attempt count changed')
    coverage=struct.unpack('!4sIIQQQ28x',old[-64:])[3];offset=25165824
    require(raw[offset:offset+len(payload)]==payload and raw[coverage:offset]==old[coverage:offset] and raw[offset+max(len(payload),len(prev)):]==old[offset+max(len(payload),len(prev)):],'Protected bytes changed')
    require(4096+((len(b['kernel'])+4095)//4096)*4096+((len(b['ramdisk'])+4095)//4096)*4096<=coverage,'Loaded metadata overlap')
    m=json.loads((F/'build-validation.json').read_text())
    require(m['candidate_sha256']==SHA and m['timing_runtime_sha256']==sha(timing) and m['station_parser_sha256']==sha(parser) and m['worker_stack_capture_sha256']==sha(capture) and m['init_sha256']==sha(e['init']['data']),'Manifest changed')
    require(m['session_token']==e['etc/lynx/session-token']['data'].decode().strip(),'Token differs')
    require(m['supplement_sha256']==sha(payload) and e['etc/lynx/payload-sha256']['data']==(sha(payload)+'\n').encode() and e['etc/lynx/payload-bytes']['data']==(str(len(payload))+'\n').encode(),'Payload metadata differs')
    require(m['target_delays_seconds']=={str(i):480+5*i for i in range(40)} and m['observation_seconds']==780,'Timing changed')
    receipts={}
    for prefix in ['emulated-stack-failure-timing-native-','emulated-native-vendor-wifi-v14-loop-','emulated-wifi-v14-image-']:
        files=sorted((P/'artifacts').glob(prefix+'*/result.json'));require(files,'Native test missing');r=json.loads(files[-1].read_text());require(r['candidate_sha256']==SHA,'Native image differs')
        if prefix=='emulated-wifi-v14-image-':require(r['module_checkpoint_failure_guard_observed'] and not r['kernel_reboot_command_observed'],'Reset guard failed')
        else:require(r['passed'] and all(r['checks'].values()),'Native check failed')
        if prefix=='emulated-stack-failure-timing-native-':require(r['source_sha256']==sha(timing) and r['checks']['38_resets'],'Native timing source differs')
        receipts[prefix]=str(files[-1])
    f=sorted((P/'artifacts').glob('emulated-native-proc-stack-*/result.json'))[-1];r=json.loads(f.read_text());require(r['passed'] and r['kernel_sha256']==sha(b['kernel']),'Stock procfs stack access unproved');receipts['procfs']=str(f)
    f=sorted((R/'tools/test-artifacts').glob('wifi-worker-stack-*/result.json'))[-1];r=json.loads(f.read_text());require(r['passed'] and r['capture_sha256']==sha(capture) and r['parser_sha256']==sha(stackparser) and len(r['checks'])>=19,'Host controls differ');receipts['host_controls']=str(f)
    c=subprocess.run(['python3',str(R/'tools/lynx_wifi_v14_contact.py'),'--self-test'],capture_output=True,text=True,timeout=20);require(c.returncode==0,'Identity checks failed')
    wrapper=(R/'tools/lynx_boot_a_wifi_v14_trial.py').read_text();require(SHA in wrapper and 'time.monotonic()+780' in wrapper and 'validate_wifi_v14_image.py' in wrapper,'Trial wrapper changed')
    model=R/'tools/avb-host/avb-boot-model'
    for unlocked in ['1','0']:
        c=subprocess.run([str(model),str(P/'artifacts/stock-cph2493-August-eu-ota'),str(F/'nord3-busybox-candidate.img'),'0',unlocked],capture_output=True,text=True,timeout=30);require(c.returncode==0 and json.loads(c.stdout)['slot_data_returned']==(unlocked=='1'),'Boot policy differs')
    out=P/'docs/wifi-v14-image-validation.json';out.write_text(json.dumps({'passed':True,'candidate_sha256':SHA,'receipts':receipts,'phone_contacted':False,'limits':'Procfs snapshots are sampled after timeout, not complete execution traces. Exact pre-cal sleep return offset independently audited. Slots9/35 are not produced. Physical Wi-Fi/SSH remain unverified.'},indent=2)+'\n');print(out)
if __name__=='__main__':main()
