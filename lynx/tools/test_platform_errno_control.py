"""Exercise all128 timer values and worker/setup failures without real reboots."""
import hashlib,json,os,subprocess,time
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent;SOURCE=ROOT/'linux-port/lynx-platform-errno-runtime.sh'


def main():
    out=ROOT/'tools/test-artifacts'/('platform-errno-control-'+str(time.time_ns()));out.mkdir()
    fake=out/'busybox'
    fake.write_text('''#!/usr/bin/python3
import os,pathlib,shutil,sys,time
r=pathlib.Path(os.environ['FIXTURE']);a=sys.argv[1:]
if a[0]=='sleep':
 time.sleep(.001);p=r/'uptime';p.write_text(str(int((r/'target').read_text()) if (r/'target').exists() else int(p.read_text().split('.')[0])+1)+'.00 0\\n')
elif a[0]=='mv':shutil.move(a[1],a[2])
elif a[0]=='cat':print('123')
elif a[0]=='awk':print(os.environ['FIELD']+' -19 1 1')
else:sys.exit(2)
''');fake.chmod(0o755)
    reset=out/'reset';reset.write_text('''#!/usr/bin/python3
import os,pathlib
r=pathlib.Path(os.environ['FIXTURE'])
with (r/'resets').open('a') as f:f.write('reset\\n')
(r/'release').touch()
''');reset.chmod(0o755)
    specs=[('field-'+str(n),n,153) for n in range(128)]+[('stalled',127,None),('setup-failure',126,153),('capture-failure',126,153),('bad-clock',None,153)]
    raw=SOURCE.read_text();cases=[]
    for name,field,status in specs:
        folder=out/name;(folder/'run/lynx').mkdir(parents=True);(folder/'run/lynx/boot.log').touch()
        (folder/'uptime').write_text('invalid 0\n' if name=='bad-clock' else '0.00 0\n')
        source=raw.replace('/proc/uptime',str(folder/'uptime')).replace('/run/lynx',str(folder/'run/lynx')).replace('/bin/boot-proof-reboot',str(reset))
        child='return '+str(status) if status is not None else f"while [ ! -f '{folder}/release' ]; do sleep .001; done; return 255"
        log=f'''log() {{ printf '%s\\n' "$*"; case "$*" in 'ERRNO_FIELD code='*) printf '%s' "$probe_delay" > '{folder}/target';; esac; }}
'''
        script=folder/'test.sh';script.write_text(f"BB='{fake}'\n"+log+f'lynx_wifi_bootstrap_child() {{ {child}; }}\n'+source+f'''
lynx_driver_trace_setup() {{ return {1 if name=='setup-failure' else 0}; }}
lynx_driver_trace_capture() {{ return {1 if name=='capture-failure' else 0}; }}
lynx_live_ufs_name() {{ live_ufs_name=bootdevice; return 0; }}
lynx_storage_probe
''')
        result=subprocess.run(['sh',str(script)],env=dict(os.environ,FIXTURE=str(folder),FIELD=str(field or 0)),capture_output=True,text=True,timeout=30)
        (folder/'stdout').write_text(result.stdout);(folder/'stderr').write_text(result.stderr)
        resets=(folder/'resets').read_text().splitlines() if (folder/'resets').exists() else []
        assert result.returncode==1,(name,result.stderr)
        assert len(resets)==(0 if field is None else 1),(name,resets)
        if field is not None:
            clock=int((folder/'uptime').read_text().split('.')[0]);assert clock==60+2*field,(name,clock)
            assert f'ERRNO_FIELD code={field} ' in result.stdout,(name,result.stdout)
        cases.append({'case':name,'expected_field':field,'reset_calls':len(resets)})
    report={'passed':True,'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'cases':cases,'phone_contacted':False,'real_reboots':False,
            'limits':'Accelerated clock fixture jumps on a requested timer sleep; verifies exact deadline, all field values and one-reset control, not physical timing.'}
    path=out/'result.json';path.write_text(json.dumps(report,indent=2)+'\n');print(path)


if __name__=='__main__':main()
