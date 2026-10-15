"""Offline fixture tests of the exact native init driver guard; no reboot."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import time

ROOT=Path(__file__).resolve().parent.parent

def main():
    source=(ROOT/'linux-port/init-boot-proof').read_text()
    guard=source[source.index('wdt_ready=0'):source.index('\nif [ "$wdt_ready"')]
    assert 'boot-proof-reboot' not in guard and 'insmod' not in guard
    output=ROOT/'tools/test-artifacts'/('boot-proof-guard-'+str(time.time_ns()))
    output.mkdir()
    results=[]
    cases=[{},dict(no_wdt=True),dict(no_mode=True),dict(value=2),dict(value=14),
           dict(offset=40),dict(mask=255),dict(wrong_driver=True),dict(wrong_node=True),
           dict(dangling_driver=True),dict(empty_value=True)]
    for index,options in enumerate(cases):
        path=output/str(index);path.mkdir()
        sysroot=path/'sys'
        devices=sysroot/'bus/platform/devices';devices.mkdir(parents=True)
        drivers=sysroot/'bus/platform/drivers';drivers.mkdir()
        ofroot=sysroot/'firmware/devicetree/base';ofroot.mkdir(parents=True)
        wdt=ofroot/'watchdog@1c007000';wdt.mkdir()
        mode=wdt/'reboot-mode';mode.mkdir()
        for name,value in [('mode-bootloader',options.get('value',3)),('offset',options.get('offset',36)),('mask',options.get('mask',15))]:
            (mode/name).write_bytes(b'' if options.get('empty_value') and name=='mode-bootloader' else struct.pack('>I',value))
        for name,node,driver,missing in [('wdt',wdt,'mtk-wdt',options.get('no_wdt')),
                                        ('mode',mode,'syscon-reboot-mode',options.get('no_mode'))]:
            if missing:continue
            device=devices/name;device.mkdir()
            if options.get('wrong_driver') and name=='mode':driver='wrong-driver'
            target=drivers/driver
            if not (options.get('dangling_driver') and name=='wdt'):target.mkdir()
            (device/'driver').symlink_to(target)
            if options.get('wrong_node') and name=='mode':node=ofroot/'different-node';node.mkdir()
            (device/'of_node').symlink_to(node)
        script='fixturebb() { "$@"; }; BB=fixturebb\n'+guard.replace('/sys/',str(sysroot)+'/')+'\nprintf "%s %s\\n" "$wdt_ready" "$mode_ready"\n'
        (path/'guard.sh').write_text(script)
        process=subprocess.run(['/bin/sh',str(path/'guard.sh')],capture_output=True,text=True,timeout=5)
        (path/'stdout.txt').write_text(process.stdout);(path/'stderr.txt').write_text(process.stderr)
        values=process.stdout.strip().split()
        allowed=values==['1','1']
        assert process.returncode==0 and allowed==(index==0),(options,process.stdout,process.stderr)
        results.append(dict(options=options,reboot_allowed=allowed,passed=True))
    report=dict(phone_contacted=False,reboot_executed=False,cases=results,
                init_source_sha256=hashlib.sha256(source.encode()).hexdigest())
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Eleven exact-source guard cases passed; evidence:',output)

if __name__=='__main__':main()
