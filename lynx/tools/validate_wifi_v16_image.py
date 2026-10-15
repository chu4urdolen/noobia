"""Validate only the firmware-service delta; reuse pinned unchanged V15 checks."""
import gzip,hashlib,json,stat,struct,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';sys.path.insert(0,str(P))
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
SHA='73311e9613a002a5bf3d3d4c4b5057840b7a427a06e1aff18a186e27e68614f6'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
    parent=json.loads((P/'docs/wifi-v15-image-validation.json').read_text());require(parent['passed'] and parent['candidate_sha256']=='c08d19beb54ef6400912651539d6ce9f510632a94d04180f30b88114d48768f2','Parent receipt differs')
    F=P/'artifacts/busybox-wifi-ssh-twostage-v16';V=P/'artifacts/busybox-wifi-ssh-twostage-v15';raw=(F/'nord3-busybox-candidate.img').read_bytes();old=(V/'nord3-busybox-candidate.img').read_bytes();require(sha(raw)==SHA and sha(old)==parent['candidate_sha256'] and len(raw)==len(old)==67108864,'Image differs')
    require(stat.S_IMODE(F.stat().st_mode)==0o700 and stat.S_IMODE((F/'nord3-busybox-candidate.img').stat().st_mode)==0o600,'Permissions differ')
    b,o=read_boot_v4(raw),read_boot_v4(old);e,p=read_newc(decompress(b['ramdisk'])),read_newc(decompress(o['ramdisk']));require(b['kernel']==o['kernel'] and b['cmdline']==o['cmdline'] and raw[:12]==old[:12] and raw[16:4096]==old[16:4096],'Kernel/header changed');require(set(e)==set(p),'First-stage entries changed')
    for n in p:
        if n not in ['etc/lynx/session-token','etc/lynx/payload-bytes','etc/lynx/payload-sha256']:require(e[n]==p[n],'Unrelated first-stage change: '+n)
    payload=(F/'supplement.cpio.gz').read_bytes();previous=(V/'supplement.cpio.gz').read_bytes();x,y=read_newc(gzip.decompress(payload)),read_newc(gzip.decompress(previous));require(set(x)-set(y)=={'etc/lynx/firmware-events.sh'} and not set(y)-set(x),'Supplement entry set changed')
    for n in y:
        if n!='etc/lynx/wifi-runtime.sh':require(x[n]==y[n],'Unrelated firmware/module/credential/station change: '+n)
    service=(P/'firmware-events.sh').read_bytes();require(x['etc/lynx/firmware-events.sh']['data']==service==(F/'firmware-events.sh').read_bytes(),'Service source differs')
    wifi=y['etc/lynx/wifi-runtime.sh']['data'];anchor=b'    lynx_stage WIFI_DRIVERS\n';require(wifi.count(anchor)==1,'Radio boundary changed');wifi=wifi.replace(anchor,b'    . /etc/lynx/firmware-events.sh || return 135\n    lynx_firmware_events_start || return 135\n'+anchor);require(x['etc/lynx/wifi-runtime.sh']['data']==wifi==(F/'wifi-runtime.sh').read_bytes(),'Startup delta differs')
    vendor=P/'artifacts/stock-cph2493-August-eu-ota/vendor-ramdisk-unpacked/etc/mdev.conf';require(not vendor.exists() and not vendor.is_symlink(),'Unexpected vendor mdev command configuration');require('etc/mdev.conf' not in e,'Unexpected first-stage mdev command configuration')
    m=json.loads((F/'build-validation.json').read_text());oldm=json.loads((V/'build-validation.json').read_text());require(m['candidate_sha256']==SHA and m['firmware_events_sha256']==sha(service) and m['init_sha256']==sha(e['init']['data']) and m['timing_runtime_sha256']==oldm['timing_runtime_sha256']==sha(e['bin/boot-proof-reboot']['data']),'Executable manifest differs');require(m['target_delays_seconds']==oldm['target_delays_seconds'] and m['observation_seconds']==660,'Fast timing changed')
    require(m['session_token']==e['etc/lynx/session-token']['data'].decode().strip() and m['supplement_sha256']==sha(payload) and e['etc/lynx/payload-sha256']['data']==(sha(payload)+'\n').encode() and e['etc/lynx/payload-bytes']['data']==(str(len(payload))+'\n').encode(),'Payload/token metadata differs')
    coverage=struct.unpack('!4sIIQQQ28x',old[-64:])[3];off=25165824;require(raw[off:off+len(payload)]==payload and raw[coverage:off]==old[coverage:off] and raw[off+max(len(payload),len(previous)):]==old[off+max(len(payload),len(previous)):],'Protected bytes changed');require(4096+((len(b['kernel'])+4095)//4096)*4096+((len(b['ramdisk'])+4095)//4096)*4096<=coverage,'Metadata overlap')
    receipts={}
    for prefix in ['emulated-native-firmware-events-','emulated-wifi-v16-image-']:
        files=sorted((P/'artifacts').glob(prefix+'*/result.json'));require(files,'Native check missing');r=json.loads(files[-1].read_text());require(r['candidate_sha256']==SHA,'Test candidate differs')
        if prefix=='emulated-wifi-v16-image-':require(r['module_checkpoint_failure_guard_observed'] and not r['kernel_reboot_command_observed'],'Reset guard failed')
        else:require(r['passed'] and all(r['checks'].values()) and r['service_sha256']==sha(service) and r['kernel_sha256']==sha(b['kernel']) and r['busybox_sha256']==sha(e['bin/busybox']['data']),'Native service/protocol checks differ')
        receipts[prefix]=str(files[-1])
    c=subprocess.run(['python3',str(R/'tools/lynx_wifi_v16_contact.py'),'--self-test'],capture_output=True,text=True,timeout=20);require(c.returncode==0,'Identity proof checks failed');wrapper=(R/'tools/lynx_boot_a_wifi_v16_trial.py').read_text();require(SHA in wrapper and 'time.monotonic()+660' in wrapper and 'lynx_fast_wifi_timing' in wrapper,'Trial policy differs')
    model=R/'tools/avb-host/avb-boot-model'
    for unlocked in ['1','0']:
        c=subprocess.run([str(model),str(P/'artifacts/stock-cph2493-August-eu-ota'),str(F/'nord3-busybox-candidate.img'),'0',unlocked],capture_output=True,text=True,timeout=30);require(c.returncode==0 and json.loads(c.stdout)['slot_data_returned']==(unlocked=='1'),'Boot policy differs')
    out=P/'docs/wifi-v16-image-validation.json';out.write_text(json.dumps({'passed':True,'candidate_sha256':SHA,'receipts':receipts,'reused_parent_receipt':str(P/'docs/wifi-v15-image-validation.json'),'phone_contacted':False,'limits':'Standard firmware-event service; exact firmware bytes unchanged. Native daemon/netlink and synthetic sysfs protocol verified. Physical firmware requests and Wi-Fi remain unproved.'},indent=2)+'\n');print(out)
if __name__=='__main__':main()
