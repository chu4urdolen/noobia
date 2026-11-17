"""Preserve the vendor firmware directory; mirror matching firmware instead of replacing it."""
import gzip,hashlib,json,secrets,struct
from pathlib import Path
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
from network_userspace import put
from prepare_busybox_diagnostics import pack
P=Path(__file__).resolve().parent;F=P/'artifacts/busybox-wifi-ssh-twostage-v7';OUT=P/'artifacts/busybox-wifi-ssh-twostage-v10'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
    require(not OUT.exists(),'Preserve prior images')
    original=(F/'nord3-busybox-candidate.img').read_bytes();require(sha(original)=='9a17b8e72e8e8fe8928f551fcf593cee1d19a712affe498f23f637e7ac4da00c','Reference changed')
    boot=read_boot_v4(original);entries=read_newc(decompress(boot['ramdisk']));oldpayload=(F/'supplement.cpio.gz').read_bytes()
    require(sha(oldpayload)=='b0aa0fbc0b8646e77e4c71aaf2caf3951033cd513649741e0daf677f5a5afb24','Payload reference changed')
    extra=read_newc(decompress(oldpayload));alias=extra['vendor/firmware']
    require(alias['mode']&0o170000==0o120000 and alias['data']==b'../lib/firmware','Unexpected firmware alias')
    put(extra,'vendor/firmware',b'',0o40755)
    mirrored=[]
    for name,item in list(extra.items()):
        if name.startswith('lib/firmware/') and item['mode']&0o170000==0o100000:
            target='vendor/firmware/'+name[len('lib/firmware/'):]
            require(target not in extra,'Existing firmware destination')
            extra[target]=dict(item);mirrored.append({'source':name,'destination':target,'sha256':sha(item['data'])})
    require(mirrored,'No firmware to mirror')
    # Stock /odm/etc is a symlink to /vendor/odm/etc; retain that link.
    relocated={}
    for name,item in list(extra.items()):
        if name=='odm/etc' or name.startswith('odm/etc/'):
            target='vendor/odm/etc'+name[len('odm/etc'):]
            require(target not in extra,'ODM destination collision')
            relocated[target]=item
            del extra[name]
    require(relocated,'No ODM configuration to relocate')
    put(extra,'vendor/odm',b'',0o40755)
    extra.update(relocated)
    payload=gzip.compress(decompress(pack(extra)),mtime=0)
    require(len(payload)<40000000,'Payload too large')
    put(entries,'etc/lynx/payload-bytes',(str(len(payload))+'\n').encode(),0o100644)
    put(entries,'etc/lynx/payload-sha256',(sha(payload)+'\n').encode(),0o100644)
    token=secrets.token_hex(16);put(entries,'etc/lynx/session-token',(token+'\n').encode(),0o100644)
    rd=pack(entries);header=bytearray(original[:1584]);struct.pack_into('<I',header,12,len(rd));align=lambda n:(n+4095)//4096*4096
    loaded=bytes(header).ljust(4096,b'\0')+boot['kernel'].ljust(align(len(boot['kernel'])),b'\0')+rd.ljust(align(len(rd)),b'\0');coverage=struct.unpack('!4sIIQQQ28x',original[-64:])[3];require(len(loaded)<=coverage,'Metadata overlap')
    image=bytearray(loaded.ljust(coverage,b'\0')+original[coverage:]);offset=25165824;require(offset+len(payload)<len(image)-4096,'Payload overlaps footer')
    image[offset:offset+max(len(payload),len(oldpayload))]=payload.ljust(max(len(payload),len(oldpayload)),b'\0');image=bytes(image)
    OUT.mkdir(mode=0o700)
    for name,data in [('nord3-busybox-candidate.img',image),('init-source',entries['init']['data']),('supplement.cpio.gz',payload),('diag-hooks.sh',(F/'diag-hooks.sh').read_bytes())]:
        path=OUT/name;path.write_bytes(data);path.chmod(0o600)
    report=json.loads((F/'build-validation.json').read_text());report.update(candidate=str(OUT/'nord3-busybox-candidate.img'),candidate_sha256=sha(image),ramdisk_bytes=len(rd),session_token=token,supplement_bytes=len(payload),supplement_sha256=sha(payload),supplement_entry_names=list(extra),firmware_directory_preserved=True,mirrored_firmware=mirrored,odm_configuration_relocated=list(relocated),phone_contacted=False,flash_eligible=False)
    (OUT/'build-validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(candidate_sha256=sha(image),ramdisk_bytes=len(rd),supplement_bytes=len(payload),mirrored_count=len(mirrored)),indent=2))
if __name__=='__main__':main()
