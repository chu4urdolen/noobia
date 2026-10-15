"""Fixed BusyBox-console image checks; no phone access."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parent.parent
PROJECT=ROOT/'linux-port'
sys.path.insert(0,str(PROJECT))
from image_formats import read_boot_v4,read_newc,module_metadata,require
from ramdisk_codec import decompress

def main():
    folder=PROJECT/'artifacts/busybox-August-busybox-console'
    expected='3c75e5791fa9ed6be1a655e978fac4c68b8ea1479ca4777b54106f51326572dc'
    report=json.loads((folder/'build-validation.json').read_text())
    image=(folder/'nord3-busybox-candidate.img').read_bytes()
    require(hashlib.sha256(image).hexdigest()==expected==report['candidate_sha256'],'Console image changed')
    stock=PROJECT/'artifacts/stock-cph2493-August-eu-ota'
    boot=read_boot_v4(image)
    require(boot['kernel']==read_boot_v4((stock/'boot.img').read_bytes())['kernel'],'Stock kernel mismatch')
    generic=read_newc(decompress(boot['ramdisk']))
    vendor=read_newc(decompress((stock/'unpacked-vendor-boot/vendor_ramdisk00').read_bytes()))
    combined={**vendor,**generic}
    require(generic['init']['data']==(folder/'init-source').read_bytes(),'Init source mismatch')
    require(b'LYNX_NATIVE_BUSYBOX_SHELL' in generic['init']['data'] and b'functions/ecm' not in generic['init']['data'],'Expected BusyBox ACM-only init')
    names=[]
    for item in report['modules']:
        data=combined['lib/modules/'+item['name']]['data']
        require(hashlib.sha256(data).hexdigest()==item['sha256'],'Stock module hash mismatch')
        require(module_metadata(data)['values']['scmversion']==['g311738fbb5a8'],'Stock module version mismatch')
        names.append(item['name'])
    require(len(names)==len(set(names))==37,'Unexpected module count')
    require(names.index('reboot-mode.ko')<names.index('syscon-reboot-mode.ko'),'Reset dependency order')
    require(names.index('xhci-mtk-hcd.ko')<names.index('mtu3.ko'),'Host dependency order')
    vm=json.loads((PROJECT/'artifacts/emulated-busybox-console-1791666814527661557/result.json').read_text())
    require(vm['candidate_sha256']==expected and vm['busybox_console_failure_guard_observed'] and not vm['kernel_reboot_command_observed'],'VM guard proof mismatch')
    model=ROOT/'tools/avb-host/avb-boot-model'
    ref=json.loads((PROJECT/'docs/avb-boot-model-results.json').read_text())
    require(hashlib.sha256(model.read_bytes()).hexdigest()==ref['binary_sha256'],'AVB model changed')
    cases=[]
    for unlocked in ['1','0']:
        process=subprocess.run([str(model),str(stock),str(folder/'nord3-busybox-candidate.img'),'0',unlocked],capture_output=True,text=True,timeout=20)
        require(process.returncode==0,'AVB model error')
        case=json.loads(process.stdout);case.update(unlocked=unlocked=='1',diagnostics=process.stderr);cases.append(case)
    require(cases[0]['slot_data_returned'] and cases[0]['boot_partitions_loaded']==1 and not cases[1]['slot_data_returned'],'Modeled AVB policy mismatch')
    output=PROJECT/'docs/busybox-console-validation.json'
    output.write_text(json.dumps(dict(candidate_sha256=expected,stock_kernel_identical=True,module_count=37,
                                     stock_module_hashes_checked=True,vm_failure_guard_passed=True,avb_policy_cases=cases,
                                     phone_contacted=False,hardware_console_proven=False),indent=2)+'\n')
    print('BusyBox console checks passed:',output)

if __name__=='__main__':main()
