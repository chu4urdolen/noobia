"""Review initcall/pstore support and decode saved VM journals honestly."""
import hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;P=ROOT/'linux-port'
from lynx_decode_stages import decode
sys.path.insert(0,str(P))
from audit_ufs_reset_supplier import fdt_nodes
def main():
    repo=P/'sources/kernel-mt6983';sources=[]
    for source,name in [('init/main.c','init-main.c'),('kernel/module.c','kernel-module.c'),('fs/pstore/ram.c','pstore-ram.c'),('fs/pstore/platform.c','pstore-platform.c')]:
        result=subprocess.run(['git','-C',str(repo),'show','81ec42ad5e803be0cba619f9f7bb298db7d33d7b:'+source],capture_output=True)
        if result.returncode:sources.append({'source':source,'error':result.stderr.decode(errors='replace')});continue
        path=P/'docs/wifi-source-reference'/name;assert not path.exists() or path.read_bytes()==result.stdout
        path.write_bytes(result.stdout);sources.append({'source':source,'saved':str(path),'sha256':hashlib.sha256(result.stdout).hexdigest()})
    build=json.loads((P/'artifacts/busybox-wifi-ssh-twostage-v5/build-validation.json').read_text())
    vm=P/'artifacts/emulated-wifi-v5-journals-1791923373163479790';journals={}
    for owner in ['bootstrap','wifi','supervisor']:
        source=vm/(owner+'.hex');result=decode(source.read_bytes(),build['session_token'])
        for record in result['records']:record['stage']=build['diagnostic_codebook'].get(str(int(record['stage_hex'],16)),record['stage'])
        result.update(origin='stock-kernel ARM64 VM fixture; not retrieved from Lynx',capture=str(source));journals[owner]=result
    dt=P/'artifacts/stock-runtime-dtb-overlay5/stock-merged.dtb'
    nodes=fdt_nodes(dt.read_bytes());backends=[]
    for path,props in nodes.items():
        compatible=props.get('compatible',b'')
        if any(word in compatible.lower() or word in path.lower().encode() for word in [b'ramoops',b'pstore']):
            backends.append({'path':path,'compatible':compatible.rstrip(b'\0').decode(errors='replace').split('\0'),'reg_hex':props.get('reg',b'').hex(),'properties':sorted(props)})
    report={'phone_contacted':False,'handset_hex_records_retrieved':False,'saved_vm_hex_decoded':journals,'pstore_dt_nodes':backends,'primary_sources':sources,'limits':'VM captures establish logger/decoder behavior only. No new pstore read, BootROM operation, persistent partition write or hardware reboot.'}
    out=P/'docs/hex-and-initcall-review.json';out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'report':str(out),'journal_validity':{name:result['complete_sequences_and_checksums'] for name,result in journals.items()},'record_counts':{name:len(result['records']) for name,result in journals.items()},'pstore_dt_nodes':backends},indent=2))
if __name__=='__main__':main()
