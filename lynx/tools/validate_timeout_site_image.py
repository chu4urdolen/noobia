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
F = P/'artifacts/busybox-timeout-site-v1'
SHA = '21d10aad02191ce95e6c7b8fec70528b57504d56d2f3b8c03654e5826427b832'


def main():
    validation = subprocess.run(['python3',str(ROOT/'tools/validate_wifi_v4_image.py')],capture_output=True,text=True,timeout=30)
    require(validation.returncode == 0, 'Original v4 validation failed: '+validation.stdout+validation.stderr)
    image = (F/'nord3-busybox-candidate.img').read_bytes()
    require(hashlib.sha256(image).hexdigest() == SHA and len(image) == 67108864, 'Storage image changed')
    reference = (P/'artifacts/busybox-wifi-ssh-twostage-v4/nord3-busybox-candidate.img').read_bytes()
    boot, previous = read_boot_v4(image),read_boot_v4(reference)
    require(boot['kernel'] == previous['kernel'], 'Kernel changed')
    require(image[:12]==reference[:12] and image[16:44]==reference[16:44] and image[1580:4096]==reference[1580:4096], 'Unrelated header change')
    require(boot['cmdline']==previous['cmdline']+' fw_devlink=permissive','Unexpected command line')
    entries, original = read_newc(decompress(boot['ramdisk'])),read_newc(decompress(previous['ramdisk']))
    require(set(entries)-set(original)=={'etc/lynx/classify-driver-trace.awk','etc/lynx/classify-timeout-logs.awk'},'Unexpected first-stage files')
    require(entries['etc/lynx/classify-driver-trace.awk']['data']==(P/'lynx-classify-platform-errno.awk').read_bytes(),'Classifier source changed')
    for name in entries:
        if name not in ['init','etc/lynx/session-token','etc/lynx/classify-driver-trace.awk','etc/lynx/classify-timeout-logs.awk']:
            require(entries[name] == original[name], 'Unrelated entry changed: '+name)
    marker = b"\nlog 'WIFI_TWO_STAGE_BOOTSTRAP_BEGIN'\n"
    source = (F/'trace-runtime.sh').read_bytes()
    expected = original['init']['data'].split(marker)[0] + source + b"\nlog 'WIFI_TWO_STAGE_BOOTSTRAP_BEGIN'\nlynx_storage_probe\nstop\n"
    require(entries['init']['data'] == expected == (F/'init-source').read_bytes(), 'Unexpected executable init content')
    require(entries['etc/lynx/session-token']['data'].decode().strip() == json.loads((F/'build-validation.json').read_text())['session_token'], 'Experiment session differs')
    _,_,_,coverage,offset,size = struct.unpack('!4sIIQQQ28x',reference[-64:])
    require(image[coverage:] == reference[coverage:] and image[offset:offset+size] == reference[offset:offset+size], 'Supplement/metadata/footer changed')
    require((4096+((len(boot['kernel'])+4095)//4096)*4096+((len(boot['ramdisk'])+4095)//4096)*4096) <= coverage, 'Loaded area overlaps metadata')
    tests = sorted((ROOT/'tools/test-artifacts').glob('timeout-site-control-*/result.json'))
    require(tests, 'Control test missing')
    test = json.loads(tests[-1].read_text())
    require(test['passed'] and test['source_sha256'] == hashlib.sha256((P/'lynx-timeout-log-runtime.sh').read_bytes()).hexdigest(), 'Tested source mismatch')
    vms = sorted((P/'artifacts').glob('emulated-timeout-site-image-*/result.json'))
    require(vms, 'Exact image guard VM test missing')
    vm = json.loads(vms[-1].read_text())
    require(vm['candidate_sha256'] == SHA and vm['module_checkpoint_failure_guard_observed'] and not vm['kernel_reboot_command_observed'], 'Hardware guard test failed')
    require((F/'nord3-busybox-candidate.img').stat().st_mode & 0o777 == 0o600, 'Private image permissions wrong')
    model=ROOT/'tools/avb-host/avb-boot-model'
    model_reference=json.loads((P/'docs/avb-boot-model-results.json').read_text())
    require(hashlib.sha256(model.read_bytes()).hexdigest()==model_reference['binary_sha256'],'AVB model changed')
    for unlocked in ['1','0']:
        check=subprocess.run([str(model),str(P/'artifacts/stock-cph2493-August-eu-ota'),str(F/'nord3-busybox-candidate.img'),'0',unlocked],capture_output=True,text=True,timeout=30)
        require(check.returncode==0,'AVB model failed')
        require(json.loads(check.stdout)['slot_data_returned']==(unlocked=='1'),'Unlocked/locked policy changed')
    require((F/'collector-source.sh').read_bytes() in source,'Observational trace source missing')
    native=sorted(path for path in (P/'artifacts').glob('emulated-native-driver-trace-cortex-a710-*/result.json') if json.loads(path.read_text()).get('source_sha256')==hashlib.sha256((F/'collector-source.sh').read_bytes()).hexdigest());require(native,'Matching concrete modern ARM trace test missing')
    n=json.loads(native[-1].read_text());require(n['passed'] and n.get('collector_platform') and n.get('platform_v2') and n.get('errno_classifier') and n.get('deferred_reset_probe') and n.get('module_loading_under_trace') and not n.get('baseline_only') and n['source_sha256']==hashlib.sha256((F/'collector-source.sh').read_bytes()).hexdigest() and n['classifier_sha256']==hashlib.sha256((P/'lynx-classify-platform-errno.awk').read_bytes()).hexdigest(),'Native tested trace/classifier mismatch')
    fixtures=sorted((ROOT/'tools/test-artifacts').glob('platform-errno-classifier-*/result.json'));require(fixtures,'Parser semantic fixtures missing')
    f=json.loads(fixtures[-1].read_text());require(f['passed'] and f['source_sha256']==hashlib.sha256((P/'lynx-classify-platform-errno.awk').read_bytes()).hexdigest(),'Parser semantic tested source mismatch')
    require((P/'lynx-timeout-log-runtime.sh').read_bytes() in source and (P/'lynx-live-ufs-name.sh').read_bytes() in source,'Errno control/name source missing')
    require(n['live_name_source_sha256']==hashlib.sha256((P/'lynx-live-ufs-name.sh').read_bytes()).hexdigest(),'Native live-name tested source differs')
    timing=sorted((ROOT/'tools/test-artifacts').glob('errno-timing-*/result.json'));require(timing,'Monotonic decoder test missing')
    t=json.loads(timing[-1].read_text());require(t['passed'] and t['decoder_sha256']==hashlib.sha256((ROOT/'tools/lynx_errno_timing.py').read_bytes()).hexdigest() and t['observer_sha256']==hashlib.sha256((ROOT/'tools/lynx_trial_observer.py').read_bytes()).hexdigest(),'Tested decoder/observer changed')
    manifest=json.loads((F/'build-validation.json').read_text());require(manifest['observation_seconds']==380 and manifest['timing_match_tolerance_seconds']==0.8 and manifest['baseline_reference_seconds']==21.9,'Timing protocol changed')
    require(manifest['target_delays_seconds']=={str(value):60+2*value for value in range(128)},'Timing field mapping changed')
    log_source=(P/'lynx-classify-timeout-sites.awk').read_bytes()
    require(entries['etc/lynx/classify-timeout-logs.awk']['data']==log_source,'Log classifier image/source differs')
    log_vms=sorted((P/'artifacts').glob('emulated-native-timeout-sites-cortex-a710-*/result.json'));require(log_vms,'Native log parser VM missing')
    l=json.loads(log_vms[-1].read_text());require(l['passed'] and l['vm_only_synthetic_kmsg'] and l['log_classifier_sha256']==hashlib.sha256(log_source).hexdigest(),'Native log tests source mismatch')
    require(l['checks']['vm_synthetic_kmsg_roundtrip'],'Native dmesg roundtrip missing')
    decoder_tests=sorted((ROOT/'tools/test-artifacts').glob('timeout-site-timing-*/result.json'));require(decoder_tests,'Mask decoder test missing')
    dt=json.loads(decoder_tests[-1].read_text());require(dt['passed'] and dt['decoder_sha256']==hashlib.sha256((ROOT/'tools/lynx_timeout_site_timing.py').read_bytes()).hexdigest(),'Mask decoder changed')
    audit=json.loads((P/'docs/timeout-message-audit.json').read_text());require(audit['passed'] and audit['kernel_sha256']==hashlib.sha256(boot['kernel']).hexdigest(),'Exact stock message audit missing')
    out = P/'docs/timeout-site-image-validation.json'
    out.write_text(json.dumps({'passed':True,'candidate_sha256':SHA,'kernel_unchanged':True,
                              'stock_metadata_footer_supplement_unchanged':True,'control_receipt':str(tests[-1]),
                              'exact_vm_receipt':str(vms[-1]),'phone_contacted':False,
                              'limits':'Coarse timing outcome remains an inference; no persistent internal log retrieval proven.'},indent=2)+'\n')
    print(out)


if __name__ == '__main__':
    main()
