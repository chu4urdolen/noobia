"""Independent, read-only validation of Lynx's fixed two-stage Wi-Fi candidate."""
import gzip,hashlib,json,stat,struct,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;P=ROOT/'linux-port';sys.path.insert(0,str(P))
from image_formats import read_boot_v4,read_newc,require,elf64,static_aarch64
from ramdisk_codec import decompress
S=P/'artifacts/stock-cph2493-August-eu-ota';F=P/'artifacts/busybox-wifi-ssh-twostage-v3'
IMAGE_SHA='3a1c2ddacac0c6fdf7e152a2db30add1b1b4fbab881346d6d346faf584abf94c'
def digest(b):return hashlib.sha256(b).hexdigest()
def main():
 image_path=F/'nord3-busybox-candidate.img';image=image_path.read_bytes();require(digest(image)==IMAGE_SHA and len(image)==67108864,'Wi-Fi image changed')
 require(stat.S_IMODE(image_path.stat().st_mode)==0o600 and stat.S_IMODE(F.stat().st_mode)==0o700,'Private image permissions changed')
 stock=(S/'boot.img').read_bytes();require(digest(stock)=='a67f03d7b826b834c23653b67eaa6efa971eb70ef8af19eee4d33fb5fc7fe995','Stock undo changed')
 base=(P/'artifacts/busybox-usb-module-checkpoints/suppliers/nord3-busybox-candidate.img').read_bytes();require(digest(base)=='0208f76c1ef5d7e523dbf83226c208f0a0d8f2c08768cbbdfb79025275fd9ece','Known reference changed')
 boot=read_boot_v4(image);ref=read_boot_v4(base);require(boot['kernel']==read_boot_v4(stock)['kernel']==ref['kernel'],'Kernel changed')
 require(image[:12]==base[:12] and image[16:4096]==base[16:4096],'Unrelated boot header changes')
 first=read_newc(decompress(boot['ramdisk']));original=read_newc(decompress(ref['ramdisk']))
 for name,entry in original.items():
  if name!='init':require(first.get(name)==entry,'Unrelated bootstrap entry changed: '+name)
 allowed={'etc/lynx','etc/lynx/bootstrap-base-modules.load','etc/lynx/bootstrap-storage-modules.load','etc/lynx/payload-bytes','etc/lynx/payload-sha256'}
 require(set(first)-set(original)==allowed,'Unexpected bootstrap files')
 init=first['init']['data'];require(init==(F/'init-source').read_bytes(),'Frozen init differs')
 require((P/'lynx-boot-payload-readonly.sh').read_bytes() in init and (P/'lynx-wifi-bootstrap-runtime.sh').read_bytes() in init,'Bootstrap source changed')
 require(init.count(b'/bin/boot-proof-reboot\n')==1 and b'lynx_wifi_bootstrap || stop' in init,'Bootstrap reset guard changed')
 size=int(first['etc/lynx/payload-bytes']['data']);expected=first['etc/lynx/payload-sha256']['data'].decode().strip();start=24*1024*1024;end=start+size
 _,_,_,coverage,offset,vsize=struct.unpack('!4sIIQQQ28x',stock[-64:]);require(end<len(image)-64 and offset+vsize<=start,'Supplement boundary invalid')
 require(image[coverage:start]==base[coverage:start] and image[end:]==base[end:],'Metadata/footer or unrelated padding changed')
 require(not any(base[start:end]),'Supplement replaced non-padding reference bytes')
 blob=image[start:end];require(digest(blob)==expected and blob==(F/'supplement.cpio.gz').read_bytes(),'Supplement hash mismatch')
 raw=gzip.decompress(blob);require(len(raw)<=128*1024*1024,'Supplement expansion oversized');extra=read_newc(raw)
 require(not any(n in extra for n in ['init','bin/busybox','bin/sh','bin/boot-proof-reboot']),'Supplement overwrites running executable')
 require(not any(n.startswith(('dev/','sys/','proc/','mnt/')) for n in extra),'Unexpected supplementary device/mount content')
 vendor=read_newc(decompress((S/'unpacked-vendor-boot/vendor_ramdisk00').read_bytes()));combined={**vendor,**first,**extra}
 audit=json.loads((P/'docs/wifi-boot-module-audit.json').read_text());require(audit['module_layout_matches_stock'] and not audit['imported_symbol_crc_conflicts'],'ABI audit failed')
 for r in audit['modules']:require(digest(combined['lib/modules/'+r['name']]['data'])==r['sha256'],'Matching stock module differs: '+r['name'])
 base_names=first['etc/lynx/bootstrap-base-modules.load']['data'].decode().splitlines();storage=first['etc/lynx/bootstrap-storage-modules.load']['data'].decode().splitlines();radio=extra['etc/lynx/wifi-radio-modules.load']['data'].decode().splitlines()
 require(len(base_names)==33 and len(set(base_names+storage+radio))==len(base_names+storage+radio) and 'mtu3.ko' not in base_names+storage+radio,'Duplicate or unwanted USB controller load')
 require(extra['etc/lynx/wifi-base-modules.load']['data']==extra['etc/lynx/wifi-storage-modules.load']['data']==b'','Already-loaded drivers would reload')
 require(extra['etc/lynx/wifi-runtime.sh']['data']==(P/'lynx-wifi-runtime.sh').read_bytes(),'Wi-Fi runtime source changed')
 require(extra['etc/lynx/calibration-readonly.sh']['data']==(P/'lynx-calibration-readonly.sh').read_bytes(),'Read-only calibration source changed')
 require(extra['bin/lynx-dhcp']['data']==(P/'lynx-dhcp.sh').read_bytes(),'DHCP hook changed')
 helper=extra['bin/lynx-wifi-control']['data'];static_aarch64(helper);require(helper==(P/'artifacts/wifi-native-helpers/lynx-wifi-control.elf').read_bytes(),'Native helper changed')
 for name in ['usr/sbin/dropbear','sbin/wpa_supplicant','sbin/wpa_cli','usr/sbin/iw','usr/bin/nc','lib/ld-musl-aarch64.so.1']:require(elf64(extra[name]['data'])['machine']==183,'Wrong userspace architecture')
 for name,source in [('etc/lynx/wpa_supplicant.conf','noobia-wpa_supplicant.conf'),('etc/dropbear/lynx_ed25519_host_key','lynx_ssh_host_ed25519'),('root/.ssh/authorized_keys','nexus_lynx_ed25519.pub')]:
  require(extra[name]['data']==(ROOT/'secrets'/source).read_bytes(),'Private configuration mismatch');require(extra[name]['mode']==0o100600 and extra[name]['uid']==0,'Private config permissions wrong')
 require('root/.ssh/nexus_lynx_ed25519' not in extra and (ROOT/'secrets/nexus_lynx_ed25519').read_bytes() not in raw,'Client private key must stay on Nexus')
 report=json.loads((F/'build-validation.json').read_text())
 for r in report['firmware']:require(digest(extra['lib/firmware/'+r['name']]['data'])==r['sha256'] and digest(Path(r['source']).read_bytes())==r['sha256'],'Matching firmware changed')
 receipts={
  'supervisor':ROOT/'tools/test-artifacts/wifi-supervisors-1791752500321885348/result.json',
  'network':P/'artifacts/emulated-native-dhcp-ssh-udp-1791749522460166466/result.json',
  'calibration':P/'artifacts/emulated-native-calibration-readonly-1791748592634210034/result.json',
  'boot_payload':P/'artifacts/emulated-native-boot-payload-1791752193887838856/result.json'}
 tests={k:json.loads(v.read_text()) for k,v in receipts.items()};require(all(x['passed'] for x in tests.values()),'Required native/control-flow tests failed')
 require(tests['supervisor']['source_sha256']=={'bootstrap':digest((P/'lynx-wifi-bootstrap-runtime.sh').read_bytes()),'wifi':digest((P/'lynx-wifi-runtime.sh').read_bytes())},'Supervisor tested source changed')
 require(tests['calibration']['helper_sha256']==digest(helper) and tests['calibration']['calibration_source_sha256']==digest((P/'lynx-calibration-readonly.sh').read_bytes()),'Calibration tested source changed')
 require(tests['boot_payload']['boot_reader_sha256']==digest((P/'lynx-boot-payload-readonly.sh').read_bytes()),'Boot reader tested source changed')
 vms=sorted((P/'artifacts').glob('emulated-wifi-image-*/result.json'));require(vms,'Exact-image VM test missing');vm=json.loads(vms[-1].read_text())
 require(vm['candidate_sha256']==IMAGE_SHA and vm['module_checkpoint_failure_guard_observed'] and not vm['kernel_reboot_command_observed'],'Exact image guard test failed')
 model=ROOT/'tools/avb-host/avb-boot-model';mref=json.loads((P/'docs/avb-boot-model-results.json').read_text());require(digest(model.read_bytes())==mref['binary_sha256'],'AVB model changed');cases=[]
 for unlocked in ['1','0']:
  p=subprocess.run([str(model),str(S),str(image_path),'0',unlocked],capture_output=True,text=True,timeout=30);require(p.returncode==0,'AVB model failed');cases.append(json.loads(p.stdout))
 require(cases[0]['slot_data_returned'] and cases[0]['boot_partitions_loaded']==1 and not cases[1]['slot_data_returned'],'AVB unlocked policy differs')
 out=P/'docs/wifi-image-validation.json';out.write_text(json.dumps({'passed':True,'candidate_sha256':IMAGE_SHA,'kernel_unchanged':True,'stock_metadata_and_footer_unchanged':True,'boot_a_only_layout':True,'supplement_sha256':expected,'native_test_receipts':{k:str(v) for k,v in receipts.items()},'exact_image_vm_receipt':str(vms[-1]),'avb_cases':cases,'hardware_wifi_verified':False,'phone_contacted':False,'limits':'Validates image layout and native software safety paths; no MT6983 radio/storage initialization or physical pstore persistence proved.'},indent=2)+'\n');print(out)
if __name__=='__main__':main()
