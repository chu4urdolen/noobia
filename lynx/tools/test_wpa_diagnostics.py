"""Batch WPA log/status/scan/rfkill parser cases on host and exact ARM BusyBox."""
import gzip,hashlib,json,os,subprocess,sys,time
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';SOURCE=P/'wpa-diagnostics.sh';out=R/'tools/test-artifacts'/('wpa-diagnostics-'+str(time.time_ns()));out.mkdir(mode=0o700);cases=out/'cases';cases.mkdir();token='a'*32
header='bssid / frequency / signal level / flags / ssid\n';ap='00:11:22:33:44:55\t2437\t-40\t[WPA2-PSK-CCMP][ESS]\tNoobia\n'
spec=[('no-control','',1,0,'',header,0,50),('empty-status','',0,0,'',header,0,50),('duplicate-status','SCANNING\nwpa_state=DISCONNECTED',0,0,'',header,0,50),('completed','COMPLETED',0,0,'WRONG_KEY\n',header,0,51),('wrong-key','DISCONNECTED',0,0,'reason=WRONG_KEY\n',header,0,52),('four-way','DISCONNECTED',0,0,'WPA: 4-Way Handshake failed\n',header,0,52),('assoc-reject','DISCONNECTED',0,0,'CTRL-EVENT-ASSOC-REJECT status_code=1\n',header+ap,0,53),('auth-reject','DISCONNECTED',0,0,'CTRL-EVENT-AUTH-REJECT\n',header+ap,0,53),('rfkill','DISCONNECTED',0,0,'',header+ap,1,54),('ap-absent','SCANNING',0,0,'',header,0,55),('ap-seen','DISCONNECTED',0,0,'',header+ap,0,56),('scan-failed','DISCONNECTED',0,1,'',header,0,59),('scan-api-fail','DISCONNECTED',0,0,'','FAIL\n',0,59),('cleared-old-error','DISCONNECTED',0,0,'WRONG_KEY\nCTRL-EVENT-CONNECTED\nCTRL-EVENT-DISCONNECTED\n',header+ap,0,56),('last-error','DISCONNECTED',0,0,'WRONG_KEY\nCTRL-EVENT-ASSOC-REJECT\n',header+ap,0,53),('wrong-token','DISCONNECTED',0,0,'',header+ap,0,59)]
spec.extend((s.lower(),s,0,0,'',header+ap,0,57) for s in ['AUTHENTICATING','ASSOCIATING','ASSOCIATED','4WAY_HANDSHAKE','GROUP_HANDSHAKE'])
spec.extend((s.lower(),s,0,0,'',header+ap,0,58) for s in ['INACTIVE','INTERFACE_DISABLED'])
expected={}
for name,state,statusrc,scanrc,log,scan,blocked,code in spec:
    f=cases/name;f.mkdir();run=f/'run';run.mkdir();(f/'token').write_text(token+'\n');(f/'ssid').write_text('Noobia\n');(run/'wpa-snapshot-token').write_text(('b'*32 if name=='wrong-token' else token)+'\n');(run/'wpa-status-result').write_text(str(statusrc)+'\n');(run/'wpa-scan-result').write_text(str(scanrc)+'\n');(run/'wpa-rfkill-blocked').write_text(str(blocked)+'\n');(run/'wpa-status').write_text('wpa_state='+state+'\n' if state else '');(run/'wpa-scan').write_text(scan);(run/'wpa.log').write_text(log)
    bb=f/'busybox';bb.write_text('#!/bin/sh\nexec "$@"\n');bb.chmod(0o755)
    source=SOURCE.read_text().replace('/run/lynx',str(run)).replace('/etc/lynx/session-token',str(f/'token')).replace('/etc/lynx/wpa-target-ssid',str(f/'ssid'))
    script=f/'test.sh';script.write_text('BB='+str(bb)+'\n'+source+'\nlynx_wpa_failure_code\nprintf "%s\\n" "$nt_wpa"\n');script.chmod(0o755);expected[name]=code
    p=subprocess.run(['sh',str(script)],capture_output=True,text=True,timeout=10);assert p.returncode==0 and p.stdout.strip()==str(code),(name,p.stdout,p.stderr)
