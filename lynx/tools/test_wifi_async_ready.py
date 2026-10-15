"""Exercise marked-probe/idle-worker/netdev readiness guards without a handset."""
import argparse,gzip,hashlib,json,os,subprocess,sys,time
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';SOURCE=P/'wifi-async-ready.sh'
parser=argparse.ArgumentParser();parser.add_argument('--native',action='store_true');args=parser.parse_args()
out=R/'tools/test-artifacts'/('wifi-async-ready-'+str(time.time_ns()));out.mkdir(mode=0o700);cases=out/'cases';cases.mkdir()
spec=[('ready',True),('delayed',True),('busy',False),('wrong-module',False),('missing-phy',False),('missing-interface',False),('bad-type',False),('bad-index',False),('zero-index',False),('ambiguous',False),('unreadable',False),('wrong-offset',False),('fake-symbol',False),('changing-index',False),('changing-pid',False),('wrong-token',False),('stale-success',False),('latest-marker',False),('probe-failed',False),('not-timeout',False)]
token='1234567890abcdef1234567890abcdef';marker='LYNX_STATION_ATTEMPT_BEGIN '+token
for name,expected in spec:
    f=cases/name;f.mkdir();run=f/'run';run.mkdir();(run/'clock').write_text('0\n');(run/'calls').write_text('0\n');(f/'token').write_text(token+'\n')
    module=f/'modules/wlan_drv_gen4m_6983';module.mkdir(parents=True)
    dev=f/'net/wlan0';(dev/'device/driver').mkdir(parents=True)
    if name!='missing-phy':(dev/'phy80211').mkdir()
    if name=='wrong-module':module=f/'modules/other';module.mkdir()
    (dev/'device/driver/module').symlink_to(module)
    (dev/'type').write_text(('2' if name=='bad-type' else '1')+'\n');(dev/'ifindex').write_text(('bad' if name=='bad-index' else '0' if name=='zero-index' else '4')+'\n')
    if name=='missing-interface':dev.rename(f/'net/other')
    log=marker+'\nwlanProbe: probe success, feature set: 0x1, persistNetdev: 1\n'
    if name=='wrong-token':log=log.replace(token,'f'*32)
    if name=='stale-success':log='wlanProbe: probe success, feature set: 0x1\n'+marker+'\n'
    if name=='latest-marker':log+=marker+'\nordinary\n'
    if name=='probe-failed':log+='wlanProbe: probe failed, reason:3\n'
    (f/'dmesg').write_text(log)
    bb=f/'busybox';bb.write_text('''#!/bin/sh
if [ "$1" = sleep ]; then
    read -r value < "$LYNX_ASYNC_FIXTURE/run/clock"
    printf '%s\\n' "$((value+$2))" > "$LYNX_ASYNC_FIXTURE/run/clock"
    exit 0
fi
if [ "$1" = dmesg ]; then cat "$LYNX_ASYNC_FIXTURE/dmesg"; exit $?; fi
exec "$@"
''');bb.chmod(0o755)
    source=SOURCE.read_text().replace('/run/lynx',str(run)).replace('/etc/lynx/session-token',str(f/'token')).replace('/sys/class/net',str(f/'net')).replace('/sys/module',str(f/'modules'))
    stub='''
lynx_clock() { IFS= read -r seconds < "$LYNX_ASYNC_FIXTURE/run/clock"; }
lynx_power_failure_code() { nt_station_code=25; [ "$mode" != not-timeout ] || nt_station_code=28; }
lynx_capture_wifi_worker_stack() {
    read -r calls < "$LYNX_ASYNC_FIXTURE/run/calls"
    calls=$((calls+1)); printf '%s\\n' "$calls" > "$LYNX_ASYNC_FIXTURE/run/calls"
    status=0; pid=101; site='mtk_wland_thread_main+0xe4/0x450'
    case "$mode" in
        busy) site='conninfra_pwr_on+0x20/0x300' ;;
        delayed) [ "$calls" -ge 3 ] || site='conninfra_pwr_on+0x20/0x300' ;;
        ambiguous) status=32 ;;
        unreadable) status=33 ;;
        wrong-offset) site='mtk_wland_thread_main+0xe40/0x450' ;;
        fake-symbol) site='FAKE_mtk_wland_thread_main+0xe4/0x450' ;;
        changing-index) printf '%s\\n' "$calls" > "$LYNX_ASYNC_FIXTURE/net/wlan0/ifindex" ;;
        changing-pid) pid=$calls ;;
    esac
    printf '%s\\n' "$status" > "$LYNX_ASYNC_FIXTURE/run/wifi-worker-stack-result"
    printf '%s\\n' "$pid" > "$LYNX_ASYNC_FIXTURE/run/wifi-worker-pid"
    printf '%s\\n' "$site" > "$LYNX_ASYNC_FIXTURE/run/wifi-worker-stack"
}
'''
    script=f/'test.sh';script.write_text('#!/bin/sh\nexport LYNX_ASYNC_FIXTURE='+str(f)+'\nmode='+name+'\nBB='+str(bb)+'\n'+stub+'\n'+source+'\nlynx_wifi_async_ready\nrc=$?\nprintf "ASYNC_READY_RESULT=%s\\n" "$rc"\nexit "$rc"\n');script.chmod(0o755)
