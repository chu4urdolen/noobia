"""Create independent, fixed-hash checks and undo for platform-chain trial."""
from pathlib import Path

T=Path(__file__).resolve().parent
OLD='dbc47af2604563013d2e7591c81b788551938d4467aeedad131370c4ae4eb94f'
NEW='aff51e9e74094d95fa0e2addbf3671326869a07eda2104f09b28821f8b07f56f'


def save(name,source):
    path=T/name;assert not path.exists(),'Preserve previous tools';path.write_text(source)


def main():
    vm=(T/'test_core_probe_image_vm.py').read_text().replace('busybox-core-probe-v1','busybox-platform-probe-v1').replace('emulated-core-probe-image-','emulated-platform-probe-image-')
    save('test_platform_probe_image_vm.py',vm)
    validator=(T/'validate_core_probe_image.py').read_text().replace('busybox-core-probe-v1','busybox-platform-probe-v1').replace(OLD,NEW)
    validator=validator.replace('core-probe-control-','platform-probe-control-').replace('emulated-core-probe-image-','emulated-platform-probe-image-').replace('core-probe-image-validation.json','platform-probe-image-validation.json')
    validator=validator.replace('lynx-classify-core-trace.awk','lynx-classify-platform-trace.awk').replace('core-trace-classifier-','platform-trace-classifier-')
    validator=validator.replace("n.get('collector_core') and n.get('core_classifier')","n.get('collector_platform') and n.get('platform_v2') and n.get('platform_classifier')")
    save('validate_platform_probe_image.py',validator)
    trial=(T/'lynx_boot_a_core_probe_trial.py').read_text().replace('busybox-core-probe-v1','busybox-platform-probe-v1').replace(OLD,NEW)
    trial=trial.replace('validate_core_probe_image.py','validate_platform_probe_image.py').replace('boot-a-core-probe-trial-','boot-a-platform-probe-trial-')
    save('lynx_boot_a_platform_probe_trial.py',trial)
    print('Pinned platform diagnostic tools prepared; no phone contacted.')


if __name__=='__main__':main()
