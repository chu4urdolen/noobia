"""Preserve pinned OnePlus primary sources for offline thermal probe review."""
import concurrent.futures,hashlib,json,time,urllib.request
from pathlib import Path
R=Path(__file__).resolve().parent.parent
COMMIT='81ec42ad5e803be0cba619f9f7bb298db7d33d7b'
PATHS=['drivers/thermal/mediatek/soc_temp_lvts.c','drivers/thermal/mediatek/soc_temp_lvts.h','drivers/cpufreq/mediatek-cpufreq-hw.c','drivers/nvmem/mtk-devinfo.c']
def main():
 out=R/'linux-port/docs'/('thermal-probe-sources-'+str(time.time_ns()));out.mkdir(mode=0o700)
 def fetch(path):
  url='https://raw.githubusercontent.com/OnePlusOSS/android_kernel_5.10_oneplus_mt6983/'+COMMIT+'/'+path
  row={'path':path,'url':url}
  try:
   with urllib.request.urlopen(url,timeout=20) as response:data=response.read(4*1024*1024)
   destination=out/Path(path).name;destination.write_bytes(data);row.update(bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),file=str(destination),state='saved')
  except Exception as error:row.update(state='failed',error=str(error))
  return row
 with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:rows=list(pool.map(fetch,PATHS))
 (out/'manifest.json').write_text(json.dumps({'commit':COMMIT,'sources':rows,'phone_contacted':False,'limits':'Published source reference; exact OEM module binary provenance is not independently established.'},indent=2)+'\n');print(json.dumps(rows,indent=2))
if __name__=='__main__':main()
