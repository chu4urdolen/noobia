"""Prepare V12 native tests, including real supplier ABI and guarded file fixtures."""
import json
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';T=R/'tools'
OLD='4aad96c499317fa7f6d46371657a8e8bb93043b99de6627f801c5508f40a1033';NEW='1e51aeff4eae67f50c5bce85986d7f423a14c6274332b99d2e64015288f8b73b'
def update(s):return s.replace(OLD,NEW).replace('busybox-wifi-ssh-twostage-v11','busybox-wifi-ssh-twostage-v12').replace('wifi-v11-','wifi-v12-')
def save(name,s):
 p=T/name;assert not p.exists(),p;compile(s,str(p),'exec');p.write_text(s)
save('test_wifi_v12_image_vm.py',update((T/'test_wifi_v11_image_vm.py').read_text()))
save('lynx_wifi_v12_contact.py',update((T/'lynx_wifi_v11_contact.py').read_text()))
save('test_native_vendor_wifi_v12_loop.py',update((T/'test_native_vendor_wifi_v11_loop.py').read_text()))
s=update((T/'lynx_boot_a_wifi_v11_trial.py').read_text()).replace('validate_wifi_v11_image','validate_wifi_v12_image').replace('lynx_network_failure_timing','lynx_station_failure_timing').replace('up to 720 seconds','up to 780 seconds').replace('time.monotonic()+720','time.monotonic()+780')
save('lynx_boot_a_wifi_v12_trial.py',s)
save('lynx_station_failure_timing.py',(T/'lynx_network_failure_timing.py').read_text().replace('range(25)','range(40)'))
s=update((T/'test_native_network_failure_timing.py').read_text()).replace('emulated-network-failure-timing-native-','emulated-station-failure-timing-native-')
s=s.replace("source=(P/'lynx-network-failure-timing.sh').read_bytes()","source=entries['bin/boot-proof-reboot']['data']")
s=s.replace('for code in $(/bin/busybox seq 0 24); do','for code in $(/bin/busybox seq 0 39); do\\n    [ "$code" = 9 ] && continue')
# Existing generated init tail is represented as a Python byte literal, not raw multiline.
old="    /bin/busybox rm -f /run/lynx/bootstrap-result /run/lynx/worker-result"
new=old+" /run/lynx/station-result /run/lynx/station-dmesg /run/lynx/radio-clock-result"
s=s.replace(old,new)
# Locate byte-literal init via AST so escaping stays exact.
import ast
tree=ast.parse(s);node=next(n for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='init' for t in n.targets))
assert isinstance(node.value,ast.BinOp)
head=ast.literal_eval(node.value.left.left)
tail=ast.literal_eval(node.value.right)
tail=tail.replace(b'for code in $(/bin/busybox seq 0 24); do',b'for code in $(/bin/busybox seq 0 39); do\n    [ "$code" = 9 ] && continue')
tail=tail.replace(b' /run/lynx/worker-result\n',b' /run/lynx/worker-result /run/lynx/station-result /run/lynx/station-dmesg /run/lynx/radio-clock-result\n')
needle=b'    echo "NATIVE_TIMING_CASE=$code"\n'
extra=b'''    if [ "$code" -ge 25 ]; then
        printf '0\\n' > /run/lynx/bootstrap-result
        if [ "$code" -ge 36 ]; then
            printf '135\\n' > /run/lynx/worker-result
            printf '%s\\n' "$code" > /run/lynx/radio-clock-result
        else
            printf '139\\n' > /run/lynx/worker-result
            status=116
            case "$code" in 25) status=114 ;; 26) status=115 ;; 27) status=117 ;; esac
            printf '%s\\n' "$status" > /run/lynx/station-result
            token=$(/bin/busybox cat /etc/lynx/session-token)
            printf 'LYNX_STATION_ATTEMPT_BEGIN %s\\n' "$token" > /run/lynx/station-dmesg
            case "$code" in
                28) echo 'WMT turn on WIFI fail!' ;;
                29) echo 'Set p2p mode handler is NULL' ;;
                30) echo 'Get wlan0 net device timeout' ;;
                31) echo 'Set wlan mode fail' ;;
                32) echo 'Wi-Fi is resetting' ;;
                33) echo 'WIFI_write invalid param' ;;
                *) echo ordinary ;;
            esac >> /run/lynx/station-dmesg
            [ "$code" != 35 ] || /bin/busybox rm /run/lynx/station-dmesg
        fi
    fi
'''
assert tail.count(needle)==1;tail=tail.replace(needle,extra+needle)
# Skip the removed legacy code9; new detailed station results replace it.
tail=tail.replace(b'for code in $(/bin/busybox seq 0 39); do\n',b'for code in $(/bin/busybox seq 0 39); do\n    [ "$code" = 9 ] && continue\n',1) if b'[ "$code" = 9 ] && continue' not in tail else tail
start=s.index('    init=');end=s.index("    put(entries,'init',init)",start)
s=s[:start]+'    init='+repr(head)+'+fixture+'+repr(tail)+'\n'+s[end:]
s=s.replace('for code in range(25):','for code in [i for i in range(40) if i!=9]:').replace("checks['25_resets']","checks['39_resets']").replace('==25\n','==39\n')
# Timing source from candidate includes parser; keeps CPIO vendor assumptions separate.
save('test_native_station_failure_timing.py',s)
print('V12 guard/network/loop/native39result tests prepared; no phone contacted.')
