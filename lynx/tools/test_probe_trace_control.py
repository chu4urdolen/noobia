"""Accelerated fixtures for bounded timing codes and exactly-one reset requests."""
import hashlib
import argparse
import json
import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'linux-port/artifacts/busybox-probe-trace-v1/trace-runtime.sh'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--v3',action='store_true');parser.add_argument('--core',action='store_true');parser.add_argument('--platform',action='store_true');args=parser.parse_args()
    if args.platform:args.core=True
    source_path=ROOT/'linux-port/artifacts/busybox-probe-trace-v3/trace-runtime.sh' if args.v3 else SOURCE
    if args.core: source_path=ROOT/'linux-port/artifacts/busybox-core-probe-v1/trace-runtime.sh'
    if args.platform: source_path=ROOT/'linux-port/artifacts/busybox-platform-probe-v1/trace-runtime.sh'
    out = ROOT / 'tools/test-artifacts' / (('probe-trace-v3-control-' if args.v3 else 'probe-trace-control-') + str(time.time_ns()))
    if args.core: out=ROOT/'tools/test-artifacts'/('core-probe-control-'+str(time.time_ns()))
    if args.platform: out=ROOT/'tools/test-artifacts'/('platform-probe-control-'+str(time.time_ns()))
    out.mkdir()
    raw = source_path.read_text()
    fake = out / 'busybox'
    fake.write_text('''#!/usr/bin/python3
import os,pathlib,shutil,sys,time
r=pathlib.Path(os.environ['FIXTURE']); a=sys.argv[1:]
if a[0]=='sleep':
 time.sleep(.005);p=r/'uptime';p.write_text(str(int(p.read_text().split('.')[0])+5)+'.00 0\\n')
elif a[0]=='mv':shutil.move(a[1],a[2])
elif a[0]=='readlink':print(os.readlink(a[1]))
elif a[0]=='awk':print(os.environ['PROBE_CODE']+' 1 -517 0 unknown 0 0 0')
elif a[0]=='cat':print('123')
elif a[0]=='grep':sys.exit(0 if os.environ['PROBE_CODE']=='3' else 1)
else:sys.exit(2)
''')
    fake.chmod(0o755)
    reset = out / 'reset'
    reset.write_text('''#!/usr/bin/python3
import os,pathlib
r=pathlib.Path(os.environ['FIXTURE'])
with (r/'resets').open('a') as f:f.write('reset\\n')
(r/'release').touch()
''')
    reset.chmod(0o755)
    cases = []
    specifications=[('result-'+str(n),153,n) for n in range(1,8)]+[('capture-failure',153,8),('stalled',None,8),('bad-clock',0,None)]
    if args.v3:
        specifications=[('setup-failure',153,1)]+[('result-'+str(n),153,n) for n in [2,4,5,6,7]]+[('capture-failure',153,3),('stalled',None,8),('bad-clock',0,None)]
    if args.core:
        specifications=[('setup-failure',153,1)]+[('result-'+str(n),153,n) for n in range(2,8)]+[('capture-failure',153,1),('stalled',None,8),('bad-clock',0,None)]
    for name, status, code in specifications:
        folder = out / name
        (folder / 'run/lynx').mkdir(parents=True)
        (folder / 'sys/device').mkdir(parents=True)
        (folder / 'run/lynx/boot.log').touch()
        (folder / 'uptime').write_text('invalid 0\n' if name == 'bad-clock' else '0.00 0\n')
        if name == 'bound-no-partition':
            (folder / 'sys/device/driver').symlink_to('/sys/bus/platform/drivers/ufshcd-mtk')
        source = raw.replace('/proc/uptime',str(folder/'uptime')).replace('/run/lynx',str(folder/'run/lynx')).replace('/sys/bus/platform/devices',str(folder/'sys')).replace('/bin/boot-proof-reboot',str(reset))
        child = 'return ' + str(status) if status is not None else f"while [ ! -f '{folder}/release' ]; do sleep .005; done; return 255"
        script = folder / 'test.sh'
        script.write_text(f"BB='{fake}'\nlog() {{ printf '%s\\n' \"$*\"; }}\nlynx_wifi_bootstrap_child() {{ {child}; }}\n" + source + f'\nlynx_driver_trace_setup() {{ return {1 if code==1 and name!="capture-failure" else 0}; }}\nlynx_driver_trace_capture() {{ return {1 if name=="capture-failure" else 0}; }}\nlynx_storage_probe\n')
        result = subprocess.run(['sh',str(script)],env=dict(os.environ,FIXTURE=str(folder),PROBE_CODE=str(code if code else 8)),capture_output=True,text=True,timeout=30)
        (folder / 'stdout').write_text(result.stdout)
        (folder / 'stderr').write_text(result.stderr)
        resets = (folder/'resets').read_text().splitlines() if (folder/'resets').exists() else []
        clock = int((folder/'uptime').read_text().split('.')[0]) if name != 'bad-clock' else None
        assert result.returncode == 1, (name,result.stderr)
        assert len(resets) == (1 if code is not None else 0), (name,resets)
        if code is not None:
            assert f'STORAGE_OUTCOME code={code} ' in result.stdout, (name,result.stdout)
            assert clock == 40 + 25*code, (name,clock)
        cases.append({'case':name,'expected_code':code,'clock_seconds':clock,'reset_calls':len(resets),'exit_code':result.returncode})
    target = out/'result.json'
    target.write_text(json.dumps({'passed':True,'source_sha256':hashlib.sha256(source_path.read_bytes()).hexdigest(),
                                  'cases':cases,'phone_contacted':False,'real_reboots':False,
                                  'limits':'Accelerated host fixtures validate result/timer control only; physical boot timing and UFS discovery are not emulated.'},indent=2)+'\n')
    print(target)


if __name__ == '__main__':
    main()
