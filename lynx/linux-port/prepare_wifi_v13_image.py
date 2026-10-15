"""Preserve V12 radio startup; refine only its RAM diagnostic result parser."""
import hashlib,json,secrets,struct
from pathlib import Path
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
from network_userspace import put
from prepare_busybox_diagnostics import pack
P=Path(__file__).resolve().parent
F=P/'artifacts/busybox-wifi-ssh-twostage-v12'
OUT=P/'artifacts/busybox-wifi-ssh-twostage-v13'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
    require(not OUT.exists(),'Preserve prior artifacts')
    raw=(F/'nord3-busybox-candidate.img').read_bytes()
    require(sha(raw)=='1e51aeff4eae67f50c5bce85986d7f423a14c6274332b99d2e64015288f8b73b','Parent changed')
    boot=read_boot_v4(raw);entries=read_newc(decompress(boot['ramdisk']))
    old=(F/'station-failure-parser.sh').read_bytes();new=(P/'power-failure-parser.sh').read_bytes()
    timing=entries['bin/boot-proof-reboot']['data'];require(timing.count(old)==1,'Parser boundary changed')
    timing=timing.replace(old,new);put(entries,'bin/boot-proof-reboot',timing)
    token=secrets.token_hex(16);put(entries,'etc/lynx/session-token',(token+'\n').encode(),0o100644)
    rd=pack(entries);header=bytearray(raw[:1584]);struct.pack_into('<I',header,12,len(rd));align=lambda n:(n+4095)//4096*4096
    loaded=bytes(header).ljust(4096,b'\0')+boot['kernel'].ljust(align(len(boot['kernel'])),b'\0')+rd.ljust(align(len(rd)),b'\0')
    coverage=struct.unpack('!4sIIQQQ28x',raw[-64:])[3];require(len(loaded)<=coverage,'Metadata overlap')
    image=loaded.ljust(coverage,b'\0')+raw[coverage:]
    OUT.mkdir(mode=0o700)
    for name in ['init-source','supplement.cpio.gz','wifi-runtime.sh','radio-clock-guard.sh','diag-hooks.sh']:
        f=OUT/name;f.write_bytes((F/name).read_bytes());f.chmod(0o600)
    for name,data in [('nord3-busybox-candidate.img',image),('timing-runtime-source',timing),('power-failure-parser.sh',new)]:
        f=OUT/name;f.write_bytes(data);f.chmod(0o600)
    report=json.loads((F/'build-validation.json').read_text());codes=report['result_codes']
    labels=['power-control timeout diagnostic','power-thread invalid callback diagnostic']+['wlanProbe raw failure reason '+str(n) for n in range(8)]+['inner power diagnostic unavailable or unrecognized']
    codes.update({str(i):v for i,v in enumerate(labels,25)})
    report.update(candidate=str(OUT/'nord3-busybox-candidate.img'),candidate_sha256=sha(image),ramdisk_bytes=len(rd),session_token=token,timing_runtime_sha256=sha(timing),station_parser_sha256=sha(new),result_codes=codes,phone_contacted=False,flash_eligible=False,diagnostic_version='v13 inner power failure',parent_sha256=sha(raw))
    (OUT/'build-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'candidate_sha256':sha(image),'ramdisk_bytes':len(rd)},indent=2))
if __name__=='__main__':main()
