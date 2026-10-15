"""Inspect debug-level initcall messages through dmesg, not console filtering."""
from pathlib import Path
T=Path(__file__).resolve().parent
def main():
    path=T/'test_native_initcall_debug_v2.py';assert not path.exists()
    source=(T/'test_native_initcall_debug.py').read_text().replace('emulated-native-initcall-debug-','emulated-native-initcall-debug-v2-')
    marker='echo CLOCK_VM_FINISHED\n$BB poweroff -f';assert source.count(marker)==1
    source=source.replace(marker,'echo CLOCK_INITCALL_DMESG_BEGIN\n$BB dmesg\necho CLOCK_INITCALL_DMESG_END\n'+marker,1)
    path.write_text(source);print(path)
if __name__=='__main__':main()
