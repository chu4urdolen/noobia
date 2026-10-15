"""Read retained logs with the proven34 prefix; no storage-controller activation."""
import hashlib,json,secrets,struct
from pathlib import Path
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
from network_userspace import put
from prepare_busybox_diagnostics import pack
P=Path(__file__).resolve().parent;F=P/'artifacts/busybox-module-progress-debug-34-v1';OUT=P/'artifacts/busybox-retained-refclk-trace-query-v1'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
    require(not OUT.exists(),'Preserve prior images')
    original=(F/'nord3-busybox-candidate.img').read_bytes();require(sha(original)=='6070a324cbbfc8a1262b94ae111e3a6b3a4cb330e66af54d2363a3e2c5b7edad','Proven34 reference changed')
    boot=read_boot_v4(original);entries=read_newc(decompress(boot['ramdisk']))
    suffix=(P/'lynx-power-controller-progress-runtime.sh').read_bytes()+b'\nlynx_module_progress\nstop\n';require(entries['init']['data'].endswith(suffix),'Reference runtime boundary changed')
    runtime=(P/'lynx-retained-ufs-trace-runtime.sh').read_bytes();init=entries['init']['data'][:-len(suffix)]+runtime+b'\nlynx_module_progress\nstop\n';put(entries,'init',init)
    reference_manifest=json.loads((P/'artifacts/busybox-refclk-trace-probe-v2/build-validation.json').read_text());require(reference_manifest['candidate_sha256']=='b4a505426c91b3a0c151b977ddcfbfddeabcca612a59959408230c19d317aea1','Traced reference changed')
    reference=reference_manifest['session_token'];put(entries,'etc/lynx/reference-ufs-token',(reference+'\n').encode(),0o100644)
    token=secrets.token_hex(16);put(entries,'etc/lynx/session-token',(token+'\n').encode(),0o100644)
    rd=pack(entries);header=bytearray(original[:1584]);struct.pack_into('<I',header,12,len(rd));align=lambda n:(n+4095)//4096*4096
    loaded=bytes(header).ljust(4096,b'\0')+boot['kernel'].ljust(align(len(boot['kernel'])),b'\0')+rd.ljust(align(len(rd)),b'\0');coverage=struct.unpack('!4sIIQQQ28x',original[-64:])[3];require(len(loaded)<=coverage,'Metadata overlap');image=loaded.ljust(coverage,b'\0')+original[coverage:]
    OUT.mkdir(mode=0o700)
    for name,raw in [('nord3-busybox-candidate.img',image),('init-source',init),('runtime-source',runtime)]:
        path=OUT/name;path.write_bytes(raw);path.chmod(0o600)
    codes={'0':'no checksum-valid reference capsule in selected bounded record'}
    require(reference_manifest['trace_events_all_ufs_specific'],'Unexpected generic event mapping')
    for index,name in reference_manifest['trace_event_symbols'].items():codes[index]='last retained reference checkpoint: '+name+('; return marker retained, retval not retrieved' if index=='8' else '; marker brackets execution, not exact stop')
    codes.update({'10':'verified trace-ready capsule; no matched trace entry retained','11':'verified pre-probe capsule; no matched trace entry retained','12':'verified probe-returned capsule; no matched trace entry retained','13':'verified reference capsule without a recognized probe phase or trace entry','14':'base prefix pending','15':'retained query pending','16':'base insertion failed','17':'reference or progress malformed','18':'worker state unavailable'})
    report=json.loads((F/'build-validation.json').read_text());report.update(candidate_sha256=sha(image),init_sha256=sha(init),ramdisk_bytes=len(rd),runtime_sha256=sha(runtime),session_token=token,reference_ufs_token=reference,reference_candidate_sha256=reference_manifest['candidate_sha256'],retained_ufs_trace_query=True,result_codes=codes,target_delays_seconds={str(i):120+5*i for i in range(19)},timing_match_tolerance_seconds=2,observation_seconds=270,phone_contacted=False,flash_eligible=False)
    (OUT/'build-validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(candidate_sha256=sha(image),ramdisk_bytes=len(rd)),indent=2))
if __name__=='__main__':main()
