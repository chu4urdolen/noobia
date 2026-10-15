"""Independent storage-only image comparison; no handset access."""
import hashlib
import json
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
P = ROOT/'linux-port'
sys.path.insert(0,str(P))
from image_formats import read_boot_v4, read_newc, require
from ramdisk_codec import decompress
F = P/'artifacts/busybox-storage-outcome-v1'
SHA = '85d219fd6625897638ef70ee9abd9959cbf625f0063cecf19905a70f03b5e358'


def main():
    validation = subprocess.run(['python3',str(ROOT/'tools/validate_wifi_v4_image.py')],capture_output=True,text=True,timeout=30)
    require(validation.returncode == 0, 'Original v4 validation failed: '+validation.stdout+validation.stderr)
    image = (F/'nord3-busybox-candidate.img').read_bytes()
    require(hashlib.sha256(image).hexdigest() == SHA and len(image) == 67108864, 'Storage image changed')
    reference = (P/'artifacts/busybox-wifi-ssh-twostage-v4/nord3-busybox-candidate.img').read_bytes()
    boot, previous = read_boot_v4(image),read_boot_v4(reference)
    require(boot['kernel'] == previous['kernel'], 'Kernel changed')
    require(image[:12] == reference[:12] and image[16:4096] == reference[16:4096], 'Unrelated header change')
    entries, original = read_newc(decompress(boot['ramdisk'])),read_newc(decompress(previous['ramdisk']))
    require(set(entries) == set(original), 'Unexpected first-stage files')
    for name in entries:
        if name not in ['init','etc/lynx/session-token']:
            require(entries[name] == original[name], 'Unrelated entry changed: '+name)
    marker = b"\nlog 'WIFI_TWO_STAGE_BOOTSTRAP_BEGIN'\n"
    source = (P/'lynx-storage-outcome-runtime.sh').read_bytes()
    expected = original['init']['data'].split(marker)[0] + source + b"\nlog 'WIFI_TWO_STAGE_BOOTSTRAP_BEGIN'\nlynx_storage_probe\nstop\n"
    require(entries['init']['data'] == expected == (F/'init-source').read_bytes(), 'Unexpected executable init content')
    require(entries['etc/lynx/session-token']['data'].decode().strip() == json.loads((F/'build-validation.json').read_text())['session_token'], 'Experiment session differs')
    _,_,_,coverage,offset,size = struct.unpack('!4sIIQQQ28x',reference[-64:])
    require(image[coverage:] == reference[coverage:] and image[offset:offset+size] == reference[offset:offset+size], 'Supplement/metadata/footer changed')
    require((4096+((len(boot['kernel'])+4095)//4096)*4096+((len(boot['ramdisk'])+4095)//4096)*4096) <= coverage, 'Loaded area overlaps metadata')
    tests = sorted((ROOT/'tools/test-artifacts').glob('storage-outcome-control-*/result.json'))
    require(tests, 'Control test missing')
    test = json.loads(tests[-1].read_text())
    require(test['passed'] and test['source_sha256'] == hashlib.sha256(source).hexdigest(), 'Tested source mismatch')
    vms = sorted((P/'artifacts').glob('emulated-storage-outcome-image-*/result.json'))
    require(vms, 'Exact image guard VM test missing')
    vm = json.loads(vms[-1].read_text())
    require(vm['candidate_sha256'] == SHA and vm['module_checkpoint_failure_guard_observed'] and not vm['kernel_reboot_command_observed'], 'Hardware guard test failed')
    require((F/'nord3-busybox-candidate.img').stat().st_mode & 0o777 == 0o600, 'Private image permissions wrong')
    out = P/'docs/storage-outcome-image-validation.json'
    out.write_text(json.dumps({'passed':True,'candidate_sha256':SHA,'kernel_unchanged':True,
                              'stock_metadata_footer_supplement_unchanged':True,'control_receipt':str(tests[-1]),
                              'exact_vm_receipt':str(vms[-1]),'phone_contacted':False,
                              'limits':'Coarse timing outcome remains an inference; no persistent internal log retrieval proven.'},indent=2)+'\n')
    print(out)


if __name__ == '__main__':
    main()
