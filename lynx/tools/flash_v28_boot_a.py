"""One guarded V28 boot_a-only trial; never reboots Lynx on USB."""
import argparse
import json
from pathlib import Path
import sys
import time

import flash_v25d_boot_a as base

ROOT = Path(__file__).resolve().parent.parent
base.IMAGE = ROOT / 'linux-port/artifacts/local-health-v28-offline/nord3-local-health-untested.img'
base.IMAGE_SHA = 'a22048376cec353af652c187da733eb198f1382efcf19924eebd5ba0b883d775'
base.VARIANT = 'v28'
base.EXCEPTION = ROOT / 'linux-port/docs/V28-TRIAL-EXCEPTION.json'


def check_scope(usb_receipt):
    review = json.loads(base.EXCEPTION.read_text())
    if review.get('state') != 'offline-ready-not-flashed':
        raise ValueError('V28 trial scope has been consumed or is not active')
    for path in (ROOT / 'logs').glob('v28-boot-a-trial-*.json'):
        if json.loads(path.read_text()).get('flash_performed') is True:
            raise ValueError('V28 boot_a already written once')
    contact = json.loads((ROOT / review['proven_v19_contact_receipt']).read_text())
    health = json.loads((ROOT / review['proven_health_receipt']).read_text())
    if (contact.get('state') != 'native-ssh-available' or
            contact.get('native_ssh_verified') is not True or
            health.get('state') != 'phone-ram-health-stage-verified' or
            health.get('contact_receipt') != str(ROOT / review['proven_v19_contact_receipt'])):
        raise ValueError('Fresh V19 recovery or health proof missing')
    path = usb_receipt.resolve(strict=True)
    if not path.is_relative_to(ROOT / 'logs'):
        raise ValueError('USB observer receipt escaped Lynx logs')
    usb = json.loads(path.read_text())
    if (usb.get('initial_fastboot_seen') is not True or
            usb.get('departure_observed') is not False or
            usb.get('observation_complete') is not False or
            time.time_ns() - usb.get('heartbeat_ns', 0) > 15_000_000_000):
        raise ValueError('Fresh passive Fastboot USB observer required')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--usb-observer-receipt', type=Path)
    args, remaining = parser.parse_known_args()
    if '--flash' in remaining:
        if args.usb_observer_receipt is None:
            raise ValueError('V28 flash requires a fresh passive USB observer')
        check_scope(args.usb_observer_receipt)
    sys.argv = [sys.argv[0]] + remaining
    base.main()
