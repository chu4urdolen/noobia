"""Preserve v7 startup/payload; replace failure timing and stop before Wi-Fi."""
import hashlib,json,secrets,struct
from pathlib import Path
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
from network_userspace import put
from prepare_busybox_diagnostics import pack
P=Path(__file__).resolve().parent;F=P/'artifacts/busybox-wifi-ssh-twostage-v7';OUT=P/'artifacts/busybox-bootstrap-timing-v1'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
    require(not OUT.exists(),'Preserve prior artifacts')
    original=(F/'nord3-busybox-candidate.img').read_bytes();require(sha(original)=='9a17b8e72e8e8fe8928f551fcf593cee1d19a712affe498f23f637e7ac4da00c','Reference changed')
    boot=read_boot_v4(original);entries=read_newc(decompress(boot['ramdisk']));init=entries['init']['data'];runtime=(P/'lynx-bootstrap-timing-runtime.sh').read_bytes()
    require(init.count(b'    /bin/boot-proof-reboot\n')==1,'Bootstrap reset boundary changed')
    init=init.replace(b'    /bin/boot-proof-reboot\n',b'    lynx_bootstrap_timing_return\n')
    boundary=b"\nlog 'WIFI_TWO_STAGE_BOOTSTRAP_BEGIN'\n";require(init.count(boundary)==1,'Entry boundary changed')
    init=init.split(boundary)[0]+b'\n'+runtime+b'''\nlynx_bootstrap_timing_clock || stop
printf '%s\n' "$bt_seconds" > /run/lynx/bootstrap-timing-start || stop
log 'WIFI_TWO_STAGE_BOOTSTRAP_BEGIN'
lynx_wifi_bootstrap || stop
log 'BOOTSTRAP_TIMING_PAYLOAD_READY; RADIO_NOT_STARTED'
lynx_bootstrap_timing_return
stop
''';put(entries,'init',init)
    token=secrets.token_hex(16);put(entries,'etc/lynx/session-token',(token+'\n').encode(),0o100644)
    rd=pack(entries);header=bytearray(original[:1584]);struct.pack_into('<I',header,12,len(rd));align=lambda n:(n+4095)//4096*4096
    loaded=bytes(header).ljust(4096,b'\0')+boot['kernel'].ljust(align(len(boot['kernel'])),b'\0')+rd.ljust(align(len(rd)),b'\0');coverage=struct.unpack('!4sIIQQQ28x',original[-64:])[3];require(len(loaded)<=coverage,'Metadata overlap');image=loaded.ljust(coverage,b'\0')+original[coverage:]
    OUT.mkdir(mode=0o700)
    for name,data in [('nord3-busybox-candidate.img',image),('init-source',init),('runtime-source',runtime)]:
        path=OUT/name;path.write_bytes(data);path.chmod(0o600)
    codes={'0':'bootstrap completed: own boot_a payload verified and extracted; radio not started','1':'bootstrap failed: base drivers (151)','2':'bootstrap failed: storage drivers or guards (152)','3':'bootstrap failed: partition discovery (153)','4':'bootstrap failed: own boot_a payload (154)','5':'bootstrap failed: other numeric status','6':'bootstrap result unavailable/deadline','7':'bootstrap result malformed'}
    report=json.loads((F/'build-validation.json').read_text());report.update(candidate=str(OUT/'nord3-busybox-candidate.img'),candidate_sha256=sha(image),init_sha256=sha(init),ramdisk_bytes=len(rd),session_token=token,runtime_sha256=sha(runtime),radio_started=False,bootstrap_timing_query=True,result_codes=codes,target_delays_seconds={str(i):240+5*i for i in range(8)},timing_match_tolerance_seconds=2,worker_sample_seconds=180,observation_seconds=360,flash_eligible=False,phone_contacted=False)
    (OUT/'build-validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(candidate_sha256=sha(image),ramdisk_bytes=len(rd)),indent=2))
if __name__=='__main__':main()
