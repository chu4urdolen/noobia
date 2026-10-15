"""Fixed boot_a modules-only checkpoint; verified stock undo, timed passive capture."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
from lynx_trial_observer import USBObserver
from lynx_wpa_timing import decode_progress_timing

ROOT = Path(__file__).resolve().parent.parent
PROJECT = ROOT / 'linux-port'
FASTBOOT = ROOT / 'tools/platform-tools/fastboot'
SERIAL = '89BYAY5L4T9HFUOV'
LINUX = PROJECT / 'artifacts/busybox-wifi-ssh-twostage-v19/nord3-busybox-candidate.img'
STOCK = PROJECT / 'artifacts/stock-cph2493-August-eu-ota/boot.img'
EXPECTED = {LINUX: ('5ce2dbf8a7c132fa7e31f6be70aa76f83afe8c293e2cd5f02251a532486fd851', 67108864),
            STOCK: ('a67f03d7b826b834c23653b67eaa6efa971eb70ef8af19eee4d33fb5fc7fe995', 67108864)}


def main():
    parser = argparse.ArgumentParser()
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument('--flash-linux', action='store_true')
    actions.add_argument('--restore-stock', action='store_true')
    parser.add_argument('--reboot', action='store_true', help='Reboot only after a successful Linux image write')
    parser.add_argument('--network-receipt', type=Path)
    args = parser.parse_args()
    safety_path = PROJECT / 'docs/SAFETY-HOLD.json'
    if args.flash_linux and safety_path.exists():
        hold = json.loads(safety_path.read_text())
        if hold.get('active'):
            raise ValueError('Linux flash held for thermal safety: ' + hold['reason'])
    if args.reboot and not args.flash_linux:
        raise ValueError('Reboot is permitted only as part of the Linux trial')
    checks = []
    for path, (digest, size) in EXPECTED.items():
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != digest or path.stat().st_size != size:
            raise ValueError('Image hash or size changed: ' + str(path))
        checks.append({'file': str(path), 'sha256': actual, 'bytes': size})
    integrity = json.loads((ROOT / 'downloads/august-eu-ota-integrity.json').read_text())
    signature = json.loads((ROOT / 'downloads/august-eu-payload-signature.json').read_text())
    if integrity['state'] != 'verified' or signature['state'] != 'verified' or not signature['full_payload_signature_valid']:
        raise ValueError('Stock OTA verification did not pass')
    if not args.restore_stock:
        validation = subprocess.run(['python3', str(ROOT / 'tools/validate_wifi_v19_image.py')],
                                    capture_output=True, text=True, timeout=30)
        if validation.returncode and not args.restore_stock:
            raise ValueError('Independent boot-proof validation failed: ' + validation.stdout + validation.stderr)
    baseline_path = ROOT / 'logs/stock-boot-chain-1791640196780904534.json'
    baseline = json.loads(baseline_path.read_text())
    if not baseline.get('all_four_writes_accepted'):
        raise ValueError('Matching stock boot-chain restoration did not complete')
    expected_baseline = {'boot_a': EXPECTED[STOCK][0],
                         'vendor_boot_a': '373c40ce66c2cf37d86f104ddb8f5affc9ab9d2f499d61ac79244b569f172587',
                         'dtbo_a': '44d947fdebee0f389295041f5af9a3509dc5dc8e1ec28c71d0b64370a8522e79',
                         'vbmeta_a': 'ff7225b9242c460586e463ef9557eab463865546be20eb245c93b62883ea8484'}
    if {item['partition']: item['sha256'] for item in baseline['images']} != expected_baseline:
        raise ValueError('Stock baseline receipt does not match this trial')
    for item in baseline['images']:
        if hashlib.sha256(Path(item['file']).read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('Stock baseline reference changed')
    recorded = json.loads((ROOT / 'logs/fastboot-preflight-1791602958363822313.json').read_text())
    fastboot_hash = hashlib.sha256(FASTBOOT.read_bytes()).hexdigest()
    if fastboot_hash != recorded['fastboot_sha256']:
        raise ValueError('Fastboot binary changed since the reviewed preflight')
    trial_command = [str(FASTBOOT), '-s', SERIAL, 'flash', 'boot_a', str(LINUX)]
    restore_command = [str(FASTBOOT), '-s', SERIAL, 'flash', 'boot_a', str(STOCK)]
    report = {'diagnostic_journals':['supervisor','bootstrap','wifi'], 'physical_log_persistence_verified':False, 'network_goal': 'native Wi-Fi and pinned key-only SSH', 'max_bootstrap_seconds':180, 'max_wifi_seconds':240, 'mode': 'offline-readiness', 'module_prefix_count': 34, 'null_node_fix': True, 'mtu3_loaded': False, 'tool_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'observer_tool_sha256': hashlib.sha256((ROOT/'tools/lynx_trial_observer.py').read_bytes()).hexdigest(), 'images': checks, 'fastboot_sha256': fastboot_hash,
              'trial_command': trial_command, 'restore_command': restore_command,
              'authorized_partition': 'boot_a', 'slot_switch_allowed': False,
              'user_authorized_expanded_recovery_and_native_linux_scope': True,
              'stock_boot_a_fastboot_write_previously_succeeded': True,
              'stock_recovery_menu_observed_by_user': True,
              'recovery_adb_available': False,
              'phone_contacted': False, 'operations': []}
    output = ROOT / 'logs' / ('boot-a-wifi-v19-trial-' + str(time.time_ns()) + '.json')

    def save():
        output.write_text(json.dumps(report, indent=2) + '\n')

    save()
    print('Stock boot image and exact restoration command verified.', flush=True)
    print('Report:', output, flush=True)
    if not (args.flash_linux or args.restore_stock):
        print(json.dumps(report, indent=2))
        return
    if args.flash_linux:
        if args.network_receipt is None: raise ValueError('Ready network collector receipt required')
        collector=json.loads(args.network_receipt.read_text())
        build=json.loads((LINUX.parent/'build-validation.json').read_text())
        if collector.get('state')!='listening' or collector.get('session_token')!=build['session_token'] or time.time_ns()-collector.get('heartbeat_ns',0)>10_000_000_000 or collector.get('elapsed_seconds',0)>90:
            raise ValueError('Collector is not fresh and ready for this image')
        address=subprocess.run(['ip','-j','address','show','dev','wlx40a5ef5f66f1'],capture_output=True,text=True,timeout=5)
        host=json.loads(address.stdout)
        if not any(item.get('local')==build['collector_ip'] for dev in host for item in dev.get('addr_info',[])):
            raise ValueError('Noobia host address changed; no flash issued')
        report['network_collector_receipt']=str(args.network_receipt)
        report['network_session_token']=build['session_token']
    report.update(mode='restore-stock' if args.restore_stock else 'flash-linux', phone_contacted=True)
    save()
    preflight = subprocess.run(['python3', str(ROOT / 'tools/lynx_fastboot_preflight.py'), '--connect'],
                               capture_output=True, text=True, timeout=120)
    report['preflight_output'] = preflight.stdout + preflight.stderr
    save()
    if preflight.returncode != 0:
        raise ValueError('Fresh read-only preflight failed; no write issued')
    fresh = json.loads(preflight.stdout)
    if int(fresh['values']['max-download-size'], 16) < EXPECTED[STOCK][1]:
        raise ValueError('Fastboot limit does not cover prepared stock undo image')
    command = restore_command if args.restore_stock else trial_command
    observer = None
    if args.flash_linux:
        if not args.reboot:
            raise ValueError('Checkpoint trial requires one reboot for observation')
        observer_path = ROOT / 'logs' / ('usb-wifi-observer-' + str(time.time_ns()) + '.json')
        observer = USBObserver(observer_path)
        observer.start()
        report['usb_observer_receipt'] = str(observer_path)
        save()
    report['operations'].append({'command': command, 'state': 'issued', 'started_ns': time.time_ns(), 'started_monotonic': time.monotonic()})
    save()
    try:
        process = subprocess.run(command, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired as error:
        report['operations'][-1].update(state='timeout', output=str(error))
        save()
        raise
    text = process.stdout + process.stderr
    report['operations'][-1].update(state='returned', finished_ns=time.time_ns(), elapsed_seconds=time.monotonic()-report['operations'][-1]['started_monotonic'], exit_code=process.returncode, output=text)
    save()
    print(text, flush=True)
    if process.returncode != 0:
        raise SystemExit(process.returncode)
    if args.reboot:
        command = [str(FASTBOOT), '-s', SERIAL, 'reboot']
        report['operations'].append({'command': command, 'state': 'issued', 'started_ns': time.time_ns(), 'started_monotonic': time.monotonic()})
        save()
        process = subprocess.run(command, capture_output=True, text=True, timeout=15)
        report['operations'][-1].update(state='returned', finished_ns=time.time_ns(), elapsed_seconds=time.monotonic()-report['operations'][-1]['started_monotonic'], exit_code=process.returncode,
                                        output=process.stdout + process.stderr)
        save()
        print(process.stdout + process.stderr, flush=True)
        if process.returncode != 0:
            raise SystemExit(process.returncode)

    if observer is not None:
        print('Observing USB and pinned SSH contact for up to 660 seconds; no additional phone commands from this trial tool.', flush=True)
        report['native_ssh_verified']=False
        deadline=time.monotonic()+660
        while time.monotonic()<deadline:
            if observer.returned.is_set(): break
            if observer.failure: raise RuntimeError('USB observer failed: '+observer.failure)
            contact=json.loads(args.network_receipt.read_text())
            if contact.get('native_ssh_verified') and contact.get('fallback_cancel_ack_exit_code')==0 and contact.get('session_token')==report['network_session_token']:
                report['native_ssh_verified']=True
                report['native_phone_ip']=contact['phone_ip']
                break
            time.sleep(.25)
        observer.stop()
        report['fastboot_return_observed']=observer.returned.is_set()
        if observer.returned.is_set():
            manifest=json.loads((LINUX.parent/'build-validation.json').read_text())
            baseline=json.loads((PROJECT/'docs/progress-debug-calibration.json').read_text())['baseline_seconds']
            report.update(decode_progress_timing(report['operations'][-1],json.loads(observer_path.read_text()),manifest,baseline))
        report['stock_undo_pending']=not report['native_ssh_verified']
        report['requires_fresh_preflight_and_reset_evidence']=not report['native_ssh_verified']
        save()
        print('Fastboot return:',report['fastboot_return_observed'],'Pinned native SSH:',report['native_ssh_verified'],flush=True)



if __name__ == '__main__':
    main()
