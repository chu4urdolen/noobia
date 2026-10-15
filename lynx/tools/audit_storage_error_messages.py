"""Retain relevant exact-stock printk literals for offline timeout analysis."""
import gzip,hashlib,json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;P=ROOT/'linux-port';S=P/'artifacts/stock-cph2493-August-eu-ota'
sys.path.insert(0,str(P))
from image_formats import read_boot_v4

def main():
    kernel=read_boot_v4((S/'boot.img').read_bytes())['kernel']
    files={'stock-kernel':gzip.decompress(kernel)}
    for name in ['mtk-scpsys','mtk-scpsys-mt6983','ufs-mediatek-mod','phy-mtk-ufs','mt6363-regulator','clk-mt6983']:
        files[name]=(S/'vendor-ramdisk-unpacked/lib/modules'/(name+'.ko')).read_bytes()
    rows={}
    for name,raw in files.items():
        candidates=set(m.group().decode('ascii') for m in re.finditer(rb'[\x20-\x7e]{8,}',raw))
        # Include source function format strings as well as explicit UFS text.
        chosen=sorted(text for text in candidates if any(word in text.lower() for word in ['timeout','timed out','failed','fail ']) and (name!='stock-kernel' or any(word in text.lower() for word in ['ufs','uic','controller','variant','clock','regulator','probe','power domain','pm domain'])))
        rows[name]={'binary_sha256':hashlib.sha256(raw).hexdigest(),'messages':chosen}
    path=P/'docs/stock-storage-error-messages.json'
    path.write_text(json.dumps({'phone_contacted':False,'kernel_gzip_sha256':hashlib.sha256(kernel).hexdigest(),'binaries':rows,'limits':'Compiled literals only; unrelated kernel messages included. Does not identify messages emitted on Lynx.'},indent=2)+'\n')
    print(path)
    for name in ['mtk-scpsys','ufs-mediatek-mod','phy-mtk-ufs']:
        print(name,json.dumps(rows[name]['messages']))

if __name__=='__main__':main()
