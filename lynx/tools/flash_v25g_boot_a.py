"""Guarded V25g boot_a-only trial; never reboots with USB attached."""
from pathlib import Path

import flash_v25d_boot_a as base

ROOT = Path(__file__).resolve().parent.parent
base.IMAGE = ROOT / 'linux-port/artifacts/selfboot-compact-v25g-offline/nord3-selfboot-compact-untested.img'
base.IMAGE_SHA = '84b037a79eb678524a88e8c66ced214502ea5381193df26e2c7cec024083bebe'
base.VARIANT = 'v25g'
base.EXCEPTION = ROOT / 'linux-port/docs/V25G-TRIAL-EXCEPTION.json'


if __name__ == '__main__':
    base.main()
