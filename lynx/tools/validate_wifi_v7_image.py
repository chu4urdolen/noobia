"""Verify the network image preserves proven UFS startup and private payload."""
import gzip,hashlib,json,stat,struct,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';sys.path.insert(0,str(P))
from image_formats import read_boot_v4,read_newc,module_metadata,elf64,require
from ramdisk_codec import decompress
SHA='9a17b8e72e8e8fe8928f551fcf593cee1d19a712affe498f23f637e7ac4da00c'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
    parent=subprocess.run(['python3',str(R/'tools/validate_wifi_v5_image.py')],capture_output=True,text=True,timeout=45);require(parent.returncode==0,'Preserved Wi-Fi reference failed: '+parent.stdout+parent.stderr)
    F=P/'artifacts/busybox-wifi-ssh-twostage-v7';REF=P/'artifacts/busybox-wifi-ssh-twostage-v5';image=(F/'nord3-busybox-candidate.img').read_bytes();reference=(REF/'nord3-busybox-candidate.img').read_bytes();require(sha(image)==SHA and len(image)==67108864,'Pinned image changed')
    require(stat.S_IMODE(F.stat().st_mode)==0o700 and stat.S_IMODE((F/'nord3-busybox-candidate.img').stat().st_mode)==0o600,'Private permissions changed')
    boot,prior=read_boot_v4(image),read_boot_v4(reference);require(boot['kernel']==prior['kernel'] and boot['cmdline']==prior['cmdline']+' initcall_debug tp_printk','Kernel/cmdline differs from reviewed startup')
    require(image[:12]==reference[:12] and image[16:44]==reference[16:44] and image[1580:4096]==reference[1580:4096],'Header geometry changed')
    entries,old=read_newc(decompress(boot['ramdisk'])),read_newc(decompress(prior['ramdisk']));require(set(entries)==set(old) and {n for n in old if entries[n]!=old[n]}=={'init','etc/lynx/bootstrap-base-modules.load','etc/lynx/session-token','etc/lynx/diag-codebook.json'},'Unrelated archive changes')
    guard=(P/'stock-clock-helper-guard.sh').read_bytes();ufs_guard=(P/'ufs-registration-guard.sh').read_bytes();trace=(P/'ufs-refclk-persistent-trace-v2-setup.sh').read_bytes()
    expected=old['init']['data'].replace(b'lynx_load_checkpoint_modules() {\n',guard+ufs_guard+trace+b'lynx_load_checkpoint_modules() {\n')
    addition=b'''        if [ "$module" = ufs-mediatek-mod.ko ]; then
            lynx_ufs_registration_guard || return 1
            lynx_stock_clock_helper_load
            clock_startup_status=$?
            if [ "$clock_startup_status" != 0 ]; then
                lynx_diag_emit 516 "$clock_startup_status" || true
                log "STOCK_CLOCK_HELPER_FAILED_BEFORE_UFS status=$clock_startup_status"
                return 1
            fi
        fi
'''
    expected=expected.replace(b'        log "CHECKPOINT_MODULE_BEGIN $module"\n',b'        log "CHECKPOINT_MODULE_BEGIN $module"\n'+addition)
    expected=expected.replace(b'        log "CHECKPOINT_MODULE_OK $module"\n',b'''        if [ "$module" = ufs-mediatek-mod.ko ]; then
            lynx_ufs_guarded_probe || return 1
        fi
        log "CHECKPOINT_MODULE_OK $module"
''')
    require(entries['init']['data']==expected==(F/'init-source').read_bytes(),'Executable startup differs')
    names=old['etc/lynx/bootstrap-base-modules.load']['data'].decode().splitlines();require(entries['etc/lynx/bootstrap-base-modules.load']['data']==('\n'.join(names[:34])+'\n').encode(),'Unexpected module prefix')
    coverage=struct.unpack('!4sIIQQQ28x',reference[-64:])[3];require(image[coverage:]==reference[coverage:],'Recovery metadata/footer/network payload changed');require(4096+((len(boot['kernel'])+4095)//4096)*4096+((len(boot['ramdisk'])+4095)//4096)*4096<=coverage,'Metadata overlap')
    blob=(F/'supplement.cpio.gz').read_bytes();require(blob==(REF/'supplement.cpio.gz').read_bytes(),'Private network payload changed');extra=read_newc(gzip.decompress(blob));require(entries['etc/lynx/diag-hooks.sh']==old['etc/lynx/diag-hooks.sh'],'Logger hooks changed')
    manifest=json.loads((F/'build-validation.json').read_text());require(manifest['session_token']==entries['etc/lynx/session-token']['data'].decode().strip() and manifest['init_sha256']==sha(expected),'Identity metadata differs')
    book=json.loads(old['etc/lynx/diag-codebook.json']['data']);book['516']='stock clock helper: load1, returned2, bound/counters3, refused or failed10..13';book['515']='trace ready16, before controlled probe17, probe returned18';require(json.loads(entries['etc/lynx/diag-codebook.json']['data'])==book==manifest['diagnostic_codebook'],'Stage codebook changed')
    require(manifest['stock_clock_guard_sha256']==sha(guard) and manifest['ufs_guard_sha256']==sha(ufs_guard) and manifest['refclk_trace_sha256']==sha(trace),'Guard/trace source differs')
    proof=json.loads((R/'logs/boot-a-stock-clock-helper-probe-trial-1792003167463063951.json').read_text());require(proof['fastboot_return_observed'] and proof['timing_module_progress_field']==0,'Successful guarded UFS reference missing')
    startup_check=subprocess.run(['python3',str(R/'tools/validate_stock_clock_helper_probe_image.py')],capture_output=True,text=True,timeout=90);require(startup_check.returncode==0,'Proven startup validation failed: '+startup_check.stdout+startup_check.stderr)
    vendor=read_newc(decompress((P/'artifacts/stock-cph2493-August-eu-ota/unpacked-vendor-boot/vendor_ramdisk00').read_bytes()));combined={**vendor,**entries,**extra}
    storage=entries['etc/lynx/bootstrap-storage-modules.load']['data'].decode().splitlines();require(storage[-1]=='ufs-mediatek-mod.ko' and len(storage)==7,'Storage order changed')
    radio=extra['etc/lynx/wifi-radio-modules.load']['data'].decode().splitlines();order=['mtk_wdt.ko','reboot-mode.ko','syscon-reboot-mode.ko']+names[:34]+storage[:-1]+['clk-bringup.ko',storage[-1]]+radio
    loaded=set();versions={};module_rows=[]
    for name in order:
        raw=combined['lib/modules/'+name]['data'];meta=module_metadata(raw)['values'];deps={d.replace('-','_') for text in meta.get('depends',[]) for d in text.split(',') if d};require(deps<=loaded,'Unloaded module dependency for '+name+': '+str(sorted(deps-loaded)))
        for crc,symbol in struct.iter_unpack('<Q56s',elf64(raw)['sections']['__versions']):
            symbol=symbol.split(b'\0')[0];require(symbol not in versions or versions[symbol]==crc,'Module CRC conflict');versions[symbol]=crc
        loaded.add(meta['name'][0].replace('-','_'));module_rows.append(dict(file=name,sha256=sha(raw)))
    require(not any(n in order for n in ['mtu3.ko','xhci-mtk-hcd.ko','rpmb-mtk.ko']),'Unexpected controller/security load')
    native=[p for p in sorted((P/'artifacts').glob('emulated-wifi-v7-journals-*/result.json')) if json.loads(p.read_text()).get('passed') and json.loads(p.read_text()).get('candidate_sha256')==SHA];require(native,'Passing matching ARM64 integration test missing')
    guards=sorted((P/'artifacts').glob('emulated-wifi-v7-image-*/result.json'));require(guards,'Exact image guard missing');g=json.loads(guards[-1].read_text());require(g['candidate_sha256']==SHA and g['module_checkpoint_failure_guard_observed'] and not g['kernel_reboot_command_observed'],'Hardware reset guard failed')
    contact=subprocess.run(['python3',str(R/'tools/lynx_wifi_v7_contact.py'),'--self-test'],capture_output=True,text=True,timeout=15);require(contact.returncode==0,'Pinned-identity collector self-test failed')
    model=R/'tools/avb-host/avb-boot-model';mref=json.loads((P/'docs/avb-boot-model-results.json').read_text());require(sha(model.read_bytes())==mref['binary_sha256'],'Boot model changed')
    for unlocked in ['0','1']:
        result=subprocess.run([str(model),str(P/'artifacts/stock-cph2493-August-eu-ota'),str(F/'nord3-busybox-candidate.img'),'0',unlocked],capture_output=True,text=True,timeout=30);require(result.returncode==0 and json.loads(result.stdout)['slot_data_returned']==(unlocked=='1'),'Boot policy changed')
    out=P/'docs/wifi-v7-image-validation.json';report=dict(passed=True,candidate_sha256=SHA,native_receipt=str(native[-1]),guard_receipt=str(guards[-1]),modules=module_rows,network_payload_unchanged=True,phone_contacted=False,hardware_wifi_verified=False,limits='Preserves the successful guarded UFS sequence and validated read-only payload/calibration/SSH software. Actual block discovery, calibration, radio association and SSH are still hardware trial results to obtain.')
    out.write_text(json.dumps(report,indent=2)+'\n');print(out)
if __name__=='__main__':main()
