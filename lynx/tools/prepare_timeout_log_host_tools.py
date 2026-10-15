"""Pin timeout diagnostic guard, validation and scoped trial tools."""
import hashlib,json
from pathlib import Path
T=Path(__file__).resolve().parent;ROOT=T.parent;P=ROOT/'linux-port'
OLD='8856714bafaabc6869ab58fa46194babcd055afd22b88ba93d3d0bf02901afaa'
NEW='b5d0ac87efdf209e849f43c842e0e06e3e4690d0dd3fc0a02f19b4ade7562d98'
def save(name,source):
    path=T/name;assert not path.exists();path.write_text(source)

def main():
    vm=(T/'test_platform_errno_image_vm.py').read_text().replace('busybox-platform-errno-v1','busybox-timeout-log-v2').replace('emulated-platform-errno-image-','emulated-timeout-log-image-')
    save('test_timeout_log_image_vm.py',vm)
    validator=(T/'validate_platform_errno_image.py').read_text().replace('busybox-platform-errno-v1','busybox-timeout-log-v2').replace(OLD,NEW)
    validator=validator.replace("{'etc/lynx/classify-driver-trace.awk'}","{'etc/lynx/classify-driver-trace.awk','etc/lynx/classify-timeout-logs.awk'}")
    validator=validator.replace("['init','etc/lynx/session-token','etc/lynx/classify-driver-trace.awk']","['init','etc/lynx/session-token','etc/lynx/classify-driver-trace.awk','etc/lynx/classify-timeout-logs.awk']")
    validator=validator.replace('platform-errno-control-','timeout-log-control-').replace('lynx-platform-errno-runtime.sh','lynx-timeout-log-runtime.sh').replace('emulated-platform-errno-image-','emulated-timeout-log-image-').replace('platform-errno-image-validation.json','timeout-log-image-validation.json')
    marker="    out = P/'docs/timeout-log-image-validation.json'"
    extra='''    log_source=(P/'lynx-classify-timeout-logs.awk').read_bytes()
    require(entries['etc/lynx/classify-timeout-logs.awk']['data']==log_source,'Log classifier image/source differs')
    log_vms=sorted((P/'artifacts').glob('emulated-native-timeout-logs-cortex-a710-*/result.json'));require(log_vms,'Native log parser VM missing')
    l=json.loads(log_vms[-1].read_text());require(l['passed'] and l['vm_only_synthetic_kmsg'] and l['log_classifier_sha256']==hashlib.sha256(log_source).hexdigest(),'Native log tests source mismatch')
    require(l['checks']['vm_synthetic_kmsg_roundtrip'],'Native dmesg roundtrip missing')
    decoder_tests=sorted((ROOT/'tools/test-artifacts').glob('timeout-log-timing-*/result.json'));require(decoder_tests,'Mask decoder test missing')
    dt=json.loads(decoder_tests[-1].read_text());require(dt['passed'] and dt['decoder_sha256']==hashlib.sha256((ROOT/'tools/lynx_timeout_log_timing.py').read_bytes()).hexdigest(),'Mask decoder changed')
    audit=json.loads((P/'docs/timeout-message-audit.json').read_text());require(audit['passed'] and audit['kernel_sha256']==hashlib.sha256(boot['kernel']).hexdigest(),'Exact stock message audit missing')
'''
    assert validator.count(marker)==1;validator=validator.replace(marker,extra+marker,1)
    save('validate_timeout_log_image.py',validator)
    trial=(T/'lynx_boot_a_platform_errno_trial.py').read_text().replace('busybox-platform-errno-v1','busybox-timeout-log-v2').replace(OLD,NEW)
    trial=trial.replace('validate_platform_errno_image.py','validate_timeout_log_image.py').replace('boot-a-platform-errno-trial-','boot-a-timeout-log-trial-')
    trial=trial.replace('from lynx_errno_timing import decode_errno_timing','from lynx_timeout_log_timing import decode_timeout_log_timing').replace('decode_errno_timing(', 'decode_timeout_log_timing(')
    save('lynx_boot_a_timeout_log_trial.py',trial)
    print('Prepared pinned timeout-context tools; no phone contacted.')

if __name__=='__main__':main()
