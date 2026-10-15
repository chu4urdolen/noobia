"""Verify proposed inner-power diagnostic literals against the exact stock modules."""
import hashlib,json,time
from pathlib import Path
R=Path(__file__).resolve().parent.parent
P=R/'linux-port'
D=P/'artifacts/stock-cph2493-August-eu-ota/wifi-reference/vendor-dlkm-unpacked/lib/modules'
checks={}
for name,literals in {
    'wmt_chrdev_wifi_connac2.ko':['WiFi on/off takes more than %d seconds','Invalid pointer','WMT turn on WIFI fail!'],
    'wlan_drv_gen4m_6983.ko':['wlanProbe: probe failed, reason:%d'],
}.items():
    f=D/name
    if not f.exists():
        raise ValueError('Expected exact stock module missing: '+str(f))
    raw=f.read_bytes()
    checks[name]={'sha256':hashlib.sha256(raw).hexdigest(),'literals':{s:s.encode() in raw for s in literals}}
passed=all(all(v['literals'].values()) for v in checks.values())
out=P/'docs'/('power-error-string-audit-'+str(time.time_ns())+'.json')
out.write_text(json.dumps({'passed':passed,'modules':checks,'phone_contacted':False,'limits':'Literal presence does not prove execution. Numeric reason labels use reference source, not independently matched binary enum semantics.'},indent=2)+'\n')
print(out)
if not passed:raise SystemExit(1)
