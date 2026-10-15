"""Extend the native capability run with isolated synthetic firmware sysfs."""
import ast
from pathlib import Path
T=Path(__file__).resolve().parent
s=(T/'test_native_mdev_daemon.py').read_text();tree=ast.parse(s);node=next(n for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='init' for t in n.targets));init=ast.literal_eval(node.value)
extra=b'''$BB mount -t tmpfs tmpfs /sys
$BB mkdir -p /sys/known /sys/unknown /lib/firmware
printf 'LYNX_NATIVE_FIRMWARE_TEST' > /lib/firmware/lynx-native-test.bin
: > /sys/known/loading
: > /sys/known/data
: > /sys/unknown/loading
: > /sys/unknown/data
ACTION=add SUBSYSTEM=firmware DEVPATH=/known FIRMWARE=lynx-native-test.bin $BB mdev
if $BB cmp -s /lib/firmware/lynx-native-test.bin /sys/known/data; then echo NATIVE_MDEV_FIRMWARE_BYTES_CONFIRMED; fi
known=$($BB cat /sys/known/loading)
echo "NATIVE_MDEV_KNOWN_LOADING=$known"
ACTION=add SUBSYSTEM=firmware DEVPATH=/unknown FIRMWARE=lynx-absent-native-test.bin $BB mdev
unknown=$($BB cat /sys/unknown/loading)
echo "NATIVE_MDEV_UNKNOWN_LOADING=$unknown"
'''
assert init.count(b'$BB poweroff -f\n')==1;init=init.replace(b'$BB poweroff -f\n',extra+b'$BB poweroff -f\n');old=ast.get_source_segment(s,node.value);assert s.count(old)==1;s=s.replace(old,repr(init)).replace('emulated-native-mdev-daemon-','emulated-native-mdev-firmware-')
anchor="report={'passed':";assert s.count(anchor)==1
s=s.replace(anchor,"checks.update(firmware_bytes=b'NATIVE_MDEV_FIRMWARE_BYTES_CONFIRMED' in console, known_loading_protocol=b'NATIVE_MDEV_KNOWN_LOADING=10' in console, unknown_explicit_abort=b'NATIVE_MDEV_UNKNOWN_LOADING=-1' in console)\n"+anchor)
s=s.replace('Actual stock ARM kernel/BusyBox daemon, no simulated firmware request or physical Wi-Fi. Literal presence alone does not prove all firmware-loader paths.','Actual stock ARM kernel/BusyBox daemon and hotplug firmware helper; synthetic sysfs control/data files test payload bytes and loading protocol. No real firmware kernel request or physical Wi-Fi.')
out=T/'test_native_mdev_firmware.py';assert not out.exists();compile(s,str(out),'exec');out.write_text(s);print(out)
