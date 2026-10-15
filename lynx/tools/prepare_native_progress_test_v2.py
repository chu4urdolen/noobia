"""Give the shortened VM sample enough time for actual hex hashing/forks."""
from pathlib import Path
T=Path(__file__).resolve().parent
def main():
    out=T/'test_native_module_progress_debug_v2.py';assert not out.exists()
    source=(T/'test_native_module_progress_debug.py').read_text().replace('emulated-native-module-progress-debug-','emulated-native-module-progress-debug-v2-')
    source=source.replace("b'progress_started+5'","b'progress_started+10'").replace("b'10').replace(b'/bin/boot-proof-reboot'","b'20').replace(b'/bin/boot-proof-reboot'")
    source=source.replace('target_delay=10','target_delay=20').replace('sample shortened to5s and timer10s','sample shortened to10s and timer20s')
    out.write_text(source);print(out)
if __name__=='__main__':main()
