"""Generate distinct pinned tools for the observational driver-trace candidate."""
from pathlib import Path

T=Path(__file__).resolve().parent
SHA='2154dbd63d2de8bab56669db2dabf5f26bb9a8a16774a968717164e8dffccfd4'
OLD='571fc62e9b6c4ba99ea3bc4c4c327fb147d405fccac073305ffd978fc101c7b0'


def save(name,source):
    path=T/name;assert not path.exists();path.write_text(source)


def main():
    vm=(T/'test_binding_profile_image_vm.py').read_text().replace('busybox-binding-profile-v1','busybox-probe-trace-v1').replace('emulated-binding-profile-image-','emulated-probe-trace-image-')
    save('test_probe_trace_image_vm.py',vm)
    control=(T/'test_storage_outcome_control.py').read_text()
    control=control.replace("SOURCE = ROOT / 'linux-port/lynx-storage-outcome-runtime.sh'", "SOURCE = ROOT / 'linux-port/artifacts/busybox-probe-trace-v1/trace-runtime.sh'").replace('storage-outcome-control-','probe-trace-control-')
    control=control.replace("elif a[0]=='readlink':print(os.readlink(a[1]))", "elif a[0]=='readlink':print(os.readlink(a[1]))\nelif a[0]=='awk':print(os.environ['PROBE_CODE']+' 1 -517 0 unknown 0 0 0')")
    start=control.index('    specifications = ');end=control.index('    for name, status, code in specifications:',start)
    control=control[:start]+"    specifications=[('result-'+str(n),153,n) for n in range(1,8)]+[('capture-failure',153,8),('stalled',None,8),('bad-clock',0,None)]\n"+control[end:]
    needle="+ source + '\\nlynx_storage_probe\\n')";assert control.count(needle)==1
    replacement="+ source + f'\\nlynx_driver_trace_setup() {{ return {1 if code==1 else 0}; }}\\nlynx_driver_trace_capture() {{ return {1 if name==\"capture-failure\" else 0}; }}\\nlynx_storage_probe\\n')"
    control=control.replace(needle,replacement)
    control=control.replace('FIXTURE=str(folder)),capture_output',"FIXTURE=str(folder),PROBE_CODE=str(code if code else 8)),capture_output")
    save('test_probe_trace_control.py',control)
    validator=(T/'validate_binding_profile_image.py').read_text().replace('busybox-binding-profile-v1','busybox-probe-trace-v1').replace(OLD,SHA).replace('emulated-binding-profile-image-','emulated-probe-trace-image-').replace('binding-profile-image-validation.json','probe-trace-image-validation.json').replace('binding-profile-control-','probe-trace-control-').replace("F/'profile-runtime.sh'","F/'trace-runtime.sh'")
    before="    require(set(entries) == set(original), 'Unexpected first-stage files')";assert validator.count(before)==1
    validator=validator.replace(before,"    require(set(entries)-set(original)=={'etc/lynx/classify-driver-trace.awk'},'Unexpected first-stage files')\n    require(entries['etc/lynx/classify-driver-trace.awk']['data']==(P/'lynx-classify-driver-trace.awk').read_bytes(),'Classifier source changed')")
    validator=validator.replace("if name not in ['init','etc/lynx/session-token']:","if name not in ['init','etc/lynx/session-token','etc/lynx/classify-driver-trace.awk']:")
    start=validator.index("    native=sorted((P/'artifacts').glob('emulated-native-binding-profile-")
    end=validator.index("    out = P/'docs/probe-trace-image-validation.json'",start)
    block="""    require((P/'lynx-driver-trace.sh').read_bytes() in source,'Observational trace source missing')
    native=sorted((P/'artifacts').glob('emulated-native-driver-trace-cortex-a710-*/result.json'));require(native,'Concrete modern ARM trace test missing')
    n=json.loads(native[-1].read_text());require(n['passed'] and not n.get('baseline_only') and n['source_sha256']==hashlib.sha256((P/'lynx-driver-trace.sh').read_bytes()).hexdigest() and n['classifier_sha256']==hashlib.sha256((P/'lynx-classify-driver-trace.awk').read_bytes()).hexdigest(),'Native tested trace/classifier mismatch')
    fixtures=sorted((ROOT/'tools/test-artifacts').glob('driver-trace-classifier-*/result.json'));require(fixtures,'Parser semantic fixtures missing')
    f=json.loads(fixtures[-1].read_text());require(f['passed'] and f['source_sha256']==hashlib.sha256((P/'lynx-classify-driver-trace.awk').read_bytes()).hexdigest(),'Parser semantic tested source mismatch')
"""
    validator=validator[:start]+block+validator[end:]
    save('validate_probe_trace_image.py',validator)
    trial=(T/'lynx_boot_a_binding_profile_trial.py').read_text().replace('busybox-binding-profile-v1','busybox-probe-trace-v1').replace(OLD,SHA).replace('validate_binding_profile_image.py','validate_probe_trace_image.py').replace('boot-a-binding-profile-trial-','boot-a-probe-trace-trial-')
    save('lynx_boot_a_probe_trace_trial.py',trial)
    print('Prepared independent native/semantic/control/layout validation and bounded trace trial tools; no phone contacted.')


if __name__=='__main__':main()
