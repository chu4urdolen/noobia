"""Create independent image guard, validation and trial tools for v3."""
from pathlib import Path

T = Path(__file__).resolve().parent
OLD = '2154dbd63d2de8bab56669db2dabf5f26bb9a8a16774a968717164e8dffccfd4'
NEW = 'b8114a11af588a9f40df0ab125895388a567879a913a973186aacc764b2185b4'


def save(name, source):
    path = T / name
    assert not path.exists(), 'Preserve existing tools'
    path.write_text(source)


def main():
    vm = (T / 'test_probe_trace_image_vm.py').read_text().replace('busybox-probe-trace-v1', 'busybox-probe-trace-v3').replace('emulated-probe-trace-image-', 'emulated-probe-trace-v3-image-')
    save('test_probe_trace_v3_image_vm.py', vm)
    validator = (T / 'validate_probe_trace_image.py').read_text().replace('busybox-probe-trace-v1', 'busybox-probe-trace-v3').replace(OLD, NEW)
    validator = validator.replace('probe-trace-control-', 'probe-trace-v3-control-').replace('emulated-probe-trace-image-', 'emulated-probe-trace-v3-image-').replace('probe-trace-image-validation.json', 'probe-trace-v3-image-validation.json')
    validator = validator.replace("P/'lynx-classify-driver-trace.awk'", "P/'lynx-classify-driver-trace-v3.awk'")
    validator = validator.replace("P/'lynx-driver-trace.sh'", "F/'collector-source.sh'")
    validator = validator.replace('driver-trace-classifier-', 'driver-trace-v3-classifier-')
    validator = validator.replace("n['passed'] and not n.get('baseline_only')", "n['passed'] and n.get('collector_v3') and n.get('deferred_reset_probe') and n.get('module_loading_under_trace') and not n.get('baseline_only')")
    save('validate_probe_trace_v3_image.py', validator)
    trial = (T / 'lynx_boot_a_probe_trace_trial.py').read_text().replace('busybox-probe-trace-v1', 'busybox-probe-trace-v3').replace(OLD, NEW)
    trial = trial.replace('validate_probe_trace_image.py', 'validate_probe_trace_v3_image.py').replace('boot-a-probe-trace-trial-', 'boot-a-probe-trace-v3-trial-')
    save('lynx_boot_a_probe_trace_v3_trial.py', trial)
    print('v3 host tools created; no phone contacted.')


if __name__ == '__main__':
    main()
