"""Preserve predecessors while generating pinned profile validation/trial tools."""
from pathlib import Path

T=Path(__file__).resolve().parent
SHA='571fc62e9b6c4ba99ea3bc4c4c327fb147d405fccac073305ffd978fc101c7b0'
OLD='5f85ae811386ccec50c1eab94649f587621035ca053126788d9627ee666bea25'


def save(name,source):
    target=T/name;assert not target.exists();target.write_text(source)


def main():
    vm=(T/'test_storage_permissive_image_vm.py').read_text().replace('busybox-storage-outcome-v2','busybox-binding-profile-v1').replace('emulated-storage-outcome-permissive-','emulated-binding-profile-image-')
    save('test_binding_profile_image_vm.py',vm)
    control=(T/'test_storage_outcome_control.py').read_text()
    control=control.replace("SOURCE = ROOT / 'linux-port/lynx-storage-outcome-runtime.sh'", "SOURCE = ROOT / 'linux-port/artifacts/busybox-binding-profile-v1/profile-runtime.sh'").replace('storage-outcome-control-','binding-profile-control-')
    start=control.index('    specifications = ');end=control.index('    for name, status, code in specifications:',start)
    control=control[:start]+"    specifications = [('profile-'+str(n),153,n) for n in range(1,8)] + [('stalled',None,8),('other',255,8),('bad-clock',0,None)]\n"+control[end:]
    needle="+ source + '\\nlynx_storage_probe\\n')"
    assert control.count(needle)==1
    control=control.replace(needle,"+ source + f'\\nlynx_binding_profile() {{ return {code if code is not None else 1}; }}\\nlynx_storage_probe\\n')")
    save('test_binding_profile_control.py',control)
    validator=(T/'validate_storage_permissive_image.py').read_text().replace('busybox-storage-outcome-v2','busybox-binding-profile-v1').replace(OLD,SHA).replace('emulated-storage-outcome-permissive-','emulated-binding-profile-image-').replace('storage-permissive-image-validation.json','binding-profile-image-validation.json').replace('storage-outcome-control-','binding-profile-control-')
    needle="source = (P/'lynx-storage-outcome-runtime.sh').read_bytes()"
    assert validator.count(needle)==1
    validator=validator.replace(needle,"source = (F/'profile-runtime.sh').read_bytes()")
    marker="    out = P/'docs/binding-profile-image-validation.json'"
    assert validator.count(marker)==1
    validator=validator.replace(marker,"""    native=sorted((P/'artifacts').glob('emulated-native-binding-profile-*/result.json'));require(native,'Native profile test missing')
    n=json.loads(native[-1].read_text());require(n['passed'] and n['candidate_sha256']==SHA and n['profile_source_sha256']==hashlib.sha256((P/'lynx-binding-profile.sh').read_bytes()).hexdigest(),'Native profile tested source changed')
    require((P/'lynx-binding-profile.sh').read_bytes() in source,'Read-only profile source missing')
"""+marker)
    save('validate_binding_profile_image.py',validator)
    trial=(T/'lynx_boot_a_storage_permissive_trial.py').read_text().replace('busybox-storage-outcome-v2','busybox-binding-profile-v1').replace(OLD,SHA).replace('validate_storage_permissive_image.py','validate_binding_profile_image.py').replace('boot-a-storage-permissive-trial-','boot-a-binding-profile-trial-')
    save('lynx_boot_a_binding_profile_trial.py',trial)
    print('Prepared separate profile control, image-guard, validation and trial tools; no phone contacted.')


if __name__=='__main__':main()
