"""Measure adding only verified stock power-domain clock suppliers; no flash."""
import hashlib,json,struct,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;P=ROOT/'linux-port';S=P/'artifacts/stock-cph2493-August-eu-ota'
sys.path.insert(0,str(P))
from image_formats import read_boot_v4,read_newc,module_metadata
from ramdisk_codec import decompress
from network_userspace import put
from prepare_busybox_diagnostics import pack
def main():
    ref=P/'artifacts/busybox-timeout-site-v1/nord3-busybox-candidate.img';raw=ref.read_bytes();boot=read_boot_v4(raw)
    entries=read_newc(decompress(boot['ramdisk']));audit=json.loads((P/'docs/scpsys-clock-suppliers.json').read_text());added=[]
    for name in audit['missing_supplier_modules']:
        data=(S/'vendor-ramdisk-unpacked/lib/modules'/name).read_bytes();metadata=module_metadata(data)
        put(entries,'lib/modules/'+name,data,0o100644)
        added.append({'module':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'modinfo':metadata['values']})
    modules=entries['etc/lynx/bootstrap-base-modules.load']['data'].decode().splitlines();index=modules.index('mtk-scpsys.ko')
    modules[index:index]=audit['missing_supplier_modules'];put(entries,'etc/lynx/bootstrap-base-modules.load',('\n'.join(modules)+'\n').encode(),0o100644)
    compressed=pack(entries);coverage=struct.unpack('!4sIIQQQ28x',raw[-64:])[3]
    aligned=lambda n:(n+4095)//4096*4096
    loaded_bytes=4096+aligned(len(boot['kernel']))+aligned(len(compressed))
    report={'phone_contacted':False,'reference_sha256':hashlib.sha256(raw).hexdigest(),'added_modules':added,'base_order':modules,'ramdisk_bytes':len(compressed),'loaded_bytes':loaded_bytes,'metadata_boundary':coverage,'fits_existing_geometry':loaded_bytes<=coverage,'remaining_bytes':coverage-loaded_bytes,'limits':'Size/ABI metadata only; no image written, no module loaded, no runtime binding or Wi-Fi proven.'}
    out=P/'docs/power-clock-image-fit.json';out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({key:report[key] for key in ['ramdisk_bytes','loaded_bytes','metadata_boundary','fits_existing_geometry','remaining_bytes','added_modules']},indent=2))
if __name__=='__main__':main()
