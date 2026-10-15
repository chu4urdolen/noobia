"""Audit diagnostic strings in the exact stock Wi-Fi character-driver module."""
import hashlib,json,time
from pathlib import Path
R=Path(__file__).resolve().parent.parent
p=R/'linux-port/artifacts/stock-cph2493-August-eu-ota/wifi-reference/vendor-dlkm-unpacked/lib/modules/wmt_chrdev_wifi_connac2.ko'
raw=p.read_bytes()
patterns=['WMT turn on WIFI fail!','Set p2p mode handler is NULL','Get %s net device timeout','Set wlan mode fail','Wi-Fi is resetting','WIFI_write invalid param']
report={'phone_contacted':False,'module':str(p),'module_sha256':hashlib.sha256(raw).hexdigest(),'diagnostic_strings':{v:{'present':v.encode() in raw,'offset':raw.find(v.encode())} for v in patterns},'limits':'String presence in exact stock module; source reference does not establish every compiled control path.'}
out=R/'linux-port/docs'/('station-error-string-audit-'+str(time.time_ns())+'.json')
out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'receipt':str(out),**report},indent=2))
assert all(r['present'] for r in report['diagnostic_strings'].values())
