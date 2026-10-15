"""Independently verify pinned UFS registration diagnostic and its test receipts."""
import hashlib,json,stat,struct,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port'
sys.path.insert(0,str(P))
from image_formats import read_boot_v4,read_newc,module_metadata,elf64,require
from ramdisk_codec import decompress
SHA='034177798aed0cb0210e51eaf563eefc055abe6fcdbde3d272f89003b1880a56'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
    F=P/'artifacts/busybox-ufs-registration-only-v1';REF=P/'artifacts/busybox-module-progress-debug-40-v1'
    check=subprocess.run(['python3',str(R/'tools/validate_storage_prefix_progress_image.py'),'--count','40'],capture_output=True,text=True,timeout=45)
    require(check.returncode==0,'Proven prefix validation failed: '+check.stdout+check.stderr)
    image=(F/'nord3-busybox-candidate.img').read_bytes();reference=(REF/'nord3-busybox-candidate.img').read_bytes()
    require(sha(image)==SHA and len(image)==67108864,'Image hash/size changed')
    require(stat.S_IMODE(F.stat().st_mode)==0o700 and stat.S_IMODE((F/'nord3-busybox-candidate.img').stat().st_mode)==0o600,'Private permissions changed')
    boot,prior=read_boot_v4(image),read_boot_v4(reference)
    require(boot['kernel']==prior['kernel'] and boot['cmdline']==prior['cmdline'],'Kernel or command line changed')
    require(image[:12]==reference[:12] and image[16:4096]==reference[16:4096],'Header geometry changed')
    current,old=read_newc(decompress(boot['ramdisk'])),read_newc(decompress(prior['ramdisk']))
    require(set(current)==set(old),'Unexpected archive entries')
    require({n for n in old if current[n]!=old[n]}=={'init','etc/lynx/session-token','etc/lynx/diag-codebook.json'},'Unrelated archive changes')
    guard=(P/'ufs-registration-guard.sh').read_bytes();runtime=(P/'lynx-ufs-registration-runtime.sh').read_bytes()
    old_suffix=(P/'lynx-storage-prefix-progress-runtime.sh').read_bytes()+b'\nlynx_module_progress\nstop\n'
    require(old['init']['data'].endswith(old_suffix),'Frozen prefix boundary changed')
    require(current['init']['data']==old['init']['data'][:-len(old_suffix)]+guard+runtime+b'\nlynx_ufs_registration\nstop\n','Executable source differs')
    require(current['init']['data']==(F/'init-source').read_bytes(),'Saved init differs')
    require(runtime.count(b'/bin/boot-proof-reboot\n')==1 and b'/proc/sysrq-trigger' not in runtime,'Reset path changed')
    coverage=struct.unpack('!4sIIQQQ28x',reference[-64:])[3]
    require(image[coverage:]==reference[coverage:] and 4096+((len(boot['kernel'])+4095)//4096)*4096+((len(boot['ramdisk'])+4095)//4096)*4096<=coverage,'Metadata or payload changed/overlapped')
    manifest=json.loads((F/'build-validation.json').read_text())
    require(manifest['guard_sha256']==sha(guard) and manifest['runtime_sha256']==sha(runtime) and manifest['session_token']==current['etc/lynx/session-token']['data'].decode().strip(),'Manifest/source differs')
    book=json.loads(old['etc/lynx/diag-codebook.json']['data']);book['513']='guarded UFS registration outcome'
    require(json.loads(current['etc/lynx/diag-codebook.json']['data'])==book,'Stage codebook changed')
    vendor=read_newc(decompress((P/'artifacts/stock-cph2493-August-eu-ota/unpacked-vendor-boot/vendor_ramdisk00').read_bytes()));merged={**vendor,**current}
    dep=json.loads((P/'docs/storage-prefix-dependencies.json').read_text());loaded=set();versions={}
    names=[row['file'] for row in dep['module_order']]+['ufs-mediatek-mod.ko']
    rows=[]
    for name in names:
        raw=merged['lib/modules/'+name]['data'];meta=module_metadata(raw)['values']
        needs={d.replace('-','_') for s in meta.get('depends',[]) for d in s.split(',') if d}
        require(needs<=loaded,'Unloaded dependencies: '+name+str(needs-loaded))
        require(meta['vermagic']==['5.10.149-android12-9-o-g311738fbb5a8 SMP preempt mod_unload modversions aarch64'],'Module vermagic differs')
        for crc,symbol in struct.iter_unpack('<Q56s',elf64(raw)['sections']['__versions']):
            symbol=symbol.split(b'\0')[0]
            require(symbol not in versions or versions[symbol]==crc,'Conflicting imported CRC')
            versions[symbol]=crc
        loaded.add(meta['name'][0].replace('-','_'));rows.append({'file':name,'sha256':sha(raw)})
    require(rows[-1]['sha256']==manifest['ufs_module_sha256']=='31e452411297a57a6ed4c31b207c3b4604fa8b55acd95cff6135c680846614a4','Stock UFS module changed')
    audit=subprocess.run(['python3',str(R/'tools/audit_stock_ufs_match_table.py')],capture_output=True,text=True,timeout=20)
    require(audit.returncode==0,'Exact stock matching audit failed')
    table=json.loads(audit.stdout);require(table['exact_table_agrees_with_profile'] and table['module_sha256']==manifest['ufs_module_sha256'],'Matching table differs')
    native=[p for p in sorted((P/'artifacts').glob('emulated-native-ufs-registration-*/result.json')) if json.loads(p.read_text()).get('passed')]
    require(native,'Passing native test missing');n=json.loads(native[-1].read_text())
    require(n['candidate_sha256']==SHA and n['guard_sha256']==sha(guard) and n['runtime_sha256']==sha(runtime),'Native-tested source changed')
    guards=sorted((P/'artifacts').glob('emulated-ufs-registration-guard-*/result.json'));require(guards,'Exact candidate guard missing');g=json.loads(guards[-1].read_text())
    require(g['candidate_sha256']==SHA and g['module_checkpoint_failure_guard_observed'] and not g['kernel_reboot_command_observed'],'Hardware reset guard failed')
    require(manifest['target_delays_seconds']=={str(i):120+5*i for i in range(6)} and manifest['worker_sample_seconds']==90 and manifest['observation_seconds']==240 and manifest['timing_match_tolerance_seconds']==2,'Timing profile changed')
    model=R/'tools/avb-host/avb-boot-model';model_ref=json.loads((P/'docs/avb-boot-model-results.json').read_text());require(sha(model.read_bytes())==model_ref['binary_sha256'],'Model changed')
    for unlocked in ['0','1']:
        result=subprocess.run([str(model),str(P/'artifacts/stock-cph2493-August-eu-ota'),str(F/'nord3-busybox-candidate.img'),'0',unlocked],capture_output=True,text=True,timeout=30)
        require(result.returncode==0 and json.loads(result.stdout)['slot_data_returned']==(unlocked=='1'),'AVB model policy changed')
    report=dict(passed=True,candidate_sha256=SHA,modules=rows,native_receipt=str(native[-1]),guard_receipt=str(guards[-1]),phone_contacted=False,limits='Stock bytes/ABI, guarded matching source, native fixtures and boot model verified. Physical registration remains unproved; timing requires reset/non-interference evidence.')
    out=P/'docs/ufs-registration-validation.json';out.write_text(json.dumps(report,indent=2)+'\n');print(out)
if __name__=='__main__':main()
