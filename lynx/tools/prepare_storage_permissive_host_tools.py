"""Separate pinned tools for the single-option storage comparison."""
from pathlib import Path

T=Path(__file__).resolve().parent
SHA='5f85ae811386ccec50c1eab94649f587621035ca053126788d9627ee666bea25'
OLD='85d219fd6625897638ef70ee9abd9959cbf625f0063cecf19905a70f03b5e358'


def save(name,source):
    target=T/name
    assert not target.exists(),'Preserve generated files'
    target.write_text(source)


def main():
    vm=(T/'test_storage_outcome_image_vm.py').read_text().replace('busybox-storage-outcome-v1','busybox-storage-outcome-v2').replace('emulated-storage-outcome-image-','emulated-storage-outcome-permissive-')
    before="'console=ttyAMA0 rdinit=/init loglevel=7 panic=0']"
    assert vm.count(before)==1
    vm=vm.replace(before,"'console=ttyAMA0 rdinit=/init loglevel=7 panic=0 '+boot['cmdline']]")
    save('test_storage_permissive_image_vm.py',vm)
    validate=(T/'validate_storage_outcome_image.py').read_text().replace('busybox-storage-outcome-v1','busybox-storage-outcome-v2').replace(OLD,SHA).replace('emulated-storage-outcome-image-','emulated-storage-outcome-permissive-').replace('storage-outcome-image-validation.json','storage-permissive-image-validation.json')
    before="    require(image[:12] == reference[:12] and image[16:4096] == reference[16:4096], 'Unrelated header change')"
    assert validate.count(before)==1
    validate=validate.replace(before,"""    require(image[:12]==reference[:12] and image[16:44]==reference[16:44] and image[1580:4096]==reference[1580:4096], 'Unrelated header change')
    require(boot['cmdline']==previous['cmdline']+' fw_devlink=permissive','Unexpected command line')""")
    marker="    out = P/'docs/storage-permissive-image-validation.json'"
    assert validate.count(marker)==1
    extra="""    model=ROOT/'tools/avb-host/avb-boot-model'
    model_reference=json.loads((P/'docs/avb-boot-model-results.json').read_text())
    require(hashlib.sha256(model.read_bytes()).hexdigest()==model_reference['binary_sha256'],'AVB model changed')
    for unlocked in ['1','0']:
        check=subprocess.run([str(model),str(P/'artifacts/stock-cph2493-August-eu-ota'),str(F/'nord3-busybox-candidate.img'),'0',unlocked],capture_output=True,text=True,timeout=30)
        require(check.returncode==0,'AVB model failed')
        require(json.loads(check.stdout)['slot_data_returned']==(unlocked=='1'),'Unlocked/locked policy changed')
"""
    validate=validate.replace(marker,extra+marker)
    save('validate_storage_permissive_image.py',validate)
    trial=(T/'lynx_boot_a_storage_outcome_trial.py').read_text().replace('busybox-storage-outcome-v1','busybox-storage-outcome-v2').replace(OLD,SHA).replace('validate_storage_outcome_image.py','validate_storage_permissive_image.py').replace('boot-a-storage-outcome-trial-','boot-a-storage-permissive-trial-')
    save('lynx_boot_a_storage_permissive_trial.py',trial)
    print('Prepared independent validation, exact VM and bounded trial tools; no phone contacted.')


if __name__=='__main__':main()
