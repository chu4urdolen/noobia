"""Prepare fixed V14 trial wrappers and native marked-timeout stack fixtures."""
import ast,json
from pathlib import Path
R=Path(__file__).resolve().parent.parent;T=R/'tools';P=R/'linux-port'
old='3b7d7962c8526e01b60f953f5f6b660e10cc6d599f7539d290f03857147165bb';new=json.loads((P/'artifacts/busybox-wifi-ssh-twostage-v14/build-validation.json').read_text())['candidate_sha256']
def update(s):return s.replace(old,new).replace('busybox-wifi-ssh-twostage-v13','busybox-wifi-ssh-twostage-v14').replace('wifi-v13-','wifi-v14-').replace('validate_wifi_v13_image','validate_wifi_v14_image')
def save(name,s):
    f=T/name;assert not f.exists(),f;compile(s,str(f),'exec');f.write_text(s)
for name in ['lynx_wifi_v13_contact.py','lynx_boot_a_wifi_v13_trial.py','test_wifi_v13_image_vm.py']:save(name.replace('v13','v14'),update((T/name).read_text()))
s=(T/'test_native_vendor_wifi_v12_loop.py').read_text().replace('1e51aeff4eae67f50c5bce85986d7f423a14c6274332b99d2e64015288f8b73b',new).replace('busybox-wifi-ssh-twostage-v12','busybox-wifi-ssh-twostage-v14').replace('wifi-v12-','wifi-v14-')
save('test_native_vendor_wifi_v14_loop.py',s)
s=update((T/'test_native_power_failure_timing.py').read_text()).replace('emulated-power-failure-timing-native-','emulated-stack-failure-timing-native-')
anchor="    fixture=source.split";idx=s.index(anchor)
s=s[:idx]+"    extra=read_newc(gzip.decompress((F/'supplement.cpio.gz').read_bytes()))\n    put(entries,'etc/lynx/power-stack-parser.sh',extra['etc/lynx/power-stack-parser.sh']['data'],0o100644)\n"+s[idx:]
tree=ast.parse(s);node=next(n for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='init' for t in n.targets))
head=ast.literal_eval(node.value.left.left);tail=ast.literal_eval(node.value.right)
tail=tail.replace(b'[ "$code" = 9 ] && continue',b'case "$code" in 9|35) continue ;; esac')
tail=tail.replace(b' /run/lynx/radio-clock-result\n',b' /run/lynx/radio-clock-result /run/lynx/wifi-worker-stack-result /run/lynx/wifi-worker-stack\n')
start=tail.index(b'            case "$code" in\n');end=tail.index(b'        fi\n    fi\n',start)
extra=b'''            echo '[WIFI-FW] WiFi on/off takes more than 10 seconds' >> /run/lynx/station-dmesg
            echo 'WMT turn on WIFI fail!' >> /run/lynx/station-dmesg
            result=0
            case "$code" in
                25) echo 'mtk_wland_thread_main+0x214/0x450' ;;
                26) echo 'wlanProbe+0x100/0x1400' ;;
                27) echo '_request_firmware+0x100/0x400' ;;
                28) echo 'conninfra_pwr_on+0x50/0x300' ;;
                29) echo 'wait_for_completion+0x20/0x100' ;;
                *) echo 'kthread+0x20/0x400' ;;
            esac > /run/lynx/wifi-worker-stack
            case "$code" in 31|32|33) result=$code ;; esac
            printf '%s\\n' "$result" > /run/lynx/wifi-worker-stack-result
            [ "$code" != 34 ] || echo ordinary > /run/lynx/station-dmesg
'''
tail=tail[:start]+extra+tail[end:]
start=s.index('    init=');end=s.index("    put(entries,'init',init)",start);s=s[:start]+'    init='+repr(head)+'+fixture+'+repr(tail)+'\n'+s[end:]
s=s.replace('if i!=9','if i not in [9,35]').replace("checks['39_resets']","checks['38_resets']").replace('==39\n','==38\n')
save('test_native_stack_failure_timing.py',s)
print('V14 fixtures prepared; no phone contacted.')
