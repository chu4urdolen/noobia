"""Validate only the firmware-directory repair against the reviewed v7 image."""
import argparse,gzip,hashlib,json,stat,struct,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';sys.path.insert(0,str(P))
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
SHA='0b0da995892b072fa17de86c814584c0eca918130431a0e49566e07a67449c13'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
    parser=argparse.ArgumentParser();parser.parse_args()
    parent=subprocess.run(['python3',str(R/'tools/validate_wifi_v7_image.py')],capture_output=True,text=True,timeout=60);require(parent.returncode==0,'v7 validation failed: '+parent.stdout+parent.stderr)
    F=P/'artifacts/busybox-wifi-ssh-twostage-v9';V=P/'artifacts/busybox-wifi-ssh-twostage-v7'
    image=(F/'nord3-busybox-candidate.img').read_bytes();old=(V/'nord3-busybox-candidate.img').read_bytes();require(sha(image)==SHA and len(image)==67108864,'Pinned image differs')
    require(stat.S_IMODE(F.stat().st_mode)==0o700 and stat.S_IMODE((F/'nord3-busybox-candidate.img').stat().st_mode)==0o600,'Private image permissions differ')
    boot,previous=read_boot_v4(image),read_boot_v4(old);entries,prior=read_newc(decompress(boot['ramdisk'])),read_newc(decompress(previous['ramdisk']))
    require(boot['kernel']==previous['kernel'] and boot['cmdline']==previous['cmdline'],'Kernel/cmdline changed')
    require(image[:12]==old[:12] and image[16:4096]==old[16:4096],'Unrelated header changed')
    require(set(entries)==set(prior),'First-stage files changed')
    for name in prior:
        if name not in ['etc/lynx/session-token','etc/lynx/payload-bytes','etc/lynx/payload-sha256']:require(entries[name]==prior[name],'First-stage driver/runtime/key changed: '+name)
    require(entries['init']['data']==(F/'init-source').read_bytes(),'Saved init differs')
    payload=(F/'supplement.cpio.gz').read_bytes();oldpayload=(V/'supplement.cpio.gz').read_bytes();require(payload[:2]==b'\x1f\x8b','Userspace payload must be gzip')
    current,original=read_newc(gzip.decompress(payload)),read_newc(gzip.decompress(oldpayload))
    require(original['vendor/firmware']['mode']&0o170000==0o120000 and original['vendor/firmware']['data']==b'../lib/firmware','Reference alias differs')
    require(current['vendor/firmware']['mode']&0o170000==0o040000 and not current['vendor/firmware']['data'],'Firmware directory was not preserved')
    mirrored={}
    for name,item in original.items():
        if name.startswith('lib/firmware/') and item['mode']&0o170000==0o100000:
            target='vendor/firmware/'+name[len('lib/firmware/'):]
            mirrored[target]=name;require(current[target]==item,'Firmware mirror bytes/permissions differ')
    require(set(current)-set(original)==set(mirrored),'Unexpected supplementary files')
    for name in original:
        if name!='vendor/firmware':require(current[name]==original[name],'Unrelated module/key/config changed: '+name)
    require(len(mirrored)==11,'Firmware list differs')
    vendor=read_newc(decompress((P/'artifacts/stock-cph2493-August-eu-ota/unpacked-vendor-boot/vendor_ramdisk00').read_bytes()))
    require(vendor['vendor/firmware']['mode']&0o170000==0o040000,'Stock collision is not the audited directory')
    for target,name in mirrored.items():
        if target in vendor:require(vendor[target]['data']==original[name]['data'],'Existing stock firmware would be overwritten with different bytes')
    manifest=json.loads((F/'build-validation.json').read_text())
    require(manifest['candidate_sha256']==SHA and manifest['init_sha256']==sha(entries['init']['data']),'Manifest executable hash differs')
    require(manifest['session_token']==entries['etc/lynx/session-token']['data'].decode().strip(),'Token differs')
    require(entries['etc/lynx/payload-bytes']['data']==(str(len(payload))+'\n').encode() and entries['etc/lynx/payload-sha256']['data']==(sha(payload)+'\n').encode(),'Payload manifest differs')
    require(manifest['supplement_bytes']==len(payload) and manifest['supplement_sha256']==sha(payload) and manifest['supplement_entry_names']==list(current),'Supplement report differs')
    offset=25165824;coverage=struct.unpack('!4sIIQQQ28x',old[-64:])[3]
    require(image[offset:offset+len(payload)]==payload,'Embedded payload differs')
    require(image[coverage:offset]==old[coverage:offset] and image[offset+max(len(payload),len(oldpayload)):]==old[offset+max(len(payload),len(oldpayload)):],'Protected metadata/footer or unrelated tail changed')
    require(4096+((len(boot['kernel'])+4095)//4096)*4096+((len(boot['ramdisk'])+4095)//4096)*4096<=coverage,'Loaded metadata overlap')
    loops=sorted((P/'artifacts').glob('emulated-native-vendor-payload-fixed-loop-*/result.json'));require(loops,'Matching vendor extraction test absent');l=json.loads(loops[-1].read_text())
    require(l['passed'] and l['candidate_sha256']==SHA and all(l['checks'].values()),'Matching-vendor block/extraction test failed')
    reader=entries['init']['data'];reader=reader[reader.index(b'lynx_read_own_boot_payload() {'):reader.index(b'lynx_wifi_bootstrap_child_unlogged() {')]
    require(l['payload_reader_sha256']==sha(reader),'Tested payload reader differs')
    journals=sorted((P/'artifacts').glob('emulated-wifi-v9-journals-*/result.json'));require(journals,'Native supervisor test absent');j=json.loads(journals[-1].read_text())
    require(j['passed'] and j['candidate_sha256']==SHA and all(j['checks'].values()),'Native supervisor/journal test differs')
    guards=sorted((P/'artifacts').glob('emulated-wifi-v9-guard-*/result.json'));require(guards,'Exact image guard absent');g=json.loads(guards[-1].read_text())
    require(g['candidate_sha256']==SHA and g['module_checkpoint_failure_guard_observed'] and not g['kernel_reboot_command_observed'],'Exact reset guard differs')
    selftest=subprocess.run(['python3',str(R/'tools/lynx_wifi_v9_contact.py'),'--self-test'],capture_output=True,text=True,timeout=20);require(selftest.returncode==0,'Pinned identity tests failed')
    model=R/'tools/avb-host/avb-boot-model';m=json.loads((P/'docs/avb-boot-model-results.json').read_text());require(sha(model.read_bytes())==m['binary_sha256'],'AVB model changed')
    for unlocked in ['1','0']:
        result=subprocess.run([str(model),str(P/'artifacts/stock-cph2493-August-eu-ota'),str(F/'nord3-busybox-candidate.img'),'0',unlocked],capture_output=True,text=True,timeout=30)
        require(result.returncode==0 and json.loads(result.stdout)['slot_data_returned']==(unlocked=='1'),'Boot policy changed')
    report={'passed':True,'candidate_sha256':SHA,'parent_v7_validation_passed':True,'kernel_modules_init_credentials_unchanged':True,'vendor_firmware_directory_preserved':True,'mirrored_firmware_count':len(mirrored),'vendor_loop_receipt':str(loops[-1]),'native_journals_receipt':str(journals[-1]),'guard_receipt':str(guards[-1]),'phone_contacted':False,'limits':'Fixes reproduced cpio directory collision; physical corrected payload extraction/Wi-Fi/SSH still unproved.'}
    out=P/'docs/wifi-v9-image-validation.json';out.write_text(json.dumps(report,indent=2)+'\n');print(out)
if __name__=='__main__':main()
