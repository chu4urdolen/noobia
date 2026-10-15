"""Retain primary local Git sources for analysis, without a phone connection."""
import hashlib,json,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
P=ROOT/'linux-port';REPO=P/'sources/kernel-mt6983';OUT=P/'docs/wifi-source-reference'
FILES={'drivers/scsi/ufs/ufshcd.c':'ufshcd.c','drivers/scsi/ufs/ufshcd-pltfrm.c':'ufshcd-pltfrm.c',
       'include/trace/events/ufs.h':'trace-ufs.h','include/trace/events/power.h':'trace-power.h',
       'drivers/phy/mediatek/phy-mtk-ufs.c':'phy-mtk-ufs.c',
       'include/linux/device/driver.h':'device-driver.h','drivers/base/platform.c':'platform.c','drivers/base/dd.c':'driver-dd.c',
       'drivers/clk/clk-conf.c':'clk-conf.c','drivers/soc/mediatek/mtk-scpsys-mt6983.c':'mtk-scpsys-mt6983.c',
       'drivers/soc/mediatek/mtk-scpsys.c':'mtk-scpsys.c'}


def main():
    revision=subprocess.run(['git','-C',str(REPO),'rev-parse','HEAD'],capture_output=True,text=True,check=True).stdout.strip()
    assert revision=='81ec42ad5e803be0cba619f9f7bb298db7d33d7b','Published reference changed'
    rows=[]
    for name,destination in FILES.items():
        raw=subprocess.run(['git','-C',str(REPO),'show','HEAD:'+name],capture_output=True,check=True).stdout
        path=OUT/destination;assert not path.exists() or path.read_bytes()==raw,'Preserve earlier reference'
        path.write_bytes(raw);rows.append({'source':name,'saved':str(path),'sha256':hashlib.sha256(raw).hexdigest()})
    report={'published_revision':revision,'files':rows,'phone_contacted':False,'limits':'Published reference, not exact stock build commit.'}
    path=P/'docs/binding-sources.json';path.write_text(json.dumps(report,indent=2)+'\n');print(path)


if __name__=='__main__':main()