# Actual snapshot wiring: controlled CLI replies plus a synthetic blocked WLAN.
name='snapshot';f=cases/name;f.mkdir();run=f/'run';run.mkdir();(f/'token').write_text(token+'\n');(f/'ssid').write_text('Noobia\n');(run/'wpa.log').write_text('');(f/'status').write_text('wpa_state=DISCONNECTED\n');(f/'scan').write_text(header+ap);rf=f/'rfkill/rfkill0';rf.mkdir(parents=True);(rf/'type').write_text('wlan\n');(rf/'soft').write_text('1\n');(rf/'hard').write_text('0\n');bb=f/'busybox';bb.write_text('#!/bin/sh\nexec "$@"\n');bb.chmod(0o755)
control=f/'control';control.write_text('#!/bin/sh\nBB='+str(bb)+'\ncase "$5" in status) exec "$BB" cat '+str(f/'status')+' ;; scan_results) exec "$BB" cat '+str(f/'scan')+' ;; *) exit 1 ;; esac\n');control.chmod(0o755)
source=SOURCE.read_text().replace('/run/lynx',str(run)).replace('/etc/lynx/session-token',str(f/'token')).replace('/etc/lynx/wpa-target-ssid',str(f/'ssid')).replace('/sys/class/rfkill',str(f/'rfkill')).replace('/sbin/wpa_cli',str(control))
script=f/'test.sh';script.write_text('BB='+str(bb)+'\nwifi_interface=wlan0\n'+source+'\nlynx_wpa_snapshot\nprintf "%s\\n" "$nt_wpa"\n');script.chmod(0o755);expected[name]=54
p=subprocess.run(['sh',str(script)],capture_output=True,text=True,timeout=15);assert p.returncode==0 and p.stdout.strip()=='54',(p.stdout,p.stderr)
sys.path.insert(0,str(P))
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress
from network_userspace import put
from prepare_busybox_diagnostics import pack
b=read_boot_v4((P/'artifacts/busybox-wifi-ssh-twostage-v18/nord3-busybox-candidate.img').read_bytes());e=read_newc(decompress(b['ramdisk']))
for f in [cases,*cases.rglob('*')]:
    rel='fixture'+('/'+str(f.relative_to(cases)) if f!=cases else '');data=b'' if f.is_dir() else f.read_bytes()
    if f.name in ['test.sh','busybox','control']:data=data.replace(str(cases).encode(),b'/fixture').replace(b'exec "$@"',b'exec /bin/busybox "$@"')
    put(e,rel,data,f.lstat().st_mode)
init=b'''#!/bin/sh
export PATH=/bin:/sbin
BB=/bin/busybox
$BB mount -t proc proc /proc
$BB mount -t sysfs sysfs /sys
$BB mount -t tmpfs tmpfs /dev
$BB mknod -m 600 /dev/console c 5 1
$BB mknod -m 666 /dev/null c 1 3
exec > /dev/console 2>&1
'''
for name,code in expected.items():init+=('result=$(/bin/busybox sh /fixture/'+name+'/test.sh)\nif [ "$result" = '+str(code)+' ]; then echo NATIVE_WPA_'+name+'=PASS; else echo NATIVE_WPA_'+name+'=FAIL:$result; fi\n').encode()
init+=b'/bin/busybox poweroff -f\n';put(e,'init',init);(out/'Image').write_bytes(gzip.decompress(b['kernel']));(out/'initramfs').write_bytes(pack(e));(out/'init-source').write_bytes(init)
q=R/'tools/qemu/noble/root';env=dict(os.environ,LD_LIBRARY_PATH=str(q/'usr/lib/x86_64-linux-gnu'),QEMU_MODULE_DIR=str(q/'usr/lib/x86_64-linux-gnu/qemu'),TMPDIR=str(R/'tools/mtk-tmp'))
command=[str(q/'usr/bin/qemu-system-aarch64'),'-L',str(q/'usr/share/qemu'),'-no-user-config','-nodefaults','-machine','virt,gic-version=3','-accel','tcg','-cpu','cortex-a710','-smp','2','-m','1024','-display','none','-monitor','none','-serial','stdio','-nic','none','-no-reboot','-kernel',str(out/'Image'),'-initrd',str(out/'initramfs'),'-append','console=ttyAMA0 rdinit=/init loglevel=7 panic=0']
p=subprocess.run(command,env=env,capture_output=True,timeout=90);console=p.stdout+p.stderr;(out/'native-console.log').write_bytes(console);checks={name:('NATIVE_WPA_'+name+'=PASS').encode() in console for name in expected};checks['clean_poweroff']=b'reboot: Power down' in console;checks['no_exception']=not any(s in console for s in [b'Kernel panic',b'Internal error:',b'CFI failure']);report={'passed':p.returncode==0 and all(checks.values()),'checks':checks,'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'kernel_sha256':hashlib.sha256(b['kernel']).hexdigest(),'host_cases':len(expected),'phone_contacted':False,'limits':'Host and actual ARM BusyBox; synthetic status/scan/rfkill and controlled CLI replies, no physical radio.'}
path=out/'result.json';path.write_text(json.dumps(report,indent=2)+'\n');print(path);require(report['passed'],'Native WPA diagnostic check failed')
