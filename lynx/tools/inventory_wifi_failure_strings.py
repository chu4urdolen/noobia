"""Save exact stock diagnostic literals for offline source review; no phone I/O."""
import hashlib,json,re,time
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port'
D=P/'artifacts/stock-cph2493-August-eu-ota/wifi-reference/vendor-dlkm-unpacked/lib/modules'
modules={}
for name in ['conninfra.ko','wmt_chrdev_wifi_connac2.ko','wlan_drv_gen4m_6983.ko']:
    raw=(D/name).read_bytes()
    literals=sorted(set(s.decode() for s in re.findall(rb'[\x20-\x7e]{8,}',raw) if re.search(rb'fail|error|timeout|timed out|firmware|Invalid pointer|probe|power on|pwr_on|patch',s,re.I)))
    modules[name]={'sha256':hashlib.sha256(raw).hexdigest(),'strings':literals,'count':len(literals)}
out=P/'docs'/('wifi-failure-literal-inventory-'+str(time.time_ns())+'.json')
out.write_text(json.dumps({'phone_contacted':False,'modules':modules,'limits':'Printable runs from exact ELF files; presence alone is neither execution evidence nor a source match.'},indent=2)+'\n')
print(json.dumps({'report':str(out),'counts':{k:v['count'] for k,v in modules.items()}},indent=2))
