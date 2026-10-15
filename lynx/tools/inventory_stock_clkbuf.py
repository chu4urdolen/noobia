"""Inspect the stock clock-buffer module and connectivity imports without phone contact."""
import hashlib,json,struct,sys,time
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';sys.path.insert(0,str(P))
from image_formats import elf64,module_metadata
from audit_ufs_reset_supplier import fdt_nodes
stock=P/'artifacts/stock-cph2493-August-eu-ota'
paths={'clkbuf':stock/'vendor-ramdisk-unpacked/lib/modules/clkbuf.ko','conninfra':stock/'wifi-reference/vendor-dlkm-unpacked/lib/modules/conninfra.ko'}
rows={}
for key,path in paths.items():
    raw=path.read_bytes();e=elf64(raw);meta=module_metadata(raw)['values']
    versions=[]
    for crc,name in struct.iter_unpack('<Q56s',e['sections'].get('__versions',b'')):
        symbol=name.split(b'\0')[0].decode()
        if any(word in symbol.lower() for word in ['clk_buf','clkbuf','symbol_get','pmic','scmi']):versions.append({'symbol':symbol,'crc':hex(crc)})
    table=e['sections']['.symtab'];names=e['sections']['.strtab'];syms=[]
    for offset in range(0,len(table),24):
        index,info,other,section,value,size=struct.unpack_from('<IBBHQQ',table,offset);name=names[index:names.index(b'\0',index)].decode()
        if any(word in name.lower() for word in ['of_match','of_device','clkbuf_id','clk_buf_ctrl','clk_buf_hw_ctrl','register_clk']):syms.append({'name':name,'size':size,'section':section})
    rows[key]={'file':str(path),'sha256':hashlib.sha256(raw).hexdigest(),'metadata':meta,'selected_imports':versions,'selected_symbols':syms}
nodes=fdt_nodes((P/'artifacts/stock-runtime-dtb-overlay5/stock-merged.dtb').read_bytes())
targets={name:{k:(v.decode(errors='replace').replace('\0','|') if k in ['compatible','status'] else v.hex()) for k,v in props.items()} for name,props in nodes.items() if 'clkbuf' in name.lower() or any(b'clkbuf' in c.lower() or b'clock_buffer' in c.lower() or b'srclken-rc' in c.lower() for c in props.get('compatible',b'').split(b'\0'))}
report={'phone_contacted':False,'modules':rows,'dt_clock_buffer_nodes':targets,'limits':'Preliminary inventory, not load eligibility or runtime success.'}
out=P/'docs'/('clkbuf-inventory-'+str(time.time_ns())+'.json');out.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'receipt':str(out),**report},indent=2))
