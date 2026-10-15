"""Build Wi-Fi v5 with five verified power-controller clock suppliers."""
import hashlib,json,secrets,struct
from pathlib import Path
from image_formats import read_boot_v4,read_newc,require,module_metadata
from ramdisk_codec import decompress
from network_userspace import put
from prepare_busybox_diagnostics import pack
P=Path(__file__).resolve().parent;F=P/'artifacts/busybox-wifi-ssh-twostage-v4';OUT=P/'artifacts/busybox-wifi-ssh-twostage-v5';S=P/'artifacts/stock-cph2493-August-eu-ota'
def main():
    require(not OUT.exists(),'Preserve prior candidates')
    original=(F/'nord3-busybox-candidate.img').read_bytes();require(hashlib.sha256(original).hexdigest()=='0abe578cdc82a8f42b6bd812f3217dcc622f2a980d93e3c3418bc6dadf731af7','Reference changed')
    boot=read_boot_v4(original);entries=read_newc(decompress(boot['ramdisk']))
    audit=json.loads((P/'docs/scpsys-clock-suppliers.json').read_text());added=audit['missing_supplier_modules']
    require(added==['clk-mt6983-cam.ko','clk-mt6983-img.ko','clk-mt6983-mdp_grp.ko','clk-mt6983-mm.ko','clk-mt6983-vcodec.ko'],'Supplier set changed')
    hashes={}
    for name in added:
        raw=(S/'vendor-ramdisk-unpacked/lib/modules'/name).read_bytes();meta=module_metadata(raw)
        require(meta['values']['scmversion']==['g311738fbb5a8'] and meta['values']['depends']==['clk-common'],'Unexpected supplier ABI/dependencies')
        put(entries,'lib/modules/'+name,raw,0o100644);hashes[name]=hashlib.sha256(raw).hexdigest()
    modules=entries['etc/lynx/bootstrap-base-modules.load']['data'].decode().splitlines();index=modules.index('mtk-scpsys.ko');modules[index:index]=added
    put(entries,'etc/lynx/bootstrap-base-modules.load',('\n'.join(modules)+'\n').encode(),0o100644)
    token=secrets.token_hex(16);put(entries,'etc/lynx/session-token',(token+'\n').encode(),0o100644)
    ramdisk=pack(entries);header=bytearray(original[:1584]);struct.pack_into('<I',header,12,len(ramdisk))
    cmdline=(boot['cmdline']+' fw_devlink=permissive').encode();require(len(cmdline)<1536,'Commandline too long');header[44:1580]=cmdline.ljust(1536,b'\0')
    align=lambda n:(n+4095)//4096*4096
    loaded=bytes(header).ljust(4096,b'\0')+boot['kernel'].ljust(align(len(boot['kernel'])),b'\0')+ramdisk.ljust(align(len(ramdisk)),b'\0')
    coverage=struct.unpack('!4sIIQQQ28x',original[-64:])[3];require(len(loaded)<=coverage,'Loaded area exceeds unchanged metadata boundary')
    image=loaded.ljust(coverage,b'\0')+original[coverage:];require(len(image)==len(original),'Image size changed')
    OUT.mkdir(mode=0o700)
    for name,raw in [('nord3-busybox-candidate.img',image),('init-source',entries['init']['data']),('supplement.cpio.gz',(F/'supplement.cpio.gz').read_bytes()),('diag-hooks.sh',(F/'diag-hooks.sh').read_bytes()),('wifi-runtime.sh',(F/'wifi-runtime.sh').read_bytes())]:
        path=OUT/name;path.write_bytes(raw);path.chmod(0o600)
    report=json.loads((F/'build-validation.json').read_text());report.update(candidate=str(OUT/'nord3-busybox-candidate.img'),candidate_sha256=hashlib.sha256(image).hexdigest(),init_sha256=hashlib.sha256(entries['init']['data']).hexdigest(),ramdisk_bytes=len(ramdisk),session_token=token,base_modules=modules,added_power_clock_sha256=hashes,commandline=cmdline.decode(),remaining_loaded_area_bytes=coverage-len(loaded),phone_contacted=False,hardware_wifi_verified=False,flash_eligible=False)
    (OUT/'build-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({key:report[key] for key in ['candidate_sha256','ramdisk_bytes','remaining_loaded_area_bytes','flash_eligible']},indent=2))
if __name__=='__main__':main()
