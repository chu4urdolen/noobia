"""Independent geometry/provenance/control validation; no phone access."""
import argparse,hashlib,json,stat,struct,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;P=ROOT/'linux-port'
sys.path.insert(0,str(P))
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
SHAS={0:'465fa84fd647dc04298565db906bcbad3794166d247900bd2246d24702a521d2',28:'9b5e9ff94c5c441e945ebc3bf714b253d2f8bcfbfcc91182b8d9baf54aeab0e4',32:'2468d6b65d4f3cd06927db51b9e077708e363a9ecdd112c568203cc4a3eea6dd',34:'6070a324cbbfc8a1262b94ae111e3a6b3a4cb330e66af54d2363a3e2c5b7edad',41:'476997a9b518d951f075194004cf288e0214741f571810f8932009b8c585d11e'}
def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--count',type=int,choices=[41],required=True);args=parser.parse_args()
    check=subprocess.run(['python3',str(ROOT/'tools/validate_wifi_v5_image.py')],capture_output=True,text=True,timeout=30);require(check.returncode==0,'Reference validation failed: '+check.stdout+check.stderr)
    F=P/'artifacts'/('busybox-module-progress-debug-'+str(args.count)+'-v1');REF=P/'artifacts/busybox-wifi-ssh-twostage-v5'
    image=(F/'nord3-busybox-candidate.img').read_bytes();reference=(REF/'nord3-busybox-candidate.img').read_bytes()
    require(sha(image)==SHAS[args.count] and len(image)==67108864,'Pinned image differs')
    require(stat.S_IMODE(F.stat().st_mode)==0o700 and stat.S_IMODE((F/'nord3-busybox-candidate.img').stat().st_mode)==0o600,'Private permissions differ')
    boot,previous=read_boot_v4(image),read_boot_v4(reference)
    require(boot['kernel']==previous['kernel'],'Kernel changed')
    require(image[:12]==reference[:12] and image[16:44]==reference[16:44] and image[1580:4096]==reference[1580:4096],'Header geometry changed')
    require(boot['cmdline']==previous['cmdline']+' initcall_debug','Unexpected kernel arguments')
    current,old=read_newc(decompress(boot['ramdisk'])),read_newc(decompress(previous['ramdisk']))
    require(set(current)-set(old)=={'etc/lynx/progress-modules.load','etc/lynx/progress-count'},'Unexpected files')
    for name in old:
        if name not in ['init','etc/lynx/session-token','etc/lynx/diag-codebook.json']:require(current[name]==old[name],'Unrelated entry changed: '+name)
    prefix=old['etc/lynx/bootstrap-base-modules.load']['data'].decode().splitlines()[:34]+old['etc/lynx/bootstrap-storage-modules.load']['data'].decode().splitlines()
    require(current['etc/lynx/progress-modules.load']['data']==('\n'.join(prefix)+'\n').encode(),'Prefix differs')
    require(current['etc/lynx/progress-count']['data']==(str(args.count)+'\n').encode(),'Count differs')
    require(not any(name in prefix for name in ['mtu3.ko','phy-mtk-xsphy.ko','tcpc_mt6375.ko','extcon-mtk-usb.ko','xhci-mtk-hcd.ko','rpmb-mtk.ko']),'Checkpoint exceeds reviewed prefix')
    source=(P/'lynx-essential-storage-progress-runtime.sh').read_bytes();marker=b"\nlog 'WIFI_TWO_STAGE_BOOTSTRAP_BEGIN'\n"
    expected=old['init']['data'].split(marker)[0]+source+b'\nlynx_module_progress\nstop\n'
    require(current['init']['data']==expected==(F/'init-source').read_bytes(),'Executable init differs')
    manifest=json.loads((F/'build-validation.json').read_text())
    require(manifest['session_token']==current['etc/lynx/session-token']['data'].decode().strip(),'Session differs')
    codes={str(i):'reserved; do not interpret' for i in range(128)}
    for index,name in enumerate(prefix,1):
        codes[str(index)]='insertion still pending at sample: '+name
        codes[str(index+42)]='last insertion completed before sampling: '+name
        codes[str(index+84)]='insertion returned failure: '+name
    codes.update({'0':'all essential module insertions and verified own boot payload read completed','42':'partition discovery or own boot payload read pending','84':'own boot payload verified and extracted','126':'partition discovery or own boot payload read failed','127':'worker progress unavailable or malformed'})
    require(manifest['result_codes']==codes,'Progress interpretation differs')
    book=json.loads(old['etc/lynx/diag-codebook.json']['data']);book['512']='module progress field'
    require(json.loads(current['etc/lynx/diag-codebook.json']['data'])==book==manifest['diagnostic_codebook'],'Hex codebook differs')
    coverage=struct.unpack('!4sIIQQQ28x',reference[-64:])[3]
    require(image[coverage:]==reference[coverage:],'Recovery metadata/footer/payload changed')
    require(4096+((len(boot['kernel'])+4095)//4096)*4096+((len(boot['ramdisk'])+4095)//4096)*4096<=coverage,'Loaded area overlaps metadata')
    controls=sorted((ROOT/'tools/test-artifacts').glob('essential-storage-progress-control-*/result.json'));require(controls,'Control test missing')
    control=json.loads(controls[-1].read_text());require(control['passed'] and control['source_sha256']==sha(source),'Tested control differs')
    native=sorted(path for path in (P/'artifacts').glob('emulated-native-essential-storage-progress-*/result.json') if json.loads(path.read_text()).get('candidate_sha256')==SHAS[args.count] and json.loads(path.read_text()).get('passed'))
    require(native,'Passing native hex/control test missing');n=json.loads(native[-1].read_text());require(n['source_sha256']==sha(source) and n['checks']['native_hex_SUCCESS'] and n['checks']['native_hex_FAILURE'] and n['checks']['native_hex_PAYLOAD'] and n['checks']['payload_failure'],'Native tested runtime differs')
    guards=sorted((P/'artifacts').glob('emulated-module-progress-debug-guard-'+str(args.count)+'-*/result.json'));require(guards,'Exact-image guard missing')
    guard=json.loads(guards[-1].read_text());require(guard['candidate_sha256']==SHAS[args.count] and guard['module_checkpoint_failure_guard_observed'] and not guard['kernel_reboot_command_observed'],'Reset safety guard failed')
    initcalls=sorted((P/'artifacts').glob('emulated-native-initcall-debug-v2-cortex-a710-*/result.json'));require(initcalls,'Stock initcall_debug proof missing')
    require(json.loads(initcalls[-1].read_text())['passed'],'Stock initcall_debug test failed')
    dep=json.loads((P/'docs/essential-storage-dependencies.json').read_text());require(dep['passed'] and not dep['dependencies_not_yet_loaded'] and not dep['shared_crc_conflicts'],'Dependency/version audit failed')
    vendor=read_newc(decompress((P/'artifacts/stock-cph2493-August-eu-ota/unpacked-vendor-boot/vendor_ramdisk00').read_bytes()));merged={**vendor,**current}
    for row in dep['module_order']:require(sha(merged['lib/modules/'+row['file']]['data'])==row['sha256'],'Audited module differs')
    require(manifest['target_delays_seconds']=={str(n):120+2*n for n in range(128)} and manifest['worker_sample_seconds']==90 and manifest['observation_seconds']==420 and manifest['timing_match_tolerance_seconds']==0.8,'Timing geometry changed')
    model=ROOT/'tools/avb-host/avb-boot-model';mref=json.loads((P/'docs/avb-boot-model-results.json').read_text());require(sha(model.read_bytes())==mref['binary_sha256'],'AVB model changed')
    for unlocked in ['1','0']:
        result=subprocess.run([str(model),str(P/'artifacts/stock-cph2493-August-eu-ota'),str(F/'nord3-busybox-candidate.img'),'0',unlocked],capture_output=True,text=True,timeout=30);require(result.returncode==0 and json.loads(result.stdout)['slot_data_returned']==(unlocked=='1'),'AVB policy changed')
    report={'passed':True,'candidate_sha256':SHAS[args.count],'prefix_count':args.count,'native_receipt':str(native[-1]),'control_receipt':str(controls[-1]),'guard_receipt':str(guards[-1]),'phone_contacted':False,'kernel_metadata_payload_unchanged':True,'timing_calibration_required':args.count!=0,'limits':'Software/geometry/ABI checks, not physical binding or log persistence. Camera timing requires debug baseline and reset/non-interference evidence.'}
    out=P/'docs'/('module-progress-debug-'+str(args.count)+'-validation.json');out.write_text(json.dumps(report,indent=2)+'\n');print(out)
if __name__=='__main__':main()
