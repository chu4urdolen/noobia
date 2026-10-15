"""Create separate fixed-hash tools for the storage-only diagnostic."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
T = ROOT/'tools'
SHA = '85d219fd6625897638ef70ee9abd9959cbf625f0063cecf19905a70f03b5e358'


def main():
    vm = (T/'test_wifi_v4_image_vm.py').read_text().replace('busybox-wifi-ssh-twostage-v4','busybox-storage-outcome-v1').replace('emulated-wifi-v4-image-','emulated-storage-outcome-image-')
    target = T/'test_storage_outcome_image_vm.py'
    assert not target.exists()
    target.write_text(vm)
    trial = (T/'lynx_boot_a_wifi_v4_trial.py').read_text()
    trial = trial.replace('busybox-wifi-ssh-twostage-v4','busybox-storage-outcome-v1').replace('0abe578cdc82a8f42b6bd812f3217dcc622f2a980d93e3c3418bc6dadf731af7',SHA)
    trial = trial.replace('validate_wifi_v4_image.py','validate_storage_outcome_image.py').replace('boot-a-wifi-v4-trial-','boot-a-storage-outcome-trial-')
    trial = trial.replace("'network_goal': 'native Wi-Fi and pinned key-only SSH'", "'diagnostic_goal': 'coarse storage result via one timed standard reboot'")
    start = trial.index('    if args.flash_linux:\n        if args.network_receipt is None:')
    end = trial.index('    report.update(mode=',start)
    trial = trial[:start] + trial[end:]
    start = trial.index("        deadline=time.monotonic()+600")
    end = trial.index('        observer.stop()',start)
    trial = trial[:start] + '''        deadline=time.monotonic()+330
        while time.monotonic()<deadline:
            if observer.returned.is_set(): break
            if observer.failure: raise RuntimeError('USB observer failed: '+observer.failure)
            time.sleep(.25)
''' + trial[end:]
    trial = trial.replace('Observing USB and pinned SSH contact for up to 600 seconds','Observing USB for up to 330 seconds')
    marker = "        report['fastboot_return_observed']=observer.returned.is_set()"
    assert trial.count(marker) == 1
    trial = trial.replace(marker, marker + '''
        if observer.returned.is_set():
            usb=json.loads(observer_path.read_text())
            reboot_finished=report['operations'][-1]['finished_ns']
            event=usb['events'][-1]
            elapsed=(event['wall_time_ns']-reboot_finished)/1e9
            manifest=json.loads((LINUX.parent/'build-validation.json').read_text())
            matches=[(code,abs(elapsed-(manifest['baseline_reference_seconds']+delay))) for code,delay in manifest['target_delays_seconds'].items()]
            inferred,error=min(matches,key=lambda pair:pair[1])
            report.update(return_seconds_after_reboot=elapsed,timing_nearest_code_hex='0x'+format(int(inferred),'02x'),timing_residual_seconds=error)
            if error<=manifest['timing_match_tolerance_seconds']:
                report['timing_inferred_outcome']=manifest['result_codes'][inferred]
            else: report['timing_inferred_outcome']=None
            report['outcome_limits']='Timing inference only. Requires post-return reset evidence and no physical interference; boot latency changes can invalidate classification.'
''',1)
    target = T/'lynx_boot_a_storage_outcome_trial.py'
    assert not target.exists()
    target.write_text(trial)
    print('Created bounded, fixed-image storage probe tools; no handset commands issued.')


if __name__ == '__main__':
    main()
