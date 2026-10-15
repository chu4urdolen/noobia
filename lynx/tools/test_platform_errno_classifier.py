"""Check every encoded errno and explicit sentinel, including live-name aliases."""
import hashlib,json,subprocess,time
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent;SOURCE=ROOT/'linux-port/lynx-classify-platform-errno.awk'


def main():
    out=ROOT/'tools/test-artifacts'/('platform-errno-classifier-'+str(time.time_ns()));out.mkdir()
    health='sh-123 [000] 1.0: health_pid: (syscall) ret=123\n'
    def pair(value,name='112b0000.ufshci'):
        return f'worker-234 [001] 2.0: platform_enter: (fn) name="{name}"\nworker-234 [001] 2.1: platform_return: (fn) ret={value}\n'
    specs=[('errno-'+str(n),health+pair(-n),n,'112b0000.ufshci') for n in range(121)]
    specs += [('deferred',health+pair(-517),121,'112b0000.ufshci'),('other-negative',health+pair(-999),122,'112b0000.ufshci'),
              ('positive',health+pair(1),123,'112b0000.ufshci'),('absent',health,124,'112b0000.ufshci'),
              ('unknown-target',health+pair(-19),124,''),('wrong-health',pair(-19),125,'112b0000.ufshci'),
              ('malformed',health+pair('0garbage'),126,'112b0000.ufshci'),
              ('unpaired',health+'worker-234 [001] 2.0: platform_return: (fn) ret=-19\n',126,'112b0000.ufshci'),
              ('alias-bootdevice',health+pair(-19,'bootdevice'),19,'bootdevice'),
              ('wrong-name',health+pair(-19,'unrelated'),124,'bootdevice'),
              ('last-return',health+pair(-22)+pair(-19),19,'112b0000.ufshci')]
    cases=[]
    for name,raw,expected,device in specs:
        path=out/(name+'.trace');path.write_text(raw)
        result=subprocess.run(['awk','-v','expected_pid=123','-v','expected_device='+device,'-f',str(SOURCE)],input=raw,text=True,capture_output=True,check=True)
        (out/(name+'.output')).write_text(result.stdout);assert int(result.stdout.split()[0])==expected,(name,result.stdout)
        cases.append({'case':name,'fixture':str(path),'expected_code':expected,'expected_device':device,'registration_failed':0})
    report={'passed':True,'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'cases':cases,'phone_contacted':False}
    path=out/'result.json';path.write_text(json.dumps(report,indent=2)+'\n');print(path)


if __name__=='__main__':main()
