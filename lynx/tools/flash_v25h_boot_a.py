"""Guarded V25h boot_a-only discovery trial; never reboots on USB."""
from pathlib import Path

import flash_v25d_boot_a as base

ROOT = Path(__file__).resolve().parent.parent
base.IMAGE = ROOT / 'linux-port/artifacts/selfboot-beacon-v25h-offline/nord3-selfboot-beacon-untested.img'
base.IMAGE_SHA = 'e6afd7ae10f77d78939d4a6b011eaeca2c255c35642434040539913d9891bd5c'
base.VARIANT = 'v25h'
base.EXCEPTION = ROOT / 'linux-port/docs/V25H-TRIAL-EXCEPTION.json'


if __name__ == '__main__':
    base.main()
