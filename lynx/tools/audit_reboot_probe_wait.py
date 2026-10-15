"""Record published kernel evidence that normal reboot waits on active probes."""
import hashlib,json,subprocess
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';D=P/'docs/wifi-source-reference'
repo=P/'sources/kernel-mt6983'
revision=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
raw=subprocess.check_output(['git','-C',str(repo),'show','HEAD:kernel/reboot.c'])
(D/'kernel-reboot.c').write_bytes(raw)
core=(D/'driver-core.c').read_bytes()
checks={'restart2_calls_kernel_restart':b'kernel_restart(buffer);' in raw,
        'kernel_restart_prepares_shutdown':b'kernel_restart_prepare(cmd);' in raw,
        'restart_prepare_calls_device_shutdown':b'device_shutdown();' in raw.split(b'void kernel_restart_prepare(char *cmd)')[1].split(b'\n}')[0],
        'device_shutdown_waits_for_probes':b'wait_for_device_probe();' in core.split(b'void device_shutdown(void)')[1].split(b'\n}')[0]}
report={'passed':all(checks.values()),'checks':checks,'published_revision':revision,'reboot_source_sha256':hashlib.sha256(raw).hexdigest(),'driver_core_sha256':hashlib.sha256(core).hexdigest(),'phone_contacted':False,'limits':'Published reference, not exact stock build commit. Explains a possible blocked normal reboot during a probe hang; does not prove this occurred on Lynx. No alternative reset path implemented or executed.'}
out=P/'docs/reboot-probe-wait.json';out.write_text(json.dumps(report,indent=2)+'\n');print(out)
assert report['passed']
