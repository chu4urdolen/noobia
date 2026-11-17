"""Read retained logs with the proven34 prefix; no storage-controller activation."""
import hashlib,json,secrets,struct
from pathlib import Path
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
from network_userspace import put
from prepare_busybox_diagnostics import pack
P=Path(__file__).resolve().parent;F=P/'artifacts/busybox-module-progress-debug-34-v1';OUT=P/'artifacts/busybox-retained-wifi-v7-query-v1'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
    require(not OUT.exists(),'Preserve prior images')
    original=(F/'nord3-busybox-candidate.img').read_bytes();require(sha(original)=='6070a324cbbfc8a1262b94ae111e3a6b3a4cb330e66af54d2363a3e2c5b7edad','Proven34 reference changed')
    boot=read_boot_v4(original);entries=read_newc(decompress(boot['ramdisk']))
    suffix=(P/'lynx-power-controller-progress-runtime.sh').read_bytes()+b'\nlynx_module_progress\nstop\n';require(entries['init']['data'].endswith(suffix),'Reference runtime boundary changed')
    runtime=(P/'lynx-retained-wifi-v7-runtime.sh').read_bytes();init=entries['init']['data'][:-len(suffix)]+runtime+b'\nlynx_module_progress\nstop\n';put(entries,'init',init)
    reference_manifest=json.loads((P/'artifacts/busybox-wifi-ssh-twostage-v7/build-validation.json').read_text());require(reference_manifest['candidate_sha256']=='9a17b8e72e8e8fe8928f551fcf593cee1d19a712affe498f23f637e7ac4da00c','Traced reference changed')
    reference=reference_manifest['session_token'];put(entries,'etc/lynx/reference-ufs-token',(reference+'\n').encode(),0o100644)
    token=secrets.token_hex(16);put(entries,'etc/lynx/session-token',(token+'\n').encode(),0o100644)
    rd=pack(entries);header=bytearray(original[:1584]);struct.pack_into('<I',header,12,len(rd));align=lambda n:(n+4095)//4096*4096
    loaded=bytes(header).ljust(4096,b'\0')+boot['kernel'].ljust(align(len(boot['kernel'])),b'\0')+rd.ljust(align(len(rd)),b'\0');coverage=struct.unpack('!4sIIQQQ28x',original[-64:])[3];require(len(loaded)<=coverage,'Metadata overlap');image=loaded.ljust(coverage,b'\0')+original[coverage:]
    OUT.mkdir(mode=0o700)
    for name,raw in [('nord3-busybox-candidate.img',image),('init-source',init),('runtime-source',runtime)]:
        path=OUT/name;path.write_bytes(raw);path.chmod(0o600)
    codes={'0': 'no checksum-valid Wi-Fi v7 reference capsule in selected bounded record', '1': 'bootstrap failed: base drivers (151)', '2': 'bootstrap failed: storage drivers or guards (152)', '3': 'bootstrap failed: partition discovery (153)', '4': 'bootstrap failed: own boot_a payload read/verification/extraction (154)', '5': 'bootstrap failed: other status', '6': 'Wi-Fi worker failed: status not retrieved', '7': 'last retained major phase: base drivers', '8': 'last retained major phase: storage or UFS clock/probe', '9': 'last retained major phase: partition discovery', '10': 'last retained major phase: own boot_a payload', '11': 'last retained major phase: payload extracted or factory calibration', '12': 'last retained major phase: radio initialization', '13': 'reference capsule retained; network phase or no recognized failure/major phase', '14': 'base prefix pending', '15': 'retained query pending', '16': 'base insertion failed', '17': 'reference or progress malformed', '18': 'worker state unavailable'}
    report=json.loads((F/'build-validation.json').read_text());report.update(candidate_sha256=sha(image),init_sha256=sha(init),ramdisk_bytes=len(rd),runtime_sha256=sha(runtime),session_token=token,reference_ufs_token=reference,reference_candidate_sha256=reference_manifest['candidate_sha256'],retained_ufs_trace_query=True,result_codes=codes,target_delays_seconds={str(i):120+5*i for i in range(19)},timing_match_tolerance_seconds=2,observation_seconds=270,phone_contacted=False,flash_eligible=False)
    (OUT/'build-validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(candidate_sha256=sha(image),ramdisk_bytes=len(rd)),indent=2))
if __name__=='__main__':main()
