"""Native module-loading test with the actual stock AEE prerequisites."""
from pathlib import Path
T=Path(__file__).resolve().parent
def main():
    target=T/'test_native_power_clocks_v2.py';assert not target.exists()
    native=(T/'test_native_power_clocks.py').read_text()
    native=native.replace("clock_names=['clk-common.ko']", "clock_names=['mrdump.ko','aee_aed.ko','clk-common.ko']")
    native=native.replace('emulated-native-power-clocks-','emulated-native-power-clocks-v2-')
    marker="    init=init.replace(b'echo TRACE_VM_INIT_ENTERED\\n',b'echo TRACE_VM_INIT_ENTERED\\n'+commands,1)"
    assert native.count(marker)==1
    native=native.replace(marker,"    init=b'''#!/bin/sh\nBB=/bin/busybox\nexport PATH=/bin:/sbin\n$BB mount -t proc proc /proc\n$BB mount -t sysfs sysfs /sys\n$BB mount -t tmpfs tmpfs /dev\n$BB mount -t tmpfs tmpfs /run\n$BB mknod -m 600 /dev/console c 5 1\n$BB mknod -m 666 /dev/null c 1 3\nexec > /dev/console 2>&1\necho CLOCK_VM_INIT_ENTERED\n'''+commands+b'''\necho CLOCK_VM_FINISHED\n$BB poweroff -f\n'''",1)
    marker="    for name in clock_names:\n        checks['clock_load_'+name]="
    assert native.count(marker)==1
    native=native.replace(marker,"    checks={'init_entered':b'CLOCK_VM_INIT_ENTERED' in raw,'finished':b'CLOCK_VM_FINISHED' in raw,'clean_poweroff':b'reboot: Power down' in raw,'no_kernel_exception':not any(m in raw for m in [b'Kernel panic',b'Internal error:',b'CFI failure'])}\n"+marker,1)
    target.write_text(native);print(target)
if __name__=='__main__':main()
