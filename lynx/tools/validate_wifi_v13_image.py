"""Independent V12-to-V13 comparison: only parser and session token may change."""
import gzip,hashlib,json,stat,struct,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';sys.path.insert(0,str(P))
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
from lynx_station_failure_timing import decode_progress_timing
SHA='3b7d7962c8526e01b60f953f5f6b660e10cc6d599f7539d290f03857147165bb'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
    p=subprocess.run(['python3',str(R/'tools/validate_wifi_v12_image.py')],capture_output=True,text=True,timeout=60);require(p.returncode==0,'Parent failed: '+p.stdout+p.stderr)
    F=P/'artifacts/busybox-wifi-ssh-twostage-v13';V=P/'artifacts/busybox-wifi-ssh-twostage-v12'
    raw=(F/'nord3-busybox-candidate.img').read_bytes();old=(V/'nord3-busybox-candidate.img').read_bytes()
    require(sha(raw)==SHA and len(raw)==len(old)==67108864,'Image changed')
    require(stat.S_IMODE(F.stat().st_mode)==0o700 and stat.S_IMODE((F/'nord3-busybox-candidate.img').stat().st_mode)==0o600,'Permissions changed')
    b,o=read_boot_v4(raw),read_boot_v4(old);e,p=read_newc(decompress(b['ramdisk'])),read_newc(decompress(o['ramdisk']))
    require(b['kernel']==o['kernel'] and b['cmdline']==o['cmdline'] and raw[:12]==old[:12] and raw[16:4096]==old[16:4096],'Kernel or header changed')
    require(set(e)==set(p),'Ramdisk entries changed')
    for n in p:
        if n not in ['bin/boot-proof-reboot','etc/lynx/session-token']:require(e[n]==p[n],'Unrelated ramdisk change: '+n)
    parser=(P/'power-failure-parser.sh').read_bytes();prior=(V/'station-failure-parser.sh').read_bytes();timing=e['bin/boot-proof-reboot']['data']
    require(p['bin/boot-proof-reboot']['data'].count(prior)==1,'Parent parser boundary changed')
    require(timing==p['bin/boot-proof-reboot']['data'].replace(prior,parser)==(F/'timing-runtime-source').read_bytes(),'Unexpected executable delta')
    coverage=struct.unpack('!4sIIQQQ28x',old[-64:])[3]
    require(raw[coverage:]==old[coverage:],'Supplement/metadata/footer changed')
    require(4096+((len(b['kernel'])+4095)//4096)*4096+((len(b['ramdisk'])+4095)//4096)*4096<=coverage,'Metadata overlap')
    for n in ['supplement.cpio.gz','wifi-runtime.sh','init-source','radio-clock-guard.sh','diag-hooks.sh']:require((F/n).read_bytes()==(V/n).read_bytes(),'Startup/reference changed: '+n)
    require((F/'power-failure-parser.sh').read_bytes()==parser,'Parser reference changed')
    m=json.loads((F/'build-validation.json').read_text())
    require(m['candidate_sha256']==SHA and m['timing_runtime_sha256']==sha(timing) and m['station_parser_sha256']==sha(parser) and m['init_sha256']==sha(e['init']['data']),'Manifest changed')
    require(m['session_token']==e['etc/lynx/session-token']['data'].decode().strip(),'Session differs')
    require(m['target_delays_seconds']=={str(i):480+5*i for i in range(40)} and m['observation_seconds']==780,'Timing changed')
    receipts={}
    for prefix in ['emulated-power-failure-timing-native-','emulated-wifi-v13-image-']:
        files=sorted((P/'artifacts').glob(prefix+'*/result.json'));require(files,'Native test missing');r=json.loads(files[-1].read_text());require(r['candidate_sha256']==SHA,'Native image differs')
        if prefix=='emulated-wifi-v13-image-':require(r['module_checkpoint_failure_guard_observed'] and not r['kernel_reboot_command_observed'],'Reset guard failed')
        else:require(r['passed'] and all(r['checks'].values()) and r['source_sha256']==sha(timing),'Native classification failed')
        receipts[prefix]=str(files[-1])
    f=sorted((R/'tools/test-artifacts').glob('power-parser-*/result.json'))[-1];r=json.loads(f.read_text());require(r['passed'] and r['source_sha256']==sha(parser) and len(r['cases'])>=25,'Parser controls failed');receipts['parser']=str(f)
    f=sorted((P/'docs').glob('power-error-string-audit-*.json'))[-1];r=json.loads(f.read_text());require(r['passed'],'Exact stock literals absent')
    D=P/'artifacts/stock-cph2493-August-eu-ota/wifi-reference/vendor-dlkm-unpacked/lib/modules'
    for name,entry in r['modules'].items():require(sha((D/name).read_bytes())==entry['sha256'] and all(entry['literals'].values()),'Stock literal audit changed')
    receipts['literal_audit']=str(f)
    c=subprocess.run(['python3',str(R/'tools/lynx_wifi_v13_contact.py'),'--self-test'],capture_output=True,text=True,timeout=20);require(c.returncode==0,'Identity test failed')
    wrapper=(R/'tools/lynx_boot_a_wifi_v13_trial.py').read_text();require('time.monotonic()+780' in wrapper and 'validate_wifi_v13_image.py' in wrapper and SHA in wrapper,'Trial bounds/hash differ')
    model=R/'tools/avb-host/avb-boot-model';ref=json.loads((P/'docs/avb-boot-model-results.json').read_text());require(sha(model.read_bytes())==ref['binary_sha256'],'Boot model changed')
    for unlocked in ['1','0']:
        c=subprocess.run([str(model),str(P/'artifacts/stock-cph2493-August-eu-ota'),str(F/'nord3-busybox-candidate.img'),'0',unlocked],capture_output=True,text=True,timeout=30)
        require(c.returncode==0 and json.loads(c.stdout)['slot_data_returned']==(unlocked=='1'),'Boot policy differs')
    out=P/'docs/wifi-v13-image-validation.json';out.write_text(json.dumps({'passed':True,'candidate_sha256':SHA,'receipts':receipts,'parent_delta':'Only current-attempt diagnostic parser and token; startup/firmware/modules/credentials unchanged','phone_contacted':False,'limits':'Reports recognized diagnostic preceding generic power failure, not complete logs. Raw numeric probe reasons are evidence; semantic labels derive from reference source.'},indent=2)+'\n');print(out)
if __name__=='__main__':main()
