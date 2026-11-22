#!/usr/bin/env python3
"""Lynx Boot & Persistence Watcher.

Continuously monitors Lynx's boot state:
1. When Lynx reboots into the early BusyBox stage (port 22):
   Detects 'SSH_READY_WAITING_FOR_PINNED_HOST' and writes /run/lynx/host-confirmed
   using the pinned session token so she transitions into Alpine userspace automatically.
2. When Lynx enters Alpine userspace (port 2222):
   Tracks boot ID changes and auto-prepares the camera stack in RAM if not already prepared.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

HOST = "192.168.100.107"
LOG_FILE = ROOT / "logs" / "lynx_boot_watcher.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
    ],
)
logger = logging.getLogger("lynx_boot_watcher")


def is_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, socket.timeout):
        return False


def run_ssh(port: int, command: str, timeout: int = 15) -> tuple[int, str]:
    from lynx_wifi_v19_contact import ssh_command
    argv = ssh_command(HOST, command)
    argv[-2:-2] = ["-p", str(port)]
    try:
        res = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return res.returncode, (res.stdout + res.stderr).strip()
    except Exception as e:
        return 1, str(e)


def handle_busybox_stage():
    code, out = run_ssh(22, "cat /run/lynx/phase 2>/dev/null", timeout=8)
    if "SSH_READY_WAITING_FOR_PINNED_HOST" in out:
        check_code, _ = run_ssh(22, "test -f /run/lynx/host-confirmed", timeout=5)
        if check_code == 0:
            logger.debug("Host already confirmed, waiting for OpenRC transition...")
            return
        logger.info("Lynx detected in bootstrap stage waiting for pinned host confirmation...")
        code, token = run_ssh(22, "cat /etc/lynx/session-token 2>/dev/null || cat /run/lynx/session-token 2>/dev/null", timeout=8)
        token = token.strip()
        if code == 0 and len(token) == 32:
            ack_cmd = f"printf '%s\\n' '{token}' > /run/lynx/host-confirmed.tmp && mv /run/lynx/host-confirmed.tmp /run/lynx/host-confirmed"
            ack_code, ack_out = run_ssh(22, ack_cmd, timeout=8)
            if ack_code == 0:
                logger.info(f"Successfully confirmed host session token ({token[:8]}...) -> Transitioning to Alpine!")
            else:
                logger.warning(f"Host confirmation failed: {ack_out}")


def check_and_prepare_camera(last_boot_id: str | None) -> str | None:
    code, boot_id = run_ssh(2222, "cat /proc/sys/kernel/random/boot_id", timeout=8)
    if code != 0 or not boot_id or len(boot_id) != 36:
        return last_boot_id

    if boot_id != last_boot_id:
        logger.info(f"Alpine userspace active on new boot: {boot_id}")
        # Tom 2026-11-23: preparing the camera the instant Alpine starts heats a
        # still-warm Lynx past the boot image's thermal guards. Camera
        # preparation is off while this switch exists (shared with
        # lynx-camera-keeper). Boot confirmation above is unaffected.
        # 2026-11-23: one camera preparer only - noobia-lynx-camera-keeper, which
        # waits for settle, health and the never-poweroff watchers.
        logger.info("Camera preparation is done by noobia-lynx-camera-keeper, not here")
        return boot_id
        # Check camera status
        status_script = ROOT / "tools" / "prepare_camera_camsv.py"
        res = subprocess.run([sys.executable, str(status_script), "--status"], capture_output=True, text=True, timeout=15, cwd=str(TOOLS))
        if "not_prepared" in res.stdout:
            logger.info("Camera not prepared for this boot. Auto-preparing camera stack in RAM...")
            prep_res = subprocess.run([sys.executable, str(status_script), "--execute", "--attended"], capture_output=True, text=True, timeout=120, cwd=str(TOOLS))
            if prep_res.returncode == 0:
                logger.info("Camera stack successfully auto-prepared!")
            else:
                logger.warning(f"Camera auto-prepare finished with returncode {prep_res.returncode}: {prep_res.stderr.strip()[:200]}")
        return boot_id

    return last_boot_id


def main():
    logger.info("Starting Lynx Boot & Persistence Watcher daemon...")
    last_boot_id = None
    while True:
        try:
            if is_port_open(HOST, 2222):
                last_boot_id = check_and_prepare_camera(last_boot_id)
            elif is_port_open(HOST, 22):
                handle_busybox_stage()
        except Exception as e:
            logger.debug(f"Loop iteration exception: {e}")
        time.sleep(2.0)


if __name__ == "__main__":
    main()
