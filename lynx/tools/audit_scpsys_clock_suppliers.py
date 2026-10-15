"""Resolve all clock suppliers used while registering stock MT6983 domains."""
import fnmatch,hashlib,json,re,struct,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;P=ROOT/'linux-port';S=P/'artifacts/stock-cph2493-August-eu-ota'
sys.path.insert(0,str(P))
from audit_ufs_reset_supplier import fdt_nodes
from image_formats import module_metadata
from stock_of_match_tables import of_match_tables
def main():
    dt=P/'artifacts/stock-runtime-dtb-overlay5/stock-merged.dtb';nodes=fdt_nodes(dt.read_bytes())
    handles={int.from_bytes(props['phandle'],'big'):name for name,props in nodes.items() if 'phandle' in props}
    power_cells=struct.unpack('>II',nodes['/ufshci@112b0000']['power-domains'])
    path=handles[power_cells[0]];props=nodes[path]
    names=props.get('clock-names',b'').rstrip(b'\0').decode().split('\0')
    cells=list(struct.unpack('>'+str(len(props.get('clocks',b''))//4)+'I',props.get('clocks',b'')))
    binaries={f.name:f.read_bytes() for f in (S/'vendor-ramdisk-unpacked/lib/modules').glob('*.ko')}
    aliases={name:module_metadata(raw)['values'].get('alias',[]) for name,raw in binaries.items()}
    tables={name:of_match_tables(raw) for name,raw in binaries.items()}
    boot=json.loads((P/'artifacts/busybox-timeout-site-v1/build-validation.json').read_text());loaded=set(boot['base_modules']+boot['storage_modules'])
    source=(P/'docs/wifi-source-reference/mtk-scpsys-mt6983.c').read_text()
    prefixes=set(re.findall(r'\.subsys(?:_lp)?_clk_prefix\s*=\s*"([^"]+)"',source))
    basic=set()
    for group in re.findall(r'\.basic(?:_lp)?_clk_name\s*=\s*\{([^}]+)\}',source):basic.update(re.findall(r'"([^"]+)"',group))
    rows=[];index=0
    for clock_name in names:
        provider=handles[cells[index]];pp=nodes[provider];count=int.from_bytes(pp.get('#clock-cells',b''),'big')
        compat=pp.get('compatible',b'').rstrip(b'\0').decode().split('\0')
        matches=sorted(name for name,patterns in aliases.items() if any(fnmatch.fnmatchcase('of:NproviderT*C'+c,pattern) or fnmatch.fnmatchcase('of:NproviderT*C'+c+'C',pattern) for c in compat for pattern in patterns if pattern.startswith('of:')))
        table_matches=sorted(name for name,items in tables.items() if any(set(compat)&set(table['compatibles']) for table in items))
        matches=sorted(set(matches+table_matches))
        literal_candidates=sorted(name for name,raw in binaries.items() if any(c and (c.encode()+b'\0') in raw for c in compat if c!='syscon'))
        used=clock_name in basic or any(clock_name.startswith(prefix+'-') for prefix in prefixes)
        rows.append({'clock_name':clock_name,'required_by_published_init':used,'provider':provider,'compatible':compat,'specifier':cells[index+1:index+1+count],'matching_modules':matches,'compatible_literal_candidates':literal_candidates,'literal_candidates_not_in_bootstrap':sorted(set(literal_candidates)-loaded),'not_in_bootstrap':sorted(set(matches)-loaded)})
        index+=1+count
    assert index==len(cells)
    missing=sorted(set(name for row in rows if row['required_by_published_init'] for name in row['not_in_bootstrap']))
    report={'phone_contacted':False,'dtb_sha256':hashlib.sha256(dt.read_bytes()).hexdigest(),'power_provider':path,'ufs_domain_id':power_cells[1],'clock_supplier_rows':rows,'missing_supplier_modules':missing,'unresolved_alias_rows':[row['clock_name'] for row in rows if row['required_by_published_init'] and not row['matching_modules']], 'exact_stock_of_tables':{name:items for name,items in tables.items() if items and name in set(m for row in rows for m in row['matching_modules'])},
            'limits':'Exact stock offline DT plus published init_scp logic; requires runtime proof that missing suppliers prevent provider registration. No additional modules loaded.'}
    out=P/'docs/scpsys-clock-suppliers.json';out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'report':str(out),'power_provider':path,'clock_count':len(rows),'missing_supplier_modules':missing,'first_missing_rows':[row for row in rows if row['required_by_published_init'] and row['not_in_bootstrap']][:5]},indent=2))
if __name__=='__main__':main()
