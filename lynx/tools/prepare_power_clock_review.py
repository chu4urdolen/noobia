"""Prepare independent native module test and retain primary review sources."""
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;P=ROOT/'linux-port';T=ROOT/'tools'
def main():
    target=T/'test_native_power_clocks.py';assert not target.exists()
    native=(T/'test_native_driver_trace.py').read_text()
    marker="    put(entries,'init',init)";assert native.count(marker)==1
    injection='''    clock_names=['clk-common.ko']+json.loads((P/'docs/scpsys-clock-suppliers.json').read_text())['missing_supplier_modules']
    clock_hashes={};commands=b''
    for name in clock_names:
        data=(P/'artifacts/stock-cph2493-August-eu-ota/vendor-ramdisk-unpacked/lib/modules'/name).read_bytes()
        put(entries,'lib/modules/'+name,data,0o100644);clock_hashes[name]=hashlib.sha256(data).hexdigest()
        commands+=(f"$BB insmod /lib/modules/{name}\\nprintf 'CLOCK_LOAD_{name}=%s\\\\n' \\\"$?\\\"\\n").encode()
    init=init.replace(b'echo TRACE_VM_INIT_ENTERED\\n',b'echo TRACE_VM_INIT_ENTERED\\n'+commands,1)
'''
    native=native.replace(marker,injection+marker,1)
    marker="    passed=code==0 and all(checks.values())"
    native=native.replace(marker,"    for name in clock_names:\n        checks['clock_load_'+name]=('CLOCK_LOAD_'+name+'=0').encode() in raw\n"+marker,1)
    native=native.replace("'passed':passed,'checks':checks","'clock_module_sha256':clock_hashes,'passed':passed,'checks':checks",1)
    native=native.replace('emulated-native-driver-trace-','emulated-native-power-clocks-')
    target.write_text(native)
    repo=P/'sources/kernel-mt6983';revision=subprocess.run(['git','-C',str(repo),'rev-parse','HEAD'],capture_output=True,text=True,check=True).stdout.strip()
    assert revision=='81ec42ad5e803be0cba619f9f7bb298db7d33d7b'
    sources={f'drivers/clk/mediatek/clk-mt6983-{name}.c':f'clk-mt6983-{name}.c' for name in ['cam','img','mdp_grp','mm','vcodec']}
    sources.update({'drivers/clk/mediatek/clk-mtk.c':'clk-mtk.c','drivers/clk/mediatek/clk-gate.c':'clk-gate.c','drivers/clk/mediatek/clk-mtk.h':'clk-mtk.h'})
    rows=[]
    for source,destination in sources.items():
        result=subprocess.run(['git','-C',str(repo),'show','HEAD:'+source],capture_output=True)
        if result.returncode:
            rows.append({'source':source,'error':result.stderr.decode(errors='replace')});continue
        path=P/'docs/wifi-source-reference'/destination;assert not path.exists() or path.read_bytes()==result.stdout
        path.write_bytes(result.stdout);rows.append({'source':source,'saved':str(path),'sha256':hashlib.sha256(result.stdout).hexdigest()})
    out=P/'docs/power-clock-review-sources.json';out.write_text(json.dumps({'published_revision':revision,'files':rows,'phone_contacted':False,'limits':'Published source, not exact stock build commit.'},indent=2)+'\n');print(out)
if __name__=='__main__':main()
