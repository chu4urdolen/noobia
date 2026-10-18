"""Guarded V27a boot_a-only diagnostic; never reboots on USB."""
from pathlib import Path

import flash_v25d_boot_a as base

ROOT = Path(__file__).resolve().parent.parent
base.IMAGE = ROOT / 'linux-port/artifacts/minimal-local-ssh-v27a-offline/nord3-minimal-local-ssh-untested.img'
base.IMAGE_SHA = 'db5381f525153971bc878109e67f47ad3256d6454d69eeab0802e3477e0024f4'
base.VARIANT = 'v27a'
base.EXCEPTION = ROOT / 'linux-port/docs/V27A-TRIAL-EXCEPTION.json'


if __name__ == '__main__':
    base.main()
