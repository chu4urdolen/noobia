"""Compare actual initramfs suppliers with the UFS power-domain requirement."""
import gzip,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;P=ROOT/'linux-port'
sys.path.insert(0,str(P))
from image_formats import read_boot_v4,read_newc
from ramdisk_codec import decompress
def main():
    F=P/'artifacts/busybox-timeout-site-v1'
    boot=read_boot_v4((F/'nord3-busybox-candidate.img').read_bytes());entries=read_newc(decompress(boot['ramdisk']))
    base=entries['etc/lynx/bootstrap-base-modules.load']['data'].decode().splitlines()
    storage=entries['etc/lynx/bootstrap-storage-modules.load']['data'].decode().splitlines()
    needed=['mtk-scpsys.ko','mtk-scpsys-mt6983.ko']
    message=b'deferred probe timeout, ignoring dependency'
    report={'phone_contacted':False,'candidate_sha256':hashlib.sha256((F/'nord3-busybox-candidate.img').read_bytes()).hexdigest(),
            'base_modules':base,'storage_modules':storage,
            'power_provider_modules':needed,'missing_from_load_lists':[name for name in needed if name not in base+storage],
            'missing_from_first_stage':[name for name in needed if 'lib/modules/'+name not in entries],
            'exact_stock_deferred_timeout_literal':message in gzip.decompress(boot['kernel']),
            'published_pm_path':'genpd provider lookup failure calls driver_deferred_probe_check_state; when timeout=0 and initcalls_done, returns -110 and emits the verified warning.',
            'limits':'Concrete missing module inventory and source-based hypothesis. Runtime provider binding and actual warning remain to be proven.'}
    path=P/'docs/missing-ufs-power-provider.json';path.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
