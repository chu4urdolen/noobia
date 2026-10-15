"""Prepare one batched timing run with prioritized WPA diagnostic slots."""
import ast,json
from pathlib import Path
R=Path(__file__).resolve().parent.parent;T=R/'tools';P=R/'linux-port';old='e24e21797997312ec21bae8f07256a3cf17411462ac6c30518543fbb2677dcab';new=json.loads((P/'artifacts/busybox-wifi-ssh-twostage-v18/build-validation.json').read_text())['candidate_sha256']
def update(s):return s.replace(old,new).replace('busybox-wifi-ssh-twostage-v17','busybox-wifi-ssh-twostage-v18').replace('wifi-v17-','wifi-v18-').replace('validate_wifi_v17_image','validate_wifi_v18_image')
def save(name,s):
    f=T/name;assert not f.exists(),f;compile(s,str(f),'exec');f.write_text(s)
for name in ['lynx_wifi_v17_contact.py','test_wifi_v17_image_vm.py']:save(name.replace('v17','v18'),update((T/name).read_text()))
save('lynx_boot_a_wifi_v18_trial.py',update((T/'lynx_boot_a_wifi_v17_trial.py').read_text()).replace('lynx_payload_fast_timing','lynx_wpa_timing'))
save('run_wifi_v18_trial.py',(T/'run_wifi_v17_trial.py').read_text().replace('v17','v18'))
s=(T/'lynx_payload_fast_timing.py').read_text().replace('{str(n):525 if n==9 else 80+5*n for n in range(50)}','{str(n):525 if n==9 else 160+5*(n-50) if n>=50 else 210+5*(n-40) if n>=40 else 260+5*(n-25) if n>=25 else 335+5*n for n in range(60)}').replace('range(50)','range(60)');save('lynx_wpa_timing.py',s)
s=update((T/'test_native_payload_fast_timing.py').read_text()).replace('emulated-payload-fast-timing-native-','emulated-wpa-timing-native-').replace('range(50)','range(60)').replace('if i not in [9,35]','if i not in [9,13,35]').replace("checks['49_resets']","checks['58_resets']").replace('==49\n','==58\n').replace('target={80+5*code}',"target={grid[str(code)]}")
anchor="source=entries['bin/boot-proof-reboot']['data']";assert s.count(anchor)==1;s=s.replace(anchor,anchor+"\n    grid=json.loads((F/'build-validation.json').read_text())['target_delays_seconds']")
tree=ast.parse(s);node=next(n for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='init' for t in n.targets));head=ast.literal_eval(node.value.left.left);tail=ast.literal_eval(node.value.right)
tail=tail.replace(b'seq 0 49',b'seq 0 59').replace(b'9|35)',b'9|13|35)').replace(b'95.00 0',b'349.00 0')
anchor=b'''    printf '%s\\n' "$((10+80+5*code))" > /fixture/target
'''
mapping=b'''    if [ "$code" -ge 50 ]; then delay=$((160+5*(code-50)))
    elif [ "$code" -ge 40 ]; then delay=$((210+5*(code-40)))
    elif [ "$code" -ge 25 ]; then delay=$((260+5*(code-25)))
    else delay=$((335+5*code)); fi
    printf '%s\\n' "$((10+delay))" > /fixture/target
''';assert tail.count(anchor)==1;tail=tail.replace(anchor,mapping)
anchor=b'    echo "NATIVE_TIMING_CASE=$code"\n';extra=b'''    if [ "$code" -ge 50 ]; then
        printf '0\\n' > /run/lynx/bootstrap-result
        printf '143\\n' > /run/lynx/worker-result
        printf '%s\\n' "$code" > /run/lynx/wpa-failure-code
    fi
''';assert tail.count(anchor)==1;tail=tail.replace(anchor,extra+anchor)
start=s.index('    init=');end=s.index("    put(entries,'init',init)",start);s=s[:start]+'    init='+repr(head)+'+fixture+'+repr(tail)+'\n'+s[end:];save('test_native_wpa_timing.py',s)
s=(T/'test_native_vendor_wifi_v16_loop.py').read_text().replace('73311e9613a002a5bf3d3d4c4b5057840b7a427a06e1aff18a186e27e68614f6',new).replace('busybox-wifi-ssh-twostage-v16','busybox-wifi-ssh-twostage-v18').replace('wifi-v16-','wifi-v18-').replace("original.index(b'lynx_read_own_boot_payload() {')","original.index(b'lynx_payload_step() {')");save('test_native_vendor_wifi_v18_loop.py',s)
print('V18 synchronized tools and batched WPA timing checks prepared.')
