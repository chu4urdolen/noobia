"""Check diagnostic literals against the exact stock kernel/module binaries."""
import gzip,hashlib,json,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent;P=ROOT/'linux-port';S=P/'artifacts/stock-cph2493-August-eu-ota'
sys.path.insert(0,str(P))
from image_formats import read_boot_v4,require


def main():
    kernel=read_boot_v4((S/'boot.img').read_bytes())['kernel']
    require(hashlib.sha256(kernel).hexdigest()=='cbc9f5dc54b5198ddd1e82d5d7bde96f43cbb383a663726ddd68919b0639d3af','Stock kernel changed')
    image=gzip.decompress(kernel);scpsys=(S/'vendor-ramdisk-unpacked/lib/modules/mtk-scpsys.ko').read_bytes()
    soc=(S/'vendor-ramdisk-unpacked/lib/modules/mtk-scpsys-mt6983.ko').read_bytes()
    literals={'power_mtcmos':(scpsys,b'Failed to power on mtcmos %s(%d)'),
              'power_sram_bus':(scpsys,b'Failed to power on sram/bus %s(%d)'),
              'host_enable':(image,b'Host controller enable failed'),
              'controller_enable':(image,b'Controller enable failed'),
              'link_startup':(image,b'link startup failed %d'),
              'uic_completion':(image,b'uic cmd 0x%x with arg3 0x%x completion timeout')}
    present={name:needle in raw for name,(raw,needle) in literals.items()}
    require(all(present.values()),'A proposed diagnostic literal is absent from exact stock binary')
    require(b'ufs0\0' in soc,'Expected power-domain name absent from stock SoC module')
    report={'passed':True,'message_literals_present':present,'power_domain_name':'ufs0',
            'scpsys_sha256':hashlib.sha256(scpsys).hexdigest(),'soc_sha256':hashlib.sha256(soc).hexdigest(),
            'kernel_sha256':hashlib.sha256(kernel).hexdigest(),'phone_contacted':False,
            'limits':'Exact compiled literals verified; does not prove they were emitted or retained on the handset.'}
    path=P/'docs/timeout-message-audit.json';path.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
