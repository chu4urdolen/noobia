"""Prepare independent native/control/guard checks for debug checkpoint images."""
from pathlib import Path
T=Path(__file__).resolve().parent
def save(name,text):
    path=T/name;assert not path.exists();path.write_text(text)
def main():
    control=(T/'test_module_progress_v2_control.py').read_text().replace('lynx-module-progress-v2-runtime.sh','lynx-module-progress-debug-runtime.sh').replace('module-progress-v2-control-','module-progress-debug-control-')
    control=control.replace('BB=\'{fake}\'\\n',"BB='{fake}'\\nlynx_diag_init() {{ return 1; }}\\n")
    save('test_module_progress_debug_control.py',control)
    native=(T/'test_native_module_progress.py').read_text().replace('import gzip,','import argparse,gzip,')
    native=native.replace('def main():\n',"def main():\n    parser=argparse.ArgumentParser();parser.add_argument('--count',type=int,choices=[0,28],required=True);args=parser.parse_args()\n",1)
    native=native.replace("F=P/'artifacts/busybox-module-progress-v1'", "F=P/'artifacts'/('busybox-module-progress-debug-'+str(args.count)+'-v1')")
    native=native.replace("'e2188b1083df15c5e5258e4b922af109d9f6787909d8d508b612d2f6490dcf7a'", "{0:'465fa84fd647dc04298565db906bcbad3794166d247900bd2246d24702a521d2',28:'9b5e9ff94c5c441e945ebc3bf714b253d2f8bcfbfcc91182b8d9baf54aeab0e4'}[args.count]")
    native=native.replace('lynx-module-progress-runtime.sh','lynx-module-progress-debug-runtime.sh').replace('emulated-native-module-progress-','emulated-native-module-progress-debug-'+"'+str(args.count)+'-")
    # Above replacement crosses a quoted prefix deliberately; verify compilation.
    native=native.replace("log() { printf '%s\\\\n' \"$*\"; }\n", "log() { printf '%s\\\\n' \"$*\"; }\n. /etc/lynx/diag-stage.sh\n")
    native=native.replace("printf 'NATIVE_PROGRESS_SUCCESS_EXIT=%s\\\\n' \"$?\"\n", "printf 'NATIVE_PROGRESS_SUCCESS_EXIT=%s\\\\n' \"$?\"\necho NATIVE_SUCCESS_HEX_BEGIN\n$BB cat /run/lynx/stages-bootstrap.hex\necho NATIVE_SUCCESS_HEX_END\n")
    native=native.replace("printf 'NATIVE_PROGRESS_FAILURE_EXIT=%s\\\\n' \"$?\"\n", "printf 'NATIVE_PROGRESS_FAILURE_EXIT=%s\\\\n' \"$?\"\necho NATIVE_FAILURE_HEX_BEGIN\n$BB cat /run/lynx/stages-bootstrap.hex\necho NATIVE_FAILURE_HEX_END\n")
    native=native.replace('panic=0\']','panic=0 initcall_debug\']')
    native=native.replace('code=113 target_delay=10','code=0 target_delay=10')
    native=native.replace("b'MODULE_PROGRESS_FIELD code=108 target_delay=10' in raw", "(('MODULE_PROGRESS_FIELD code='+('108' if args.count else '0')+' target_delay=10').encode() in raw)")
    marker="    report={'passed':";assert native.count(marker)==1
    extra='''    from lynx_decode_stages import decode
    hex_receipts={};token=entries['etc/lynx/session-token']['data'].decode().strip()
    for name in ['SUCCESS','FAILURE']:
        begin=('NATIVE_'+name+'_HEX_BEGIN\\r\\n').encode();end=('NATIVE_'+name+'_HEX_END').encode()
        capture=raw.split(begin)[-1].split(end)[0] if begin in raw else b''
        decoded=decode(capture,token);hex_receipts[name]=decoded
        (out/(name.lower()+'.hex')).write_bytes(capture)
        checks['native_hex_'+name]=decoded['complete_sequences_and_checksums'] and all(record['stage_hex']=='0x0200' for record in decoded['records'])
'''
    native=native.replace(marker,extra+marker,1).replace("'source_sha256':hashlib", "'prefix_count':args.count,'hex_receipts':hex_receipts,'source_sha256':hashlib",1)
    compile(native,'native-debug-test','exec');save('test_native_module_progress_debug.py',native)
    guard=(T/'test_wifi_v5_image_vm.py').read_text().replace("    parser.add_argument('--wifi-candidate'", "    parser.add_argument('--count',type=int,choices=[0,28],required=True)\n    parser.add_argument('--wifi-candidate'",1)
    guard=guard.replace("prefix='emulated-wifi-v5-image-'", "prefix='emulated-module-progress-debug-guard-'+str(args.count)+'-'")
    guard=guard.replace("ROOT/'linux-port/artifacts/busybox-wifi-ssh-twostage-v5/nord3-busybox-candidate.img'", "ROOT/'linux-port/artifacts'/('busybox-module-progress-debug-'+str(args.count)+'-v1')/'nord3-busybox-candidate.img'")
    compile(guard,'guard-debug-test','exec');save('test_module_progress_debug_guard.py',guard)
    print('Debug tests prepared; no handset contacted.')
if __name__=='__main__':main()
