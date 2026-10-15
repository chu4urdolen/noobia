"""Check error cascades, target filtering and every valid six-bit mask."""
import hashlib,json,subprocess,time
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent;SOURCE=ROOT/'linux-port/lynx-classify-timeout-sites.awk'


def main():
    out=ROOT/'tools/test-artifacts'/('timeout-site-classifier-'+str(time.time_ns()));out.mkdir()
    messages=['ufshcd-mtk 112b0000.ufshci: probe failed -110',
              'scpsys: Failed to enable lp_clk ufs0(-110)',
              'ufshcd-mtk 112b0000.ufshci: Initialization failed',
              'ufshcd-mtk 112b0000.ufshci: ufshcd_init: variant mediatek init failed err -110',
              'ufshcd-mtk 112b0000.ufshci: regulator init failed -110',
              'ufshcd-mtk 112b0000.ufshci: ufshcd_setup_clocks: core_clk enable failed, err=-110']
    specs=[]
    for selection in range(64):
        raw='\n'.join('[ 3.2][ T1] '+text for n,text in enumerate(messages) if selection & (1<<n))+'\n'
        specs.append(('selection-'+str(selection),raw,selection))
    specs += [('unrelated','other-device: probe failed -110\nscpsys: Failed to enable lp_clk gpu(-110)\n',0),
              ('wrong-errno','scpsys: Failed to enable lp_clk ufs0(-5)\n',0),
              ('power-clk-args','scpsys: Failed to enable clk ufs0(-110 1)\n',2),
              ('cascaded',messages[0]+'\n'+messages[2]+'\n',5)]
    cases=[]
    for name,raw,expected in specs:
        path=out/(name+'.log');path.write_text(raw)
        result=subprocess.run(['awk','-v','expected_device=112b0000.ufshci','-v','expected_domain=ufs0','-f',str(SOURCE)],input=raw,text=True,capture_output=True,check=True)
        assert int(result.stdout)==expected,(name,result.stdout);(out/(name+'.output')).write_text(result.stdout)
        cases.append({'case':name,'fixture':str(path),'expected_code':expected,'expected_device':'112b0000.ufshci','registration_failed':0})
    report={'passed':True,'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'cases':cases,'phone_contacted':False}
    path=out/'result.json';path.write_text(json.dumps(report,indent=2)+'\n');print(path)


if __name__=='__main__':main()
