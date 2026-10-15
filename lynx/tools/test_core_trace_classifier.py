"""Check per-task, nested correlation before trusting a physical diagnosis."""
import hashlib,json,subprocess,time
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
SOURCE=ROOT/'linux-port/lynx-classify-core-trace.awk'


def main():
    out=ROOT/'tools/test-artifacts'/('core-trace-classifier-'+str(time.time_ns())); out.mkdir()
    health='sh-123 [000] 1.0: health_pid: (syscall) ret=123\n'
    def entry(kind,pid=234,name='112b0000.ufshci'):
        return f'worker-{pid} [001] 2.0: {kind}_enter: (fn) name="{name}"\n'
    def leave(kind,value,pid=234):
        return f'worker-{pid} [001] 2.1: {kind}_return: (fn) ret={value}\n'
    mtk=lambda value:f'worker-234 [001] 2.2: mtk_probe_return: (fn) ret={value}\n'
    specs=[('empty','',1,0),('health-only',health,7,0),('wrong-health',health.replace('ret=123','ret=999'),1,0),
           ('registration-rejected',health,3,1),('registration-unhealthy','',1,1),
           ('probe-success',health+mtk(0),2,0),('probe-error',health+mtk(-517),7,0),
           ('supplier-error',health+entry('supplier')+leave('supplier',-517),4,0),
           ('pins-error',health+entry('pins')+leave('pins',-22),5,0),
           ('domain-error',health+entry('domain')+leave('domain',-517),6,0),
           ('unrelated-error',health+entry('supplier',name='unrelated')+leave('supplier',-517),7,0),
           ('unpaired',health+leave('supplier',-517),1,0),('unfinished',health+entry('supplier'),1,0),
           ('malformed',health+entry('pins')+leave('pins','oops'),1,0),
           ('nested',health+entry('supplier')+entry('supplier',name='unrelated')+leave('supplier',0)+leave('supplier',-517),4,0),
           ('interleaved',health+entry('supplier')+entry('supplier',pid=999,name='unrelated')+leave('supplier',-517,pid=999)+leave('supplier',0),7,0),
           ('last-success',health+entry('supplier')+leave('supplier',-517)+entry('supplier')+leave('supplier',0),7,0),
           ('stage-priority',health+entry('supplier')+leave('supplier',-517)+entry('domain')+leave('domain',-517),4,0),
           ('bad-retval-boundary',health+entry('supplier')+leave('supplier','0garbage'),1,0)]
    cases=[]
    for name,raw,expected,rejected in specs:
        path=out/(name+'.trace'); path.write_text(raw)
        result=subprocess.run(['awk','-v','expected_pid=123','-v','registration_failed='+str(rejected),'-f',str(SOURCE)],input=raw,text=True,capture_output=True,check=True)
        (out/(name+'.output')).write_text(result.stdout)
        assert int(result.stdout.split()[0])==expected,(name,result.stdout)
        cases.append({'case':name,'fixture':str(path),'expected_code':expected,'registration_failed':rejected})
    report={'passed':True,'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'cases':cases,'phone_contacted':False}
    path=out/'result.json'; path.write_text(json.dumps(report,indent=2)+'\n'); print(path)


if __name__=='__main__':main()
