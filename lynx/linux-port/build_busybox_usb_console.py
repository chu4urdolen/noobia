"""Prepare the BusyBox ACM-console image offline; never flash."""
import hashlib
import json
from pathlib import Path
import struct
from image_formats import read_boot_v4,read_newc,require,module_metadata
from ramdisk_codec import compress_legacy,decompress
from audit_early_boot import read_fdt,cells,strings

BASE=Path(__file__).resolve().parent
STOCK=BASE/'artifacts/stock-cph2493-August-eu-ota'
SOURCE=BASE/'artifacts/busybox-August-lz4-avb'
OUTPUT=BASE/'artifacts/busybox-August-busybox-console'
MODULES=['mtk_wdt.ko','reboot-mode.ko','syscon-reboot-mode.ko'] + [name for name in (BASE/'artifacts/busybox-August-usb-device-xhci/usb-modules.load').read_text().splitlines() if name != 'mtk_wdt.ko']

def main():
    require(not OUTPUT.exists(),'Preserve existing proof artifact')
    stock=(STOCK/'boot.img').read_bytes()
    require(hashlib.sha256(stock).hexdigest()=='a67f03d7b826b834c23653b67eaa6efa971eb70ef8af19eee4d33fb5fc7fe995','Stock image changed')
    source=(SOURCE/'nord3-busybox-candidate.img').read_bytes()
    old=json.loads((SOURCE/'build-validation.json').read_text())
    require(hashlib.sha256(source).hexdigest()==old['candidate_sha256'],'Native base changed')
    boot=read_boot_v4(source)
    require(boot['kernel']==read_boot_v4(stock)['kernel'],'Exact stock kernel required')
    nodes,info=read_fdt((STOCK/'unpacked-vendor-boot/dtb').read_bytes())
    path='/watchdog@1c007000/reboot-mode'
    mode=nodes[path]
    require(strings(mode['compatible'])==['syscon-reboot-mode'],'Unexpected mode driver')
    require(cells(mode['mode-bootloader'])==[3] and cells(mode['offset'])==[36] and cells(mode['mask'])==[15],'Unexpected stock reboot mode')
    audit=json.loads((BASE/'docs/august-vendor-ramdisk-audit.json').read_text())
    expected={item['path']:item['sha256'] for item in audit['entries']}
    modules=[]
    for name in MODULES:
        data=(STOCK/'vendor-ramdisk-unpacked/lib/modules'/name).read_bytes()
        digest=hashlib.sha256(data).hexdigest()
        require(digest==expected['lib/modules/'+name],'Stock module changed')
        metadata=module_metadata(data)['values']
        modules.append(dict(name=name,sha256=digest,metadata=metadata))
    entries=read_newc(decompress(boot['ramdisk']))
    init=(BASE/'init-busybox-usb-console').read_bytes()
    proof=(BASE/'init-boot-proof').read_bytes()
    guard=proof[proof.index(b'wdt_ready=0'):proof.index(b'\nif [ "$wdt_ready"')]
    init=init.replace(b'# LYNX_RESET_GUARD',guard)
    init=init.replace(b'# LYNX_USB_ROLE_HELPER',(BASE/'usb-device-mode-xhci.sh').read_bytes())
    entries['etc/lynx-usb-modules.load']=dict(mode=0o100644,uid=0,gid=0,rdevmajor=0,rdevminor=0,data=('\n'.join(name for name in MODULES if name not in ['reboot-mode.ko','syscon-reboot-mode.ko'])+'\n').encode())
    helper=(BASE/'artifacts/boot-proof-reboot.elf').read_bytes()
    require(helper[:4]==b'\x7fELF' and struct.unpack_from('<H',helper,18)[0]==183,'Expected ARM64 helper')
    entries['init']['data']=init
    entries['bin/boot-proof-reboot']=dict(mode=0o100755,uid=0,gid=0,rdevmajor=0,rdevminor=0,data=helper)
    archive=bytearray()
    for inode,(name,item) in enumerate([*entries.items(),('TRAILER!!!',dict(mode=0,uid=0,gid=0,rdevmajor=0,rdevminor=0,data=b''))],1):
        encoded=name.encode()+b'\0'
        fields=[inode,item['mode'],item['uid'],item['gid'],1,0,len(item['data']),0,0,item['rdevmajor'],item['rdevminor'],len(encoded),0]
        archive+=b'070701'+''.join(f'{value:08x}' for value in fields).encode()+encoded
        archive+=b'\0'*(-len(archive)%4);archive+=item['data'];archive+=b'\0'*(-len(archive)%4)
    archive+=b'\0'*(-len(archive)%512)
    require(read_newc(archive)==entries,'CPIO round trip failed')
    ramdisk=compress_legacy(bytes(archive))
    header=bytearray(source[:1584]);struct.pack_into('<I',header,12,len(ramdisk))
    align=lambda value:(value+4095)//4096*4096
    payload=bytes(header).ljust(4096,b'\0')+boot['kernel'].ljust(align(len(boot['kernel'])),b'\0')+ramdisk.ljust(align(len(ramdisk)),b'\0')
    magic,_,_,coverage,offset,size=struct.unpack('!4sIIQQQ28x',stock[-64:])
    require(magic==b'AVBf' and len(payload)<=coverage<=offset,'Payload overlaps stock metadata')
    image=payload.ljust(coverage,b'\0')+stock[coverage:]
    require(len(image)==67108864,'Partition size changed')
    report=dict(purpose='Live BusyBox ACM shell, no networking yet', candidate_sha256=hashlib.sha256(image).hexdigest(),image_bytes=len(image),
                kernel_sha256=hashlib.sha256(boot['kernel']).hexdigest(),
                init_sha256=hashlib.sha256(init).hexdigest(),helper_sha256=hashlib.sha256(helper).hexdigest(),
                modules=modules,stock_reboot_mode_node=path,stock_reboot_mode_info=info,
                standard_reboot_command='bootloader',bootloader_mode_value=3,
                repeated_reboot_allowed=False,partition_writes_allowed=False,
                persistent_oem_metadata_preserved=True,oem_payload_hash_matches=False,
                vendor_ramdisk_sha256=hashlib.sha256((STOCK/'unpacked-vendor-boot/vendor_ramdisk00').read_bytes()).hexdigest(),
                phone_contacted=False,hardware_boot_proven=False,flash_eligible=False,
                limits='Prepared offline only. A Fastboot return alone cannot prove native boot; reset-cause and mode evidence must corroborate it. USB console hardware behavior is unproven. Bound gadget does not prove host enumeration; module-probe hangs can still require physical Fastboot return.')
    OUTPUT.mkdir()
    (OUTPUT/'nord3-busybox-candidate.img').write_bytes(image)
    (OUTPUT/'initramfs.cpio.lz4').write_bytes(ramdisk)
    (OUTPUT/'init-source').write_bytes(init)
    (OUTPUT/'build-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({key:report[key] for key in ['purpose','candidate_sha256','image_bytes','kernel_sha256','flash_eligible']},indent=2))

if __name__=='__main__':main()
