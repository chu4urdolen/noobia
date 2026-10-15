"""Prepare batched payload fault injection and expanded fast timing checks."""
import ast,json
from pathlib import Path
R=Path(__file__).resolve().parent.parent;T=R/'tools';P=R/'linux-port';old='73311e9613a002a5bf3d3d4c4b5057840b7a427a06e1aff18a186e27e68614f6';new=json.loads((P/'artifacts/busybox-wifi-ssh-twostage-v17/build-validation.json').read_text())['candidate_sha256']
def update(s):return s.replace(old,new).replace('busybox-wifi-ssh-twostage-v16','busybox-wifi-ssh-twostage-v17').replace('wifi-v16-','wifi-v17-').replace('validate_wifi_v16_image','validate_wifi_v17_image')
def save(name,s):
    f=T/name;assert not f.exists(),f;compile(s,str(f),'exec');f.write_text(s)
for name in ['lynx_wifi_v16_contact.py','test_wifi_v16_image_vm.py']:save(name.replace('v16','v17'),update((T/name).read_text()))
s=update((T/'lynx_boot_a_wifi_v16_trial.py').read_text()).replace('lynx_fast_wifi_timing','lynx_payload_fast_timing');save('lynx_boot_a_wifi_v17_trial.py',s)
save('run_wifi_v17_trial.py',(T/'run_wifi_v16_trial.py').read_text().replace('v16','v17'))
save('lynx_payload_fast_timing.py',(T/'lynx_fast_wifi_timing.py').read_text().replace('120+5*n','80+5*n').replace('range(40)','range(50)'))
s=(T/'test_native_fast_wifi_timing.py').read_text().replace('c08d19beb54ef6400912651539d6ce9f510632a94d04180f30b88114d48768f2',new).replace('busybox-wifi-ssh-twostage-v15','busybox-wifi-ssh-twostage-v17').replace('emulated-fast-wifi-timing-native-','emulated-payload-fast-timing-native-').replace('range(40)','range(50)').replace('target={120+5*code}','target={80+5*code}').replace("checks['39_resets']","checks['49_resets']").replace('==39\n','==49\n')
tree=ast.parse(s);node=next(n for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='init' for t in n.targets));head=ast.literal_eval(node.value.left.left);tail=ast.literal_eval(node.value.right)
tail=tail.replace(b'seq 0 39',b'seq 0 49').replace(b'10+120+5*code',b'10+80+5*code').replace(b'133.00 0',b'95.00 0')
needle=b'    echo "NATIVE_TIMING_CASE=$code"\n';extra=b'''    if [ "$code" -ge 40 ]; then
        printf '154\\n' > /run/lynx/bootstrap-result
        printf '%s\\n' "$((code-39))" > /run/lynx/payload-step
    fi
''';assert tail.count(needle)==1;tail=tail.replace(needle,extra+needle)
start=s.index('    init=');end=s.index("    put(entries,'init',init)",start);s=s[:start]+'    init='+repr(head)+'+fixture+'+repr(tail)+'\n'+s[end:];save('test_native_payload_fast_timing.py',s)
s=update((T/'test_native_vendor_wifi_v16_loop.py').read_text()).replace("original.index(b'lynx_read_own_boot_payload() {')","original.index(b'lynx_payload_step() {')")
tree=ast.parse(s);node=next(n for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='init' for t in n.targets));head=ast.literal_eval(node.value.left.left);tail=ast.literal_eval(node.value.right)
wrapper=b'''#!/bin/sh
case "$LYNX_PAYLOAD_FAIL:$1:$2" in
    3:blockdev:--getsize64) echo 0; exit 0 ;;
    4:blockdev:--setro|6:dd:*|7:sha256sum:*|8:gzip:*|9:cpio:*) exit 1 ;;
esac
exec /bin/busybox "$@"
'''
anchor="    init=";assert s.count(anchor)==1;s=s.replace(anchor,"    put(entries,'bin/payload-busybox',"+repr(wrapper)+")\n"+anchor)
head=head.replace(b'BB=/bin/busybox',b'BB=/bin/payload-busybox')
head=head.replace(b'log() { printf',b'log() { case "$LYNX_PAYLOAD_FAIL:$1" in 10:BOOT_A_SUPPLEMENT_VERIFIED_AND_EXTRACTED*) return 1 ;; esac; printf')
extra=b'''original_bytes=$($BB cat /etc/lynx/payload-bytes)
for phase in 1 2 3 4 5 6 7 8 9 10; do
    export LYNX_PAYLOAD_FAIL=$phase
    if [ "$phase" = 1 ]; then $BB mv /fixture/block/loop0/uevent /fixture/block/loop0/saved; fi
    if [ "$phase" = 2 ]; then $BB mv /dev/loop0 /dev/loop.saved; fi
    if [ "$phase" = 5 ]; then echo bad > /etc/lynx/payload-bytes; fi
    echo "PAYLOAD_FAULT_PHASE=$phase"
    lynx_read_own_boot_payload
    rc=$?
    read -r observed < /run/lynx/payload-step
    echo "PAYLOAD_FAULT_RESULT=$rc STEP=$observed"
    if [ "$phase" = 1 ]; then $BB mv /fixture/block/loop0/saved /fixture/block/loop0/uevent; fi
    if [ "$phase" = 2 ]; then $BB mv /dev/loop.saved /dev/loop0; fi
    printf '%s\\n' "$original_bytes" > /etc/lynx/payload-bytes
done
unset LYNX_PAYLOAD_FAIL
'''
anchor=b'$BB poweroff -f\n';assert tail.count(anchor)==1;tail=tail.replace(anchor,extra+anchor)
start=s.index('    init=');end=s.index("    put(entries,'init',init)",start);s=s[:start]+'    init='+repr(head)+'+fixture+'+repr(tail)+'\n'+s[end:]
anchor="    report={'passed':";checks="    for phase in range(1,11):\n        section=console.split(('PAYLOAD_FAULT_PHASE='+str(phase)+'\\r\\n').encode())[-1].split(b'PAYLOAD_FAULT_PHASE=')[0]\n        checks['fault_'+str(phase)]=('PAYLOAD_FAULT_RESULT=1 STEP='+str(phase)).encode() in section\n";assert s.count(anchor)==1;s=s.replace(anchor,checks+anchor);save('test_native_vendor_wifi_v17_loop.py',s)
print('V17 synchronized tools, 49 timing resets and 10 payload faults prepared.')
