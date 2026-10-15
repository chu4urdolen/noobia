"""Freeze a checkpoint-specific copy of the existing guarded boot_a trial."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def replace_once(text, before, after):
    assert text.count(before) == 1, 'Reviewed source changed: ' + before[:80]
    return text.replace(before, after)


def main():
    target = ROOT / 'lynx_boot_a_usb_checkpoint_trial.py'
    assert not target.exists(), 'Preserve trial source'
    source = (ROOT / 'lynx_boot_a_busybox_console_trial.py').read_text()
    source = replace_once(source, 'import time\n', 'import time\nfrom lynx_trial_observer import USBObserver\n')
    source = source.replace('busybox-August-busybox-console', 'busybox-usb-module-checkpoints/with-mtu3')
    source = source.replace('3c75e5791fa9ed6be1a655e978fac4c68b8ea1479ca4777b54106f51326572dc', '5bb984899b19c9e739faa23aa9039374a5ad20ab99c10948d5d2b964da3616d6')
    source = source.replace('validate_busybox_usb_console.py', 'validate_usb_module_checkpoint.py')
    source = source.replace('boot-a-busybox-console-trial-', 'boot-a-usb-checkpoint-trial-')
    start = source.index('    if args.flash_linux:\n        active=')
    end = source.index("    report['operations'].append", start)
    source = source[:start] + '''    observer = None
    if args.flash_linux:
        if not args.reboot:
            raise ValueError('Checkpoint trial requires one reboot for observation')
        observer_path = ROOT / 'logs' / ('usb-checkpoint-observer-' + str(time.time_ns()) + '.json')
        observer = USBObserver(observer_path)
        observer.start()
        report['usb_observer_receipt'] = str(observer_path)
        save()
''' + source[end:]
    source = source.replace("{'command': command, 'state': 'issued'}", "{'command': command, 'state': 'issued', 'started_ns': time.time_ns(), 'started_monotonic': time.monotonic()}")
    source = source.replace("update(state='returned', exit_code=process.returncode", "update(state='returned', finished_ns=time.time_ns(), elapsed_seconds=time.monotonic()-report['operations'][-1]['started_monotonic'], exit_code=process.returncode")
    source = replace_once(source, "\n\nif __name__ == '__main__':", '''
    if observer is not None:
        print('Observing USB for up to 180 seconds after reboot; no further phone commands.', flush=True)
        report['fastboot_return_observed'] = observer.observe_return(180)
        report['requires_fresh_preflight_and_reset_evidence'] = True
        report['stock_undo_pending'] = True
        save()
        print('Observed Fastboot return:', report['fastboot_return_observed'], flush=True)
        print('Observation:', report['usb_observer_receipt'], flush=True)


if __name__ == '__main__':''')
    source = replace_once(source, '"""Fixed boot_a BusyBox ACM-console trial; verified stock undo, no other partition writes."""', '"""Fixed boot_a modules-only checkpoint; verified stock undo, timed passive capture."""')
    compile(source, str(target), 'exec')
    target.write_text(source)
    print(target)


if __name__ == '__main__':
    main()
