"""Fixed, reviewed V25f boot_a-only trial. Never reboots with USB attached."""
from pathlib import Path

import flash_v25d_boot_a as base

ROOT = Path(__file__).resolve().parent.parent
base.IMAGE = ROOT / 'linux-port/artifacts/selfboot-wifi-first-v25f-offline/nord3-selfboot-health-untested.img'
base.IMAGE_SHA = 'e885fb8162e7faf40fba68732fadd77aa3b4328a4b235e4ae4e60873d8feec0d'
base.VARIANT = 'v25f'
base.EXCEPTION = ROOT / 'linux-port/docs/V25F-TRIAL-EXCEPTION.json'


if __name__ == '__main__':
    base.main()
