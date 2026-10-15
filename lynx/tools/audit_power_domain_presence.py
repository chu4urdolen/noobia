"""Check whether stock-kernel domain directories can support a read-only query."""
import hashlib,json,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';D=P/'docs/wifi-source-reference';repo=P/'sources/kernel-mt6983'
raw=subprocess.check_output(['git','-C',str(repo),'show','HEAD:drivers/base/power/domain.c']);(D/'genpd-domain.c').write_bytes(raw)
text=raw.decode();cfg=(P/'artifacts/stock-cph2493-August-eu-ota/kernel-config.txt').read_text();driver=(D/'mtk-scpsys-mt6983.c').read_text()
sys.path.insert(0,str(P))
from image_formats import elf64
module=(P/'artifacts/stock-cph2493-August-eu-ota/vendor-ramdisk-unpacked/lib/modules/mtk-scpsys-mt6983.ko').read_bytes()
rodata=b''.join(data for name,data in elf64(module)['sections'].items() if 'rodata' in name)
checks={'debugfs_enabled':'CONFIG_DEBUG_FS=y\n' in cfg,'generic_domains_enabled':'CONFIG_PM_GENERIC_DOMAINS=y\n' in cfg,'genpd_debug_add_exists':'genpd_debug_add' in text,'runtime_domain_init_adds_debugfs':'genpd_debug_add(genpd);' in text.split('int pm_genpd_init')[1].split('EXPORT_SYMBOL_GPL(pm_genpd_init)')[0],'ufs_domain_name_known':'.name = "ufs0"' in driver,'stock_controller_name_known':'.name = "mtk-scpsys-mt6983"' in driver,'exact_stock_ufs_name':b'ufs0\0' in rodata,'exact_stock_controller_name':b'mtk-scpsys-mt6983\0' in rodata}
report={'passed':all(checks.values()),'checks':checks,'genpd_source_sha256':hashlib.sha256(raw).hexdigest(),'published_revision':subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip(),'phone_contacted':False,'limits':'Source differs from exact stock build commit. Driver symlink and debugfs directory presence support binding/domain-object registration, not successful power-on or independently verified onecell provider registration.'}
out=P/'docs/power-domain-presence-audit.json';out.write_text(json.dumps(report,indent=2)+'\n');print(out);assert report['passed']
