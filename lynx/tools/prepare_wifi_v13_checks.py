"""Create fixed V13 wrappers and actual ARM timing fixtures without phone access."""
import ast,json
from pathlib import Path
R=Path(__file__).resolve().parent.parent;T=R/'tools';P=R/'linux-port'
old='1e51aeff4eae67f50c5bce85986d7f423a14c6274332b99d2e64015288f8b73b'
new=json.loads((P/'artifacts/busybox-wifi-ssh-twostage-v13/build-validation.json').read_text())['candidate_sha256']
def update(s):return s.replace(old,new).replace('busybox-wifi-ssh-twostage-v12','busybox-wifi-ssh-twostage-v13').replace('wifi-v12-','wifi-v13-').replace('validate_wifi_v12_image','validate_wifi_v13_image')
def save(name,s):
    p=T/name;assert not p.exists(),p;compile(s,str(p),'exec');p.write_text(s)
for name in ['lynx_wifi_v12_contact.py','lynx_boot_a_wifi_v12_trial.py','test_wifi_v12_image_vm.py']:
    save(name.replace('v12','v13'),update((T/name).read_text()))
s=update((T/'test_native_station_failure_timing.py').read_text()).replace('emulated-station-failure-timing-native-','emulated-power-failure-timing-native-')
tree=ast.parse(s);node=next(n for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='init' for t in n.targets))
head=ast.literal_eval(node.value.left.left);tail=ast.literal_eval(node.value.right)
start=tail.index(b'            status=116\n');end=tail.index(b'            printf',start)
tail=tail[:start]+b'            status=116\n'+tail[end:]
start=tail.index(b'            case "$code" in\n');end=tail.index(b'            [ "$code" != 35 ]',start)
case=b'''            case "$code" in
                25) echo '[WIFI-FW] WiFi on/off takes more than 30 seconds' ;;
                26) echo '[WIFI-FW] thread[E]: Invalid pointer' ;;
                27|28|29|30|31|32|33|34) echo "wlanProbe: probe failed, reason:$((code-27))" ;;
                *) echo ordinary ;;
            esac >> /run/lynx/station-dmesg
            echo 'WMT turn on WIFI fail!' >> /run/lynx/station-dmesg
'''
tail=tail[:start]+case+tail[end:]
start=s.index('    init=');end=s.index("    put(entries,'init',init)",start)
s=s[:start]+'    init='+repr(head)+'+fixture+'+repr(tail)+'\n'+s[end:]
save('test_native_power_failure_timing.py',s)
print('V13 fixtures and fixed trial/listener wrappers prepared; no phone contacted.')
