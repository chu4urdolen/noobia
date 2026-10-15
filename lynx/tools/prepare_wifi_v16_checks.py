"""Prepare V16 wrappers and one batched real-kernel firmware service test."""
import ast,json
from pathlib import Path
R=Path(__file__).resolve().parent.parent;T=R/'tools';P=R/'linux-port';old='c08d19beb54ef6400912651539d6ce9f510632a94d04180f30b88114d48768f2';new=json.loads((P/'artifacts/busybox-wifi-ssh-twostage-v16/build-validation.json').read_text())['candidate_sha256']
def update(s):return s.replace(old,new).replace('busybox-wifi-ssh-twostage-v15','busybox-wifi-ssh-twostage-v16').replace('wifi-v15-','wifi-v16-').replace('validate_wifi_v15_image','validate_wifi_v16_image')
def save(name,s):
    f=T/name;assert not f.exists(),f;compile(s,str(f),'exec');f.write_text(s)
for name in ['lynx_wifi_v15_contact.py','lynx_boot_a_wifi_v15_trial.py','test_wifi_v15_image_vm.py']:save(name.replace('v15','v16'),update((T/name).read_text()))
save('run_wifi_v16_trial.py',(T/'run_wifi_v15_trial.py').read_text().replace('v15','v16'))
s=update((T/'test_native_mdev_firmware.py').read_text()).replace('emulated-native-mdev-firmware-','emulated-native-firmware-events-')
anchor='init=';start=s.index(anchor)
s=s[:start]+"extra=read_newc(gzip.decompress((P/'artifacts/busybox-wifi-ssh-twostage-v16/supplement.cpio.gz').read_bytes()));service=extra['etc/lynx/firmware-events.sh']['data'];put(e,'etc/lynx/firmware-events.sh',service,0o100644)\n"+s[start:]
tree=ast.parse(s);node=next(n for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='init' for t in n.targets));init=ast.literal_eval(node.value)
extra=b'''$BB mkdir -p /run/lynx
log() { echo "$@"; }
. /etc/lynx/firmware-events.sh
if lynx_firmware_events_start; then
    echo NATIVE_FIRMWARE_EVENT_SERVICE_READY
    $BB cat /run/lynx/firmware-events-ready
    if ! lynx_firmware_events_start; then echo NATIVE_FIRMWARE_DUPLICATE_REFUSED; fi
    kill "$firmware_events_pid"
    wait "$firmware_events_pid"
fi
$BB rm -f /run/lynx/mdev.pid
printf 'unsafe-command-fixture\\n' > /etc/mdev.conf
if ! lynx_firmware_events_start; then echo NATIVE_FIRMWARE_CONFIG_REFUSED; fi
$BB rm -f /etc/mdev.conf
'''
anchor=b'$BB mount -t tmpfs tmpfs /sys\n';assert init.count(anchor)==1;init=init.replace(anchor,extra+anchor);segment=ast.get_source_segment(s,node.value);assert s.count(segment)==1;s=s.replace(segment,repr(init))
anchor="report={'passed':";assert s.count(anchor)==1;s=s.replace(anchor,"checks.update(service_ready=b'NATIVE_FIRMWARE_EVENT_SERVICE_READY' in console, duplicate_refused=b'NATIVE_FIRMWARE_DUPLICATE_REFUSED' in console, command_config_refused=b'NATIVE_FIRMWARE_CONFIG_REFUSED' in console)\n"+anchor)
anchor="(out/'result.json').write_text";assert s.count(anchor)==1;s=s.replace(anchor,"report.update(candidate_sha256='"+new+"',service_sha256=hashlib.sha256(service).hexdigest())\n"+anchor)
save('test_native_firmware_events.py',s);print('V16 tools and batched firmware service checks prepared.')
