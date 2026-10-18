"""Guarded V27a boot_a-only diagnostic; never reboots on USB."""
import json
from pathlib import Path
import sys

import flash_v25d_boot_a as base

ROOT = Path(__file__).resolve().parent.parent
base.IMAGE = ROOT / 'linux-port/artifacts/minimal-local-ssh-v27a-offline/nord3-minimal-local-ssh-untested.img'
base.IMAGE_SHA = 'db5381f525153971bc878109e67f47ad3256d6454d69eeab0802e3477e0024f4'
base.VARIANT = 'v27a'
base.EXCEPTION = ROOT / 'linux-port/docs/V27A-TRIAL-EXCEPTION.json'


def check_repeat_scope():
    review = json.loads(base.EXCEPTION.read_text())
    if review.get('state') != 'offline-ready-repeat-not-flashed':
        raise ValueError('V27a repeat review is not active')
    prior_path = ROOT / review['prior_trial_receipt']
    contact_path = ROOT / review['proven_v19_contact_receipt']
    if not prior_path.resolve().is_relative_to(ROOT / 'logs') or not contact_path.resolve().is_relative_to(ROOT / 'logs'):
        raise ValueError('V27a repeat evidence path escaped Lynx logs')
    prior = json.loads(prior_path.read_text())
    contact = json.loads(contact_path.read_text())
    if (prior.get('state') != 'written-await-unplugged-boot' or
            prior.get('images', {}).get('v27a', {}).get('sha256') != base.IMAGE_SHA or
            contact.get('state') != 'native-ssh-available' or
            contact.get('native_ssh_verified') is not True):
        raise ValueError('V27a repeat lacks prior trial and V19 recovery proof')
    for path in (ROOT / 'logs').glob('v27a-boot-a-trial-*.json'):
        if path == prior_path:
            continue
        trial = json.loads(path.read_text())
        if trial.get('created_ns', 0) > prior['created_ns'] and trial.get('flash_performed') is True:
            raise ValueError('V27a repeat already written; refusing a third trial')


if __name__ == '__main__':
    if '--flash' in sys.argv:
        check_repeat_scope()
    base.main()
