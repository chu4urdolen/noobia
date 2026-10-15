"""Preserve primary stock power-management sources; no handset access."""
import concurrent.futures,hashlib,json,time,urllib.request
from pathlib import Path
R=Path(__file__).resolve().parent.parent;COMMIT='81ec42ad5e803be0cba619f9f7bb298db7d33d7b';MODULE_COMMIT='b7485501b2c4e0abae154e44c3861bd0fc6d605a'
PATHS=[('android_kernel_5.10_oneplus_mt6983',COMMIT,p) for p in ['drivers/power/supply/mt6375-gauge.c','drivers/thermal/thermal-generic-adc.c']]+[('android_kernel_modules_oneplus_mt6983',MODULE_COMMIT,p) for p in ['vendor/oplus/kernel/cpu/oplus_omrg/oplus_omrg.c','vendor/oplus/kernel/thermal/oplus_omrg/oplus_omrg.c','vendor/oplus/kernel/charger/charger_ic/oplus_battery_mtk6983S.c','vendor/oplus/kernel/charger/gauge_ic/oplus_bq27541.c','vendor/oplus/kernel/charger/Makefile']]
def main():
 out=R/'linux-port/docs'/('power-management-sources-'+str(time.time_ns()));out.mkdir(mode=0o700)
 def fetch(spec):
  repo,commit,path=spec;url='https://raw.githubusercontent.com/OnePlusOSS/'+repo+'/'+commit+'/'+path;row={'path':path,'url':url,'commit':commit}
  try:
   with urllib.request.urlopen(url,timeout=15) as response:data=response.read(4*1024*1024)
   f=out/(path.replace('/','__'));f.write_bytes(data);row.update(state='saved',bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),file=str(f))
  except Exception as error:row.update(state='failed',error=str(error))
  return row
 with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:rows=list(pool.map(fetch,PATHS))
 (out/'manifest.json').write_text(json.dumps({'commit':COMMIT,'sources':rows,'phone_contacted':False,'limits':'Published reference; exact OEM binary provenance not independently established.'},indent=2)+'\n');print(json.dumps(rows,indent=2))
if __name__=='__main__':main()
