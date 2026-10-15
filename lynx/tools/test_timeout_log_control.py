"""Exercise actual AWK and shell gating with fake clock/reset only; no phone."""
import hashlib,json,os,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;P=ROOT/'linux-port'
SOURCE=P/'lynx-timeout-log-runtime.sh'

def main():
    out=ROOT/'tools/test-artifacts'/('timeout-log-control-'+str(time.time_ns()));out.mkdir()
    fake=out/'busybox'
    fake.write_text('''#!/usr/bin/python3
import os,pathlib,shutil,subprocess,sys,time
r=pathlib.Path(os.environ['FIXTURE']);a=sys.argv[1:]
if a[0]=='sleep':
 time.sleep(.001);p=r/'uptime';p.write_text(str(int((r/'target').read_text()) if (r/'target').exists() else int(p.read_text().split('.')[0])+1)+'.00 0\\n')
elif a[0]=='mv':shutil.move(a[1],a[2])
elif a[0]=='cat':print('123')
elif a[0]=='awk':sys.exit(subprocess.run(a).returncode)
else:sys.exit(2)
''');fake.chmod(0o755)
    reset=out/'reset';reset.write_text('''#!/usr/bin/python3
import os,pathlib
r=pathlib.Path(os.environ['FIXTURE'])
with (r/'resets').open('a') as f:f.write('reset\\n')
(r/'release').touch()
''');reset.chmod(0o755)
    fixtures=sorted((ROOT/'tools/test-artifacts').glob('timeout-log-classifier-*/result.json'))
    log_cases=json.loads(fixtures[-1].read_text())['cases']
    cases=[]
    specs=[(c['case'],c['expected_code'],Path(c['fixture']).read_text(),-110,1) for c in log_cases]
    specs += [('health-two',33,'scpsys: Failed to power on mtcmos ufs0(-110)\n',-110,2),
              ('wrong-return',124,'ufs0(-110)\n',-5,1),('zero-return',124,'ufs0(-110)\n',0,1),
              ('wrong-health',125,'ufs0(-110)\n',-110,0),('empty-dmesg',126,'',-110,1),
              ('setup-failure',126,'present\n',-110,1),('capture-failure',126,'present\n',-110,1),
              ('stalled',127,'present\n',-110,1),('bad-clock',None,'present\n',-110,1)]
    for name,field,dmesg,ret,health in specs:
        folder=out/name;run=folder/'run/lynx';run.mkdir(parents=True)
        (run/'boot.log').touch();(run/'kernel-dmesg.log').write_text(dmesg)
        trace='fixture-234 [000] 1.0: platform_enter: (fixture) name="112b0000.ufshci"\n'+f'fixture-234 [000] 1.1: platform_return: (fixture) ret={ret}\n'
        if health:trace+=('fixture-123 [000] 1.2: health_pid: (fixture) ret=123\n')*health
        (run/'driver-trace.log').write_text(trace)
        (folder/'uptime').write_text('invalid 0\n' if name=='bad-clock' else '0.00 0\n')
        source=SOURCE.read_text().replace('/proc/uptime',str(folder/'uptime')).replace('/run/lynx',str(run)).replace('/bin/boot-proof-reboot',str(reset))
        source=source.replace('/etc/lynx/classify-driver-trace.awk',str(P/'lynx-classify-platform-errno.awk')).replace('/etc/lynx/classify-timeout-logs.awk',str(P/'lynx-classify-timeout-logs.awk'))
        child=f"while [ ! -f '{folder}/release' ]; do sleep .001; done; return 255" if name=='stalled' else 'return 153'
        log=f'''log() {{ printf '%s\\n' "$*"; case "$*" in 'TIMEOUT_CONTEXT code='*) printf '%s' "$probe_delay" > '{folder}/target';; esac; }}
'''
        script=folder/'test.sh';script.write_text(f"BB='{fake}'\n"+log+f'lynx_wifi_bootstrap_child() {{ {child}; }}\n'+source+f'''
lynx_driver_trace_setup() {{ return {int(name=='setup-failure')}; }}
lynx_driver_trace_capture() {{ return {int(name=='capture-failure')}; }}
lynx_live_ufs_name() {{ live_ufs_name=112b0000.ufshci; return 0; }}
lynx_storage_probe
''')
        result=subprocess.run(['sh',str(script)],env=dict(os.environ,FIXTURE=str(folder)),capture_output=True,text=True,timeout=30)
        (folder/'stdout').write_text(result.stdout);(folder/'stderr').write_text(result.stderr)
        resets=(folder/'resets').read_text().splitlines() if (folder/'resets').exists() else []
        assert result.returncode==1 and len(resets)==int(field is not None),(name,result.stdout,result.stderr,resets)
        if field is not None:
            assert f'TIMEOUT_CONTEXT code={field} ' in result.stdout,(name,result.stdout)
            assert int((folder/'uptime').read_text().split('.')[0])==60+2*field,name
        cases.append({'case':name,'expected_field':field,'reset_calls':len(resets)})
    report={'passed':True,'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'cases':cases,'phone_contacted':False,'real_reboots':False}
    path=out/'result.json';path.write_text(json.dumps(report,indent=2)+'\n');print(path)

if __name__=='__main__':main()
