"""Distinguish expected driver matching from unrelated probes and setup failures."""
import hashlib,json,subprocess,time
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent;SOURCE=ROOT/'linux-port/lynx-classify-platform-trace.awk'


def main():
    out=ROOT/'tools/test-artifacts'/('platform-trace-classifier-'+str(time.time_ns()));out.mkdir()
    health='sh-123 [000] 1.0: health_pid: (syscall) ret=123\n'
    def entry(kind,pid=234,name='112b0000.ufshci',driver='ufshcd-mtk'):
        return f'worker-{pid} [001] 2.0: {kind}_enter: (fn) name="{name}" driver="{driver}"\n'
    def leave(kind,value,pid=234):
        return f'worker-{pid} [001] 2.1: {kind}_return: (fn) ret={value}\n'
    pair=lambda kind,value:entry(kind)+leave(kind,value)
    specs=[('empty','',1),('health-only',health,5),('wrong-health',health.replace('ret=123','ret=999'),1),
           ('no-match',health+pair('match',0),2),('negative-match',health+pair('match',-517),2),
           ('matched-no-probe',health+pair('match',1),6),('dma-error',health+pair('dma',-22),3),
           ('platform-error',health+pair('platform',-19),4),('platform-success',health+pair('platform',0),7),
           ('other-driver',health+entry('match',driver='other')+leave('match',0),5),
           ('unrelated-device',health+entry('match',name='unrelated')+leave('match',1),5),
           ('unpaired',health+leave('match',0),1),('unfinished',health+entry('match'),1),
           ('nested',health+entry('match')+entry('match',driver='other')+leave('match',0)+leave('match',1),6),
           ('interleaved',health+entry('match')+entry('match',pid=999,driver='other')+leave('match',0,pid=999)+leave('match',1),6),
           ('last-match-wins',health+pair('match',0)+pair('match',1),6),
           ('malformed-return',health+entry('dma')+leave('dma','0garbage'),1),
           ('missing-driver-field',health+entry('match').replace(' driver="ufshcd-mtk"','')+leave('match',1),1),
           ('all-success',health+pair('match',1)+pair('dma',0)+pair('platform',0),7),
           ('positive-platform-failure',health+pair('platform',1),4)]
    cases=[]
    for name,raw,expected in specs:
        path=out/(name+'.trace');path.write_text(raw)
        result=subprocess.run(['awk','-v','expected_pid=123','-f',str(SOURCE)],input=raw,text=True,capture_output=True,check=True)
        (out/(name+'.output')).write_text(result.stdout);assert int(result.stdout.split()[0])==expected,(name,result.stdout)
        cases.append({'case':name,'fixture':str(path),'expected_code':expected,'registration_failed':0})
    report={'passed':True,'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'cases':cases,'phone_contacted':False}
    path=out/'result.json';path.write_text(json.dumps(report,indent=2)+'\n');print(path)


if __name__=='__main__':main()
