"""Inventory omitted stock startup modules and retain their primary sources."""
import hashlib,json,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';sys.path.insert(0,str(P))
from image_formats import module_metadata
from audit_ufs_reset_supplier import fdt_nodes
def main():
    repo=P/'sources/kernel-mt6983';stock=P/'artifacts/stock-cph2493-August-eu-ota'
    revision=subprocess.run(['git','-C',str(repo),'rev-parse','HEAD'],check=True,capture_output=True,text=True).stdout.strip()
    listing=subprocess.run(['git','-C',str(repo),'ls-tree','-r','--name-only','HEAD','drivers/clk/mediatek','drivers/soc/mediatek'],check=True,capture_output=True,text=True).stdout.splitlines()
    wanted=[name for name in listing if name.endswith('/clk-bringup.c') or name.endswith('/mtk-scpsys-bringup.c') or name.endswith('/clk-mt6983.c')]
    wanted.append('include/dt-bindings/clock/mt6983-clk.h')
    sources=[]
    for name in wanted:
        raw=subprocess.run(['git','-C',str(repo),'show','HEAD:'+name],check=True,capture_output=True).stdout
        out=P/'docs/wifi-source-reference'/('startup-'+Path(name).name)
        assert not out.exists() or out.read_bytes()==raw,'Preserve source'
        out.write_bytes(raw);sources.append(dict(source=name,file=str(out),sha256=hashlib.sha256(raw).hexdigest()))
    modules=[]
    for name in ['clk-bringup.ko','mtk-scpsys-bringup.ko','nvmem_mtk-devinfo.ko','clk-mt6983.ko']:
        raw=(stock/'vendor-ramdisk-unpacked/lib/modules'/name).read_bytes()
        modules.append(dict(file=name,sha256=hashlib.sha256(raw).hexdigest(),metadata=module_metadata(raw)['values']))
    dtb=(P/'artifacts/stock-runtime-dtb-overlay5/stock-merged.dtb').read_bytes();nodes=fdt_nodes(dtb)
    ufs=nodes['/ufshci@112b0000'];phandles={int.from_bytes(p['phandle'],'big'):(name,p) for name,p in nodes.items() if 'phandle' in p}
    clock_cells=[int.from_bytes(ufs['clocks'][i:i+4],'big') for i in range(0,len(ufs['clocks']),4)]
    clock_suppliers=[];index=0
    while index<len(clock_cells):
        name,props=phandles[clock_cells[index]];count=int.from_bytes(props.get('#clock-cells',b'\0\0\0\0'),'big')
        clock_suppliers.append(dict(node=name,compatible=props.get('compatible',b'').rstrip(b'\0').decode().split('\0'),specifier=clock_cells[index+1:index+1+count],status=props.get('status',b'okay\0').rstrip(b'\0').decode()))
        index+=1+count
    bringup_nodes=[]
    for name,props in nodes.items():
        compatible=props.get('compatible',b'').rstrip(b'\0').decode(errors='replace').split('\0')
        if not any(c in ['mediatek,clk-bring-up','mediatek,clk-post-ao','mediatek,scpsys-bringup','mediatek,scpsys-bring-up','mediatek,scpsys-post-ao'] for c in compatible):continue
        specs=[];cells=[int.from_bytes(props.get('clocks',b'')[i:i+4],'big') for i in range(0,len(props.get('clocks',b'')),4)];position=0
        while position<len(cells):
            supplier,sp=phandles[cells[position]];count=int.from_bytes(sp.get('#clock-cells',b'\0\0\0\0'),'big')
            specs.append(dict(supplier=supplier,specifier=cells[position+1:position+1+count]));position+=1+count
        parent=name.rsplit('/',1)[0]
        bringup_nodes.append(dict(node=name,compatible=compatible,status=props.get('status',b'okay\0').rstrip(b'\0').decode(),post_ao=props.get('mediatek,post_ao',b'').hex(),clock_property_sha256=hashlib.sha256(props.get('clocks',b'')).hexdigest(),clock_suppliers=specs,power_domains=props.get('power-domains',b'').hex(),parent_compatible=nodes.get(parent,{}).get('compatible',b'').hex()))
    report=dict(phone_contacted=False,published_revision=revision,sources=sources,modules=modules,ufs_dt_properties={k:v.hex() for k,v in ufs.items() if k in ['reg','resets','reset-names','power-domains','clocks','clock-names']},ufs_clock_names=ufs.get('clock-names',b'').rstrip(b'\0').decode().split('\0'),ufs_clock_suppliers=clock_suppliers,limits='Stock startup/source inventory and merged-DT clock specifiers; missing modules are not proven prerequisites and none are loaded by this audit. Published source is not the exact stock build.')
    report['bringup_nodes']=bringup_nodes
    out=P/'docs/ufs-stock-startup-audit.json';out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(report=str(out),sources=[r['source'] for r in sources],ufs_clock_names=report['ufs_clock_names'],ufs_clock_suppliers=clock_suppliers,bringup_nodes=bringup_nodes),indent=2))
if __name__=='__main__':main()
