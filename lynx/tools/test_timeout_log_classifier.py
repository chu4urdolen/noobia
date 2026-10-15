"""Check error cascades, target filtering and every valid six-bit mask."""
import hashlib,json,subprocess,time
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent;SOURCE=ROOT/'linux-port/lynx-classify-timeout-logs.awk'


def main():
    out=ROOT/'tools/test-artifacts'/('timeout-log-classifier-'+str(time.time_ns()));out.mkdir()
    messages=['scpsys: Failed to power on mtcmos ufs0(-110)',
              'scpsys: Failed to power on sram/bus ufs0(-110)',
              'ufshcd-mtk 112b0000.ufshci: Controller enable failed',
              'ufshcd-mtk 112b0000.ufshci: link startup failed -110',
              'ufshcd-mtk 112b0000.ufshci: uic cmd 0x16 with arg3 0x0 completion timeout',
              'ufshcd-mtk 112b0000.ufshci: probe failed -110']
    specs=[]
    for selection in range(64):
        raw='\n'.join('[ 3.2][ T1] '+text for n,text in enumerate(messages) if selection & (1<<n))+'\n'
        # Specific power/link/UIC messages also establish generic timeout evidence.
        expected=selection | (32 if selection & (1|2|8|16) else 0)
        specs.append(('selection-'+str(selection),raw,expected))
    specs += [('unrelated','other-device: link startup failed -110\nscpsys: Failed to power on mtcmos gpu(-110)\n',0),
              ('wrong-errno','scpsys: Failed to power on mtcmos ufs0(-5)\n',0),
              ('cascaded','\n'.join(messages[:2])+'\n',35),
              ('non-hce','ufshcd-mtk 112b0000.ufshci: Host controller enable failed with non-hce\n',4)]
    cases=[]
    for name,raw,expected in specs:
        path=out/(name+'.log');path.write_text(raw)
        result=subprocess.run(['awk','-v','expected_device=112b0000.ufshci','-v','expected_domain=ufs0','-f',str(SOURCE)],input=raw,text=True,capture_output=True,check=True)
        assert int(result.stdout)==expected,(name,result.stdout);(out/(name+'.output')).write_text(result.stdout)
        cases.append({'case':name,'fixture':str(path),'expected_code':expected,'expected_device':'112b0000.ufshci','registration_failed':0})
    report={'passed':True,'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'cases':cases,'phone_contacted':False}
    path=out/'result.json';path.write_text(json.dumps(report,indent=2)+'\n');print(path)


if __name__=='__main__':main()
