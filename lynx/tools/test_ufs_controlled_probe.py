"""Fixture-only checks of probe refusal paths and bounded exact-device request."""
import hashlib,json,os,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parent.parent;SOURCE=R/'linux-port/ufs-persistent-trace-setup.sh'
def main():
    out=R/'tools/test-artifacts'/('ufs-controlled-probe-'+str(time.time_ns()));out.mkdir()
    fake=out/'busybox';fake.write_text('''#!/usr/bin/python3
import os,pathlib,sys
a=sys.argv[1:];r=pathlib.Path(os.environ['FIXTURE']);mode=os.environ['MODE']
if a[0]=='cat':sys.stdout.write(pathlib.Path(a[1]).read_text())
elif a[0]=='readlink' and a[1]=='-f':print(pathlib.Path(a[2]).resolve())
elif a[0]=='dd':
    args=dict(x.split('=',1) for x in a[1:])
    assert args['bs']=='64' and args['count']=='1'
    data=pathlib.Path(args['if']).read_bytes()
    assert data==b'112b0000.ufshci\\n' and len(data)<=64
    assert args['of']==str(r/'sys/bus/platform/drivers_probe')
    with (r/'probe-calls').open('a') as f:f.write(data.decode())
    if mode=='write-fail':sys.exit(1)
    if mode in ['success','wrong-driver']:
        target=r/'sys/bus/platform/drivers'/('ufshcd-mtk' if mode=='success' else 'other')
        (r/'sys/bus/platform/devices/112b0000.ufshci/driver').symlink_to(target)
else:sys.exit(2)
''');fake.chmod(0o755)
    specs=[('success',0,1),('setup-fail',6,0),('override-changed',9,0),('bound-before',9,0),('bad-name',9,0),('write-fail',7,1),('unbound',8,1),('wrong-driver',8,1)]
    cases=[]
    for name,expected,calls in specs:
        folder=out/name;sysroot=folder/'sys/bus/platform';device=sysroot/'devices'/('bad:name' if name=='bad-name' else '112b0000.ufshci');device.mkdir(parents=True)
        (sysroot/'drivers/ufshcd-mtk').mkdir(parents=True);(sysroot/'drivers/other').mkdir()
        (folder/'run/lynx').mkdir(parents=True);(sysroot/'drivers_probe').touch()
        (device/'driver_override').write_text('keep\n' if name=='override-changed' else 'lynx-block-ufs-probe\n')
        if name=='bound-before':(device/'driver').symlink_to(sysroot/'drivers/ufshcd-mtk')
        source=SOURCE.read_text().split('lynx_ufs_guarded_probe()')[1]
        source='lynx_ufs_guarded_probe()'+source
        source=source.replace('/sys/bus/platform',str(sysroot)).replace('/run/lynx',str(folder/'run/lynx'))
        script=folder/'test.sh';script.write_text("BB='"+str(fake)+"'\nufs_target='"+str(device)+"'\nlynx_ufs_persistent_trace_setup() { return "+('1' if name=='setup-fail' else '0')+"; }\nlynx_diag_emit() { return 0; }\nlog() { printf '%s\\n' \"$*\"; }\n"+source+'\nlynx_ufs_guarded_probe\n')
        result=subprocess.run(['sh',str(script)],env=dict(os.environ,FIXTURE=str(folder),MODE=name),capture_output=True,text=True,timeout=10)
        (folder/'stdout').write_text(result.stdout);(folder/'stderr').write_text(result.stderr)
        assert result.returncode==expected,(name,result.returncode,result.stderr)
        callfile=folder/'probe-calls';count=len(callfile.read_text().splitlines()) if callfile.exists() else 0
        assert count==calls,(name,count)
        if name=='override-changed':assert (device/'driver_override').read_text()=='keep\n'
        cases.append(dict(case=name,status=expected,exact_device_requests=count))
    report=dict(passed=True,cases=cases,source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),phone_contacted=False,limits='Fixture attributes and fake dd/readlink; no kernel/device probing. Actual module trace setup tested separately in stock-kernel VM.')
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(out/'result.json')
if __name__=='__main__':main()
