"""Resolve UFS DMA and assigned-clock resources from the merged stock tree."""
import hashlib,json,struct,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent;P=ROOT/'linux-port'
sys.path.insert(0,str(ROOT/'tools'))
sys.path.insert(0,str(P))
from audit_ufs_reset_supplier import fdt_nodes
from image_formats import module_metadata


def main():
    dtb=P/'artifacts/stock-runtime-dtb-overlay5/stock-merged.dtb'
    nodes=fdt_nodes(dtb.read_bytes());props=nodes['/ufshci@112b0000']
    handles={int.from_bytes(p['phandle'],'big'):name for name,p in nodes.items() if 'phandle' in p}
    manifest=json.loads((P/'artifacts/busybox-wifi-ssh-twostage-v4/build-validation.json').read_text())
    loaded=set(manifest['base_modules']+manifest['storage_modules'])
    stock=P/'artifacts/stock-cph2493-August-eu-ota'
    paths=list((stock/'vendor-ramdisk-unpacked/lib/modules').glob('*.ko'))+list((stock/'wifi-reference/vendor-dlkm-unpacked/lib/modules').glob('*.ko'))
    edges=[]
    for key,cells_key in [('iommus','#iommu-cells'),('assigned-clocks','#clock-cells'),('assigned-clock-parents','#clock-cells')]:
        if key not in props:continue
        data=props[key];assert len(data)%4==0
        cells=struct.unpack('>'+str(len(data)//4)+'I',data);index=0
        while index<len(cells):
            if cells[index]==0:index+=1;continue
            provider=handles[cells[index]];provider_props=nodes[provider]
            count=int.from_bytes(provider_props.get(cells_key,b''),'big')
            compatibles=provider_props.get('compatible',b'').rstrip(b'\0').decode().split('\0')
            candidates=[]
            for path in paths:
                raw=path.read_bytes()
                if any(value.encode()+b'\0' in raw for value in compatibles if value):
                    metadata=module_metadata(raw)['values']
                    candidates.append({'file':str(path),'sha256':hashlib.sha256(raw).hexdigest(),'name':metadata.get('name'),
                                       'depends':metadata.get('depends'),'vermagic':metadata.get('vermagic'),'loaded_before_ufs':path.name in loaded})
            edges.append({'property':key,'provider':provider,'compatible':compatibles,'specifier':list(cells[index+1:index+1+count]),'module_candidates':candidates})
            index+=1+count
    report={'phone_contacted':False,'dtb_sha256':hashlib.sha256(dtb.read_bytes()).hexdigest(),'ufs_properties':sorted(props),
            'dma_coherent':'dma-coherent' in props,'resource_edges':edges,
            'limits':'Offline stock overlay5 reconstruction; bootloader runtime changes excluded. Compatible literals identify candidates, not proven live requirements or DMA failures.'}
    path=P/'docs/ufs-dma-requirements.json';path.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
