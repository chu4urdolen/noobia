"""Create pinned, independent tools for the core checks diagnostic."""
from pathlib import Path

T=Path(__file__).resolve().parent
OLD='b8114a11af588a9f40df0ab125895388a567879a913a973186aacc764b2185b4'
NEW='dbc47af2604563013d2e7591c81b788551938d4467aeedad131370c4ae4eb94f'


def save(name,source):
    path=T/name; assert not path.exists(),'Preserve prior tools'; path.write_text(source)


def main():
    vm=(T/'test_probe_trace_v3_image_vm.py').read_text().replace('busybox-probe-trace-v3','busybox-core-probe-v1').replace('emulated-probe-trace-v3-image-','emulated-core-probe-image-')
    save('test_core_probe_image_vm.py',vm)
    validator=(T/'validate_probe_trace_v3_image.py').read_text().replace('busybox-probe-trace-v3','busybox-core-probe-v1').replace(OLD,NEW)
    validator=validator.replace('probe-trace-v3-control-','core-probe-control-').replace('emulated-probe-trace-v3-image-','emulated-core-probe-image-')
    validator=validator.replace('probe-trace-v3-image-validation.json','core-probe-image-validation.json').replace('lynx-classify-driver-trace-v3.awk','lynx-classify-core-trace.awk')
    validator=validator.replace('driver-trace-v3-classifier-','core-trace-classifier-')
    validator=validator.replace("n.get('collector_v3')","n.get('collector_core') and n.get('core_classifier')")
    save('validate_core_probe_image.py',validator)
    trial=(T/'lynx_boot_a_probe_trace_v3_trial.py').read_text().replace('busybox-probe-trace-v3','busybox-core-probe-v1').replace(OLD,NEW)
    trial=trial.replace('validate_probe_trace_v3_image.py','validate_core_probe_image.py').replace('boot-a-probe-trace-v3-trial-','boot-a-core-probe-trial-')
    save('lynx_boot_a_core_probe_trial.py',trial)
    print('Core diagnostic host tools ready; no phone contacted.')


if __name__=='__main__':main()
