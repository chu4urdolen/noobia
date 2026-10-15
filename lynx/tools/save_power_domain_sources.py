"""Retain published PM-domain primary sources; never contacts the handset."""
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;P=ROOT/'linux-port';REPO=P/'sources/kernel-mt6983'
def main():
    revision=subprocess.run(['git','-C',str(REPO),'rev-parse','HEAD'],capture_output=True,text=True,check=True).stdout.strip()
    assert revision=='81ec42ad5e803be0cba619f9f7bb298db7d33d7b'
    rows=[]
    for source,name in [('drivers/base/power/common.c','pm-common.c'),('drivers/base/power/domain.c','pm-domain.c'),('include/linux/pm_domain.h','pm-domain.h')]:
        raw=subprocess.run(['git','-C',str(REPO),'show','HEAD:'+source],capture_output=True,check=True).stdout
        path=P/'docs/wifi-source-reference'/name
        assert not path.exists() or path.read_bytes()==raw
        path.write_bytes(raw);rows.append({'source':source,'saved':str(path),'sha256':hashlib.sha256(raw).hexdigest()})
    path=P/'docs/power-domain-sources.json';path.write_text(json.dumps({'published_revision':revision,'files':rows,'phone_contacted':False,'limits':'Published source, not exact stock build commit.'},indent=2)+'\n');print(path)
if __name__=='__main__':main()
