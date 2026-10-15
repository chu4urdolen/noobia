"""Audit exact early-module dependencies and symbol-version agreement."""
import hashlib,json,struct,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;P=ROOT/'linux-port'
sys.path.insert(0,str(P))
from image_formats import read_boot_v4,read_newc,elf64,module_metadata,require
from ramdisk_codec import decompress
def main():
    F=P/'artifacts/busybox-module-progress-debug-28-v1';image=(F/'nord3-busybox-candidate.img').read_bytes()
    vendor=P/'artifacts/stock-cph2493-August-eu-ota/unpacked-vendor-boot/vendor_ramdisk00'
    entries={**read_newc(decompress(vendor.read_bytes())),**read_newc(decompress(read_boot_v4(image)['ramdisk']))}
    prefix=entries['etc/lynx/progress-modules.load']['data'].decode().splitlines()
    loaded=set();rows=[];versions={};conflicts=[];missing=[]
    for name in ['mtk_wdt.ko','reboot-mode.ko','syscon-reboot-mode.ko']+prefix:
        raw=entries['lib/modules/'+name]['data'];meta=module_metadata(raw)['values'];parsed=elf64(raw)
        deps=[dep.replace('-','_') for text in meta.get('depends',[]) for dep in text.split(',') if dep]
        absent=sorted(set(deps)-loaded)
        if absent:missing.append({'module':name,'dependencies_not_yet_loaded':absent})
        table=parsed['sections'].get('__versions',b'');require(len(table)%64==0,'Unexpected modversion record size')
        for offset in range(0,len(table),64):
            crc=struct.unpack_from('<Q',table,offset)[0];symbol=table[offset+8:offset+64].split(b'\0')[0].decode()
            if symbol in versions and versions[symbol]!=crc:conflicts.append({'symbol':symbol,'module':name,'crc':hex(crc),'prior_crc':hex(versions[symbol])})
            versions[symbol]=crc
        module_name=meta['name'][0].replace('-','_');loaded.add(module_name)
        rows.append({'file':name,'module_name':module_name,'sha256':hashlib.sha256(raw).hexdigest(),'depends':deps,'vermagic':meta['vermagic'],'imported_version_records':len(table)//64,'module_layout_crc':hex(versions.get('module_layout',0))})
    report={'passed':not missing and not conflicts,'phone_contacted':False,'candidate_sha256':hashlib.sha256(image).hexdigest(),'module_order':rows,'dependencies_not_yet_loaded':missing,'shared_crc_conflicts':conflicts,'limits':'Exact stock modinfo and imported CRC consistency; builtin-provider ABI and hardware initialization require the native/runtime tests.'}
    out=P/'docs/module-progress-dependencies.json';out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'report':str(out),'passed':report['passed'],'dependencies_not_yet_loaded':missing,'shared_crc_conflicts':conflicts},indent=2));require(report['passed'],'Dependency audit failed')
if __name__=='__main__':main()
