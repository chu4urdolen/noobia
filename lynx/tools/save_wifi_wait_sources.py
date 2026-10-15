"""Fetch pinned manufacturer reference sources, preserving hashes and failures."""
import hashlib,json,time,urllib.request
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port'
commit='b7485501b2c4e0abae154e44c3861bd0fc6d605a'
prefix='vendor/mediatek/kernel_modules/connectivity/'
paths={'axi.c':prefix+'wlan/core/gen4m/os/linux/hif/axi/axi.c','pre_cal.c':prefix+'wlan/core/gen4m/chips/common/pre_cal.c','conninfra_core.c':prefix+'conninfra/core/conninfra_core.c'}
out=P/'docs'/('wifi-wait-sources-'+str(time.time_ns()));out.mkdir(mode=0o700)
report={'commit':commit,'repository':'OnePlusOSS/android_kernel_modules_oneplus_mt6983','files':[],'phone_contacted':False,'limits':'Published reference sources; exact stock build provenance not independently established.'}
for name,path in paths.items():
    url='https://raw.githubusercontent.com/'+report['repository']+'/'+commit+'/'+path;entry={'url':url,'source_path':path,'started_ns':time.time_ns()};report['files'].append(entry)
    try:
        with urllib.request.urlopen(url,timeout=25) as response:
            data=response.read(1048577)
            if len(data)>1048576:raise ValueError('Source exceeds bounded read')
        f=out/name;f.write_bytes(data);entry.update(state='saved',file=str(f),sha256=hashlib.sha256(data).hexdigest(),bytes=len(data))
    except Exception as error:entry.update(state='failed',error=repr(error))
    entry['finished_ns']=time.time_ns();(out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
print(out/'manifest.json')
if any(e['state']!='saved' for e in report['files']):raise SystemExit(1)
