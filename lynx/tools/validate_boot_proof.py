"""Independent fixed-image proof checks and AOSP AVB policy model; no USB."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parent.parent
PROJECT=ROOT/'linux-port'
sys.path.insert(0,str(PROJECT))
from image_formats import read_boot_v4,read_newc,require
from ramdisk_codec import decompress

def main():
    directory=PROJECT/'artifacts/busybox-August-boot-proof-bound-guards'
    stock=PROJECT/'artifacts/stock-cph2493-August-eu-ota'
    image=(directory/'nord3-busybox-candidate.img').read_bytes()
    digest=hashlib.sha256(image).hexdigest()
    require(digest=='a9a72334185a5ddec9b6e3ece6e9e01600582f62c4db7bebc8ce87c4d5c3fe43','Fixed proof image changed')
    original=(stock/'boot.img').read_bytes()
    require(hashlib.sha256(original).hexdigest()=='a67f03d7b826b834c23653b67eaa6efa971eb70ef8af19eee4d33fb5fc7fe995','Stock undo image changed')
    boot=read_boot_v4(image)
    require(boot['kernel']==read_boot_v4(original)['kernel'],'Kernel differs from matching stock')
    entries=read_newc(decompress(boot['ramdisk']))
    vendor=read_newc(decompress((stock/'unpacked-vendor-boot/vendor_ramdisk00').read_bytes()))
    combined={**vendor,**entries}
    require(combined['init']['data']==(PROJECT/'init-boot-proof').read_bytes(),'Native init differs from preserved source')
    require(combined['bin/boot-proof-reboot']['data']==(PROJECT/'artifacts/boot-proof-reboot.elf').read_bytes(),'Reboot helper changed')
    for name in ['mtk_wdt.ko','reboot-mode.ko','syscon-reboot-mode.ko']:
        require(combined['lib/modules/'+name]['data']==(stock/'vendor-ramdisk-unpacked/lib/modules'/name).read_bytes(),'Module overlay differs from stock')
    vm=json.loads((PROJECT/'artifacts/emulated-boot-proof-guard-1791662599378418727/result.json').read_text())
    require(vm['candidate_sha256']==digest and vm['guard_stop_observed'] and not vm['kernel_reboot_command_observed'],'Exact-image negative VM test failed')
    helper=json.loads((PROJECT/'artifacts/emulated-reboot-helper-1791662465537639804/result.json').read_text())
    require(helper['kernel_reboot_command_observed'] and helper['exit_code']==0 and helper['helper_sha256']==hashlib.sha256(combined['bin/boot-proof-reboot']['data']).hexdigest(),'Positive helper VM test failed')
    fixtures=json.loads((ROOT/'tools/test-artifacts/boot-proof-guard-1791662566283189527/result.json').read_text())
    require(fixtures['init_source_sha256']==hashlib.sha256(combined['init']['data']).hexdigest() and all(x['passed'] for x in fixtures['cases']),'Source guard tests failed')
    model=ROOT/'tools/avb-host/avb-boot-model'
    reference=json.loads((PROJECT/'docs/avb-boot-model-results.json').read_text())
    require(hashlib.sha256(model.read_bytes()).hexdigest()==reference['binary_sha256'],'AVB model changed')
    cases=[]
    for unlocked in [1,0]:
        process=subprocess.run([str(model),str(stock),str(directory/'nord3-busybox-candidate.img'),'0',str(unlocked)],capture_output=True,text=True,timeout=20)
        require(process.returncode==0,'AVB model failed')
        result=json.loads(process.stdout);result.update(unlocked=bool(unlocked),diagnostics=process.stderr)
        cases.append(result)
    require(cases[0]['slot_data_returned'] and cases[0]['boot_partitions_loaded']==1 and not cases[1]['slot_data_returned'],'Unexpected modeled AVB policy')
    report=dict(phone_contacted=False,candidate_sha256=digest,independent_checks_passed=True,
                cases=cases,hardware_boot_proven=False,controlled_trial_ready=True,
                limits='AOSP AVB is not the proprietary OnePlus bootloader; QEMU has no MT6983 hardware. Controlled boot_a-only trial relies on prior user authorization and verified stock restore.')
    path=PROJECT/'docs/boot-proof-validation.json'
    path.write_text(json.dumps(report,indent=2)+'\n')
    print('Independent checks passed; receipt:',path)

if __name__=='__main__':main()
