"""Prepare synchronized V15 tools and batched early/late timing fixtures."""
import ast,json
from pathlib import Path
R=Path(__file__).resolve().parent.parent;T=R/'tools';P=R/'linux-port';old='5bc287a9fea447edfe83eeb284d8371ea0ac093f3a17f74e3db66bb171cedded';new=json.loads((P/'artifacts/busybox-wifi-ssh-twostage-v15/build-validation.json').read_text())['candidate_sha256']
def update(s):return s.replace(old,new).replace('busybox-wifi-ssh-twostage-v14','busybox-wifi-ssh-twostage-v15').replace('wifi-v14-','wifi-v15-').replace('validate_wifi_v14_image','validate_wifi_v15_image')
def save(name,s):
    f=T/name;assert not f.exists(),f;compile(s,str(f),'exec');f.write_text(s)
for name in ['lynx_wifi_v14_contact.py','test_wifi_v14_image_vm.py','test_native_vendor_wifi_v14_loop.py']:save(name.replace('v14','v15'),update((T/name).read_text()))
s=update((T/'lynx_boot_a_wifi_v14_trial.py').read_text()).replace('lynx_station_failure_timing','lynx_fast_wifi_timing').replace('up to 780 seconds','up to 660 seconds').replace('time.monotonic()+780','time.monotonic()+660');save('lynx_boot_a_wifi_v15_trial.py',s)
s=(T/'lynx_station_failure_timing.py').read_text().replace('{str(n):480+5*n for n in range(40)}','{str(n):525 if n==9 else 120+5*n for n in range(40)}').replace('elapsed-baseline-480-5*n','elapsed-baseline-manifest[\'target_delays_seconds\'][str(n)]');save('lynx_fast_wifi_timing.py',s)
s=(T/'run_wifi_v14_trial.py').read_text().replace('v14','v15').replace("'780'","'660'");save('run_wifi_v15_trial.py',s)
s=update((T/'test_native_stack_failure_timing.py').read_text()).replace('emulated-stack-failure-timing-native-','emulated-fast-wifi-timing-native-')
tree=ast.parse(s);node=next(n for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='init' for t in n.targets));head=ast.literal_eval(node.value.left.left);tail=ast.literal_eval(node.value.right)
tail=tail.replace(b'430.00 0',b'30.00 0').replace(b'10+480+5*code',b'10+120+5*code')
anchor=b"printf 'bad\\n' > /run/lynx/network-timing-start\n"
extra=b'''printf '0\\n' > /run/lynx/bootstrap-result
printf '131\\n' > /run/lynx/worker-result
printf '10\\n' > /run/lynx/network-timing-start
printf '133.00 0\\n' > /fixture/uptime
printf '535\\n' > /fixture/target
echo NATIVE_FAST_TIMING_LATE_SLOT
lynx_network_timing_reboot
echo "NATIVE_FAST_TIMING_LATE_EXIT=$?"
printf '600.00 0\\n' > /fixture/uptime
echo NATIVE_FAST_TIMING_TOO_LATE
lynx_network_timing_reboot
echo "NATIVE_FAST_TIMING_TOO_LATE_EXIT=$?"
'''
assert tail.count(anchor)==1;tail=tail.replace(anchor,extra+anchor)
start=s.index('    init=');end=s.index("    put(entries,'init',init)",start);s=s[:start]+'    init='+repr(head)+'+fixture+'+repr(tail)+'\n'+s[end:]
s=s.replace('target={480+5*code}','target={120+5*code}').replace(".split(b'NATIVE_TIMING_INVALID_START')[0]",".split(b'NATIVE_TIMING_INVALID_START')[0].split(b'NATIVE_FAST_TIMING_LATE_SLOT')[0]")
s=s.replace("checks['38_resets']","checks['39_resets']").replace('==38\n','==39\n')
anchor="    checks['clean_poweroff']"
extra="    late=console.split(b'NATIVE_FAST_TIMING_LATE_SLOT')[-1].split(b'NATIVE_FAST_TIMING_TOO_LATE')[0]\n    checks['late_result_uses_separate_slot']=b'LYNX_NETWORK_TIMING code=9 target=525' in late and b'NATIVE_FAST_TIMING_LATE_EXIT=1' in late\n    refused=console.split(b'NATIVE_FAST_TIMING_TOO_LATE')[-1].split(b'NATIVE_TIMING_INVALID_START')[0]\n    checks['missed_all_slots_refused']=b'NATIVE_FAST_TIMING_TOO_LATE_EXIT=1' in refused and b'NATIVE_TIMING_RESET' not in refused\n"
assert s.count(anchor)==1;s=s.replace(anchor,extra+anchor).replace("console.split(b'NATIVE_FAST_TIMING_TOO_LATE')[-1]", "console.split(b'NATIVE_FAST_TIMING_TOO_LATE\\r\\n')[-1]");save('test_native_fast_wifi_timing.py',s)
print('V15 synchronized wrappers and batched early/late timing tests prepared.')
