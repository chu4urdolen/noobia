#!/usr/bin/env python3
"""Is Lynx's guard switch on? (Tom, 2026-11-22: 45 C is fine; guards off.)

While /etc/lynx/power-thermal-guard.disable exists on Lynx, the camera trial
and preparation tools skip their battery and temperature gates (identity,
boot-image and health-issue checks still apply). The answer is read once per
process over the pinned Alpine SSH link; any doubt means the guards stay ON.
"""
import functools
import subprocess

from lynx_wifi_v19_contact import ssh_command

HOST = "192.168.100.107"
SWITCH = "/etc/lynx/power-thermal-guard.disable"


@functools.lru_cache(maxsize=1)
def guards_off() -> bool:
    argv = ssh_command(HOST, f"test -e {SWITCH} && echo GUARDS_OFF || echo GUARDS_ON")
    argv[-2:-2] = ["-p", "2222"]
    try:
        out = subprocess.run(argv, capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return out.strip().splitlines()[-1:] == ["GUARDS_OFF"]
