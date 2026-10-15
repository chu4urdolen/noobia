"""Offline variant using a standard kernel driver-ordering parameter."""
import argparse
import hashlib
import json
import secrets
import struct
from pathlib import Path
from image_formats import read_boot_v4, read_newc, require
from network_userspace import put
from prepare_busybox_diagnostics import pack
from ramdisk_codec import decompress

P = Path(__file__).resolve().parent
SOURCES = {'storage': ('busybox-storage-outcome-v1','85d219fd6625897638ef70ee9abd9959cbf625f0063cecf19905a70f03b5e358','busybox-storage-outcome-v2'),
           'wifi': ('busybox-wifi-ssh-twostage-v4','0abe578cdc82a8f42b6bd812f3217dcc622f2a980d93e3c3418bc6dadf731af7','busybox-wifi-ssh-twostage-v5')}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--kind',choices=list(SOURCES),required=True)
    args=parser.parse_args()
    folder,sha,target=SOURCES[args.kind]
    original=P/'artifacts'/folder
    out=P/'artifacts'/target
    require(not out.exists(),'Preserve previous variants')
    data=(original/'nord3-busybox-candidate.img').read_bytes()
    require(hashlib.sha256(data).hexdigest()==sha,'Reference changed')
    boot=read_boot_v4(data)
    require(boot['cmdline']=='rdinit=/init panic=10 noobia.usb=1','Unexpected original command line')
    # Preserve kernel bytes; change only its standard boot command-line field.
    parameter=(boot['cmdline']+' fw_devlink=permissive').encode()
    entries=read_newc(decompress(boot['ramdisk']))
    token=secrets.token_hex(16)
    put(entries,'etc/lynx/session-token',(token+'\n').encode(),0o100644)
    ramdisk=pack(entries)
    header=bytearray(data[:1584])
    header[44:1580]=parameter.ljust(1536,b'\0')
    struct.pack_into('<I',header,12,len(ramdisk))
    align=lambda n:(n+4095)//4096*4096
    loaded=bytes(header).ljust(4096,b'\0')+boot['kernel'].ljust(align(len(boot['kernel'])),b'\0')+ramdisk.ljust(align(len(ramdisk)),b'\0')
    _,_,_,coverage,offset,size=struct.unpack('!4sIIQQQ28x',data[-64:])
    require(len(loaded)<=coverage,'Loaded area overlaps metadata')
    image=loaded.ljust(coverage,b'\0')+data[coverage:]
    require(len(image)==len(data) and image[coverage:]==data[coverage:],'Unrelated supplemental/metadata area changed')
    parsed=read_boot_v4(image)
    require(parsed['kernel']==boot['kernel'] and parsed['cmdline']==parameter.decode(),'Kernel/command line changed unexpectedly')
    require(read_newc(decompress(parsed['ramdisk']))==entries,'Archive round trip failed')
    out.mkdir(mode=0o700)
    for name,raw in [('nord3-busybox-candidate.img',image),('init-source',entries['init']['data'])]:
        path=out/name;path.write_bytes(raw);path.chmod(0o600)
    for name in ['supplement.cpio.gz','diag-hooks.sh','wifi-runtime.sh']:
        if (original/name).exists():
            path=out/name;path.write_bytes((original/name).read_bytes());path.chmod(0o600)
    report=json.loads((original/'build-validation.json').read_text())
    report.update(candidate=str(out/'nord3-busybox-candidate.img'),candidate_sha256=hashlib.sha256(image).hexdigest(),session_token=token,
                  ramdisk_bytes=len(ramdisk),kernel_cmdline=parameter.decode(),parameter_scope='inferred device dependency ordering; no security authentication change',
                  phone_contacted=False,flash_eligible=False,hardware_wifi_verified=False)
    (out/'build-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['candidate','candidate_sha256','ramdisk_bytes','kernel_cmdline']},indent=2))


if __name__=='__main__':main()