results=[]
for name,expected in spec:
    p=subprocess.run(['sh',str(cases/name/'test.sh')],capture_output=True,text=True,timeout=30);(cases/name/'console.log').write_text(p.stdout+p.stderr)
    assert (p.returncode==0)==expected,(name,p.returncode,p.stdout,p.stderr)
    calls=int((cases/name/'run/calls').read_text());assert calls<=45
    if name=='ready':assert calls==2
    if name=='delayed':assert calls==4
    if name=='not-timeout':assert calls==0
    results.append({'case':name,'passed':True,'calls':calls})
report={'passed':True,'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'phone_contacted':False,'cases':results}
if args.native:
    sys.path.insert(0,str(P))
    from image_formats import read_boot_v4,read_newc,require
    from ramdisk_codec import decompress
    from network_userspace import put
    from prepare_busybox_diagnostics import pack
    b=read_boot_v4((P/'artifacts/busybox-wifi-ssh-twostage-v14/nord3-busybox-candidate.img').read_bytes());e=read_newc(decompress(b['ramdisk']))
    selected=['ready','delayed','busy','wrong-module','latest-marker','changing-pid']
    for name in selected:
        f=cases/name
        for path in [f,*f.rglob('*')]:
            rel='fixture/'+str(path.relative_to(cases));mode=path.lstat().st_mode
            if path.is_symlink():data=str(path.readlink()).replace(str(cases),'/fixture').encode()
            elif path.is_dir():data=b''
            else:
                data=path.read_bytes()
                if path.name in ['test.sh','busybox']:data=data.replace(str(cases).encode(),b'/fixture').replace(b'exec "$@"',b'exec /bin/busybox "$@"').replace(b'then cat ',b'then /bin/busybox cat ')
                if path.name in ['clock','calls']:data=b'0\n'
            put(e,rel,data,mode)
    put(e,'fixture',b'',0o40700)
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
    for name in selected:
        expected=dict(spec)[name];init+=('echo NATIVE_ASYNC_CASE='+name+'\n/bin/busybox sh /fixture/'+name+'/test.sh\necho NATIVE_ASYNC_EXIT=$?\n').encode()
    init+=b'/bin/busybox poweroff -f\n';put(e,'init',init)
    (out/'Image').write_bytes(gzip.decompress(b['kernel']));(out/'initramfs').write_bytes(pack(e));(out/'init-source').write_bytes(init)
    q=R/'tools/qemu/noble/root';env=dict(os.environ,LD_LIBRARY_PATH=str(q/'usr/lib/x86_64-linux-gnu'),QEMU_MODULE_DIR=str(q/'usr/lib/x86_64-linux-gnu/qemu'),TMPDIR=str(R/'tools/mtk-tmp'))
    command=[str(q/'usr/bin/qemu-system-aarch64'),'-L',str(q/'usr/share/qemu'),'-no-user-config','-nodefaults','-machine','virt,gic-version=3','-accel','tcg','-cpu','cortex-a710','-smp','2','-m','1024','-display','none','-monitor','none','-serial','stdio','-nic','none','-no-reboot','-kernel',str(out/'Image'),'-initrd',str(out/'initramfs'),'-append','console=ttyAMA0 rdinit=/init loglevel=7 panic=0']
    p=subprocess.run(command,env=env,capture_output=True,timeout=120);console=p.stdout+p.stderr;(out/'native-console.log').write_bytes(console);checks={}
    for name in selected:
        section=console.split(('NATIVE_ASYNC_CASE='+name+'\r\n').encode())[-1].split(b'NATIVE_ASYNC_CASE=')[0]
        checks[name]=('NATIVE_ASYNC_EXIT='+('0' if dict(spec)[name] else '1')).encode() in section
    checks['clean_poweroff']=b'reboot: Power down' in console;checks['no_exception']=not any(s in console for s in [b'Kernel panic',b'Internal error:',b'CFI failure'])
    report.update(native_checks=checks,kernel_sha256=hashlib.sha256(b['kernel']).hexdigest());assert p.returncode==0 and all(checks.values()),checks
path=out/'result.json';path.write_text(json.dumps(report,indent=2)+'\n');print(path)
