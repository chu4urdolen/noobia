"""Preserve prior checks; pin tests and host runner to the payload-step image."""
from pathlib import Path
R=Path(__file__).resolve().parent.parent;T=R/'tools'
OLD='a9c233c6aefbae80e2e9cd1fabbb1dcda8cdac3119d9ea58bc5e95b73c96802a';NEW='9df9229dba14a1b29e17a5bcdb8c34fb813682998a63ff57718ed1bb7f6f9226'
def common(s):
    return s.replace(OLD,NEW).replace('busybox-bootstrap-timing-v1','busybox-payload-timing-v1').replace('lynx-bootstrap-timing-runtime.sh','lynx-payload-timing-runtime.sh').replace('emulated-bootstrap-timing-','emulated-payload-timing-')
def save(name,s):
    p=T/name;assert not p.exists(),p;compile(s,str(p),'exec');p.write_text(s)
def main():
    s=common((T/'test_bootstrap_timing_runtime.py').read_text())
    s=s.replace('for status in 0 151 152 153 154 99 missing malformed; do','for status in 0 p1 p2 p3 p4 p5 p6 p7 missing malformed; do')
    parameter=chr(36)+'{status#p}'
    s=s.replace('    if [ "$status" = missing ]; then','    if [ "$status" != "'+parameter+'" ]; then\n        printf \'154\\\\n\' > /run/lynx/bootstrap-result\n        printf \'%s\\\\n\' "'+parameter+'" > /run/lynx/payload-progress\n    elif [ "$status" = missing ]; then')
    s=s.replace("for code,status in enumerate(['0','151','152','153','154','99','missing','malformed']):","for status,code in [('0',0),('p1',1),('p2',2),('p3',3),('p4',4),('p5',5),('p6',6),('p7',7),('missing',8),('malformed',8)]:")
    s=s.replace("checks['eight_resets']","checks['ten_resets']").replace("==8\n","==10\n")
    save('test_payload_timing_runtime.py',s)
    save('test_payload_timing_guard.py',common((T/'test_bootstrap_timing_guard.py').read_text()))
    s=(T/'test_native_payload_loop.py').read_text().replace('9a17b8e72e8e8fe8928f551fcf593cee1d19a712affe498f23f637e7ac4da00c',NEW).replace('busybox-wifi-ssh-twostage-v7','busybox-payload-timing-v1').replace('emulated-native-payload-loop-','emulated-native-payload-step-loop-')
    save('test_native_payload_step_loop.py',s)
    save('lynx_payload_timing.py',(T/'lynx_bootstrap_timing.py').read_text().replace('range(8)','range(9)'))
    s=common((T/'lynx_boot_a_bootstrap_timing_v2_trial.py').read_text()).replace('lynx_bootstrap_timing','lynx_payload_timing').replace('validate_bootstrap_timing_image','validate_payload_timing_image').replace('boot-a-bootstrap-timing-v2-trial-','boot-a-payload-timing-trial-')
    save('lynx_boot_a_payload_timing_trial.py',s)
    print('Pinned native/loop/guard/decoder/trial prepared.')
if __name__=='__main__':main()
