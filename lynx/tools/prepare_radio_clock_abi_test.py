"""Use the exact stock kernel/vendor ramdisk to verify supplier module ABI."""
from pathlib import Path
R=Path(__file__).resolve().parent.parent;T=R/'tools'
s=(T/'test_native_vendor_wifi_v12_loop.py').read_text().replace('emulated-native-vendor-wifi-v12-loop-','emulated-radio-clock-abi-')
start=s.index('    init=');end=s.index("    put(entries,'init',init)",start)
init=b'''#!/bin/sh
export PATH=/bin:/sbin
BB=/bin/busybox
$BB mount -t proc proc /proc
$BB mount -t sysfs sysfs /sys
$BB mount -t tmpfs tmpfs /dev
$BB mknod -m 600 /dev/console c 5 1
$BB mknod -m 666 /dev/null c 1 3
exec > /dev/console 2>&1
for module in regmap-spmi mt6685-core clkbuf; do
    $BB insmod "/lib/modules/$module.ko"
    printf 'RADIO_CLOCK_ABI module=%s exit=%s\\n' "$module" "$?"
done
if [ -d /sys/module/regmap_spmi ] && [ -d /sys/module/mt6685_core ] && [ -d /sys/module/clkbuf ]; then echo RADIO_CLOCK_ABI_MODULES_PRESENT; fi
$BB poweroff -f
'''
s=s[:start]+'    init='+repr(init)+'\n'+s[end:]
start=s.index('    checks=');end=s.index('    report=',start)
s=s[:start]+"""    checks={name:('RADIO_CLOCK_ABI module='+name+' exit=0').encode() in console for name in ['regmap-spmi','mt6685-core','clkbuf']}
    checks['modules_present']=b'RADIO_CLOCK_ABI_MODULES_PRESENT' in console
    checks['clean_poweroff']=b'reboot: Power down' in console
    checks['no_exception']=not any(x in console for x in [b'Kernel panic',b'Internal error:',b'CFI failure',b'Unknown symbol'])
"""+s[end:]
s=s.replace('Stock kernel/real ARM64 BusyBox/real loop block I/O; partition metadata is fixture. Does not prove physical UFS reads.','Stock kernel/ARM64 BusyBox and actual stock supplier module initialization; virtual machine has no matching MTK peripheral nodes. Does not prove physical binding or hardware clock outputs.')
out=T/'test_native_radio_clock_abi.py';assert not out.exists();compile(s,str(out),'exec');out.write_text(s);print(out)
