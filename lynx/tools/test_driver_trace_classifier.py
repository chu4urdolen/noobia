"""Check interleaving, nested calls, errors and incomplete traces conservatively."""
import hashlib,json,subprocess,time
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
SOURCE=ROOT/'linux-port/lynx-classify-driver-trace.awk'


def event(pid,name,args):
    return f' insmod-{pid} [001] d..1 1.000000: {name}: (function+0x0/0x10) {args}\n'


def main():
    out=ROOT/'tools/test-artifacts'/('driver-trace-classifier-'+str(time.time_ns()));out.mkdir()
    u=lambda ret:event(10,'init_return',f'ret={ret}')
    enter=lambda pid,name:event(pid,'domain_enter',f'name="{name}"')
    leave=lambda pid,ret:event(pid,'domain_return',f'ret={ret}')
    cases=[('defer',u(-517),2),('configuration',u(-22),4),('missing-device',u(-19),4),('lookup',u(-2),4),
           ('timeout',u(-110),5),('io',u(-5),5),('other',u(-12),6),('success',u(0),7),('empty','',8),
           ('domain',enter(10,'112b0000.ufshci')+leave(10,-517),3),
           ('unrelated-domain',enter(10,'11201000.usb')+leave(10,-517),8),
           ('interleaved',enter(10,'112b0000.ufshci')+enter(20,'11201000.usb')+leave(20,-5)+leave(10,-517),3),
           ('nested',enter(10,'112b0000.ufshci')+enter(10,'other')+leave(10,-5)+leave(10,-517),3),
           ('later-success',u(-517)+u(0),7),('unpaired',leave(10,-517),8),
           ('unfinished',enter(10,'112b0000.ufshci'),8),('bad-ret',event(10,'init_return','ret=garbled'),8),
           ('domain-with-lost-event',leave(30,-5)+enter(10,'112b0000.ufshci')+leave(10,-517),8)]
    results=[]
    for name,text,code in cases:
        capture=out/(name+'.log');capture.write_text(text)
        result=subprocess.run(['awk','-f',str(SOURCE),str(capture)],capture_output=True,text=True,timeout=5)
        assert result.returncode==0 and int(result.stdout.split()[0])==code,(name,result.stdout,result.stderr)
        results.append({'case':name,'code':code,'output':result.stdout.strip()})
    (out/'result.json').write_text(json.dumps({'passed':True,'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'cases':results,'phone_contacted':False},indent=2)+'\n')
    print(out/'result.json')


if __name__=='__main__':main()
