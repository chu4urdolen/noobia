#!/usr/bin/env python3
"""Lynx Cellular Bringup and Network Configuration Tool.

Autonomous Republic of Noobia - Principle 10: Graceful quiescence.
Brings up CCCI baseband (MediaTek MT6983 MD1) on OnePlus Nord 3 (Lynx),
unlocks SIM, activates cellular PDP context, and configures ccmni0.
"""

from __future__ import annotations

import os
import re
import select
import subprocess
import sys
import time
from pathlib import Path

# Partition mapping for OnePlus Nord 3 ( Dimensity 9000 MT6983 )
BY_NAME_MAP = {
    "para": "/dev/sdc2",
    "proinfo": "/dev/sdc46",
    "md1img": "/dev/sdc23",
    "md1img_a": "/dev/sdc23",
    "md1img_b": "/dev/sdc58",
    "md3img": "/dev/sdc23",
    "nvcfg": "/dev/sdc9",
    "nvdata": "/dev/sdc10",
    "persist": "/dev/sdc18",
    "protect1": "/dev/sdc19",
    "protect2": "/dev/sdc20",
    "nvram": "/dev/sdc48",
    "otp": "/dev/sdc22",
}

VENDOR_MOUNTS = [
    ("/dev/sdc9", "/mnt/vendor/nvcfg"),
    ("/dev/sdc10", "/mnt/vendor/nvdata"),
    ("/dev/sdc18", "/mnt/vendor/persist"),
    ("/dev/sdc19", "/mnt/vendor/protect_f"),
    ("/dev/sdc20", "/mnt/vendor/protect_s"),
]

VENDOR_SYMLINKS = [
    ("/mnt/vendor/nvdata", "/vendor/nvdata"),
    ("/mnt/vendor/nvcfg", "/vendor/nvcfg"),
    ("/mnt/vendor/protect_f", "/vendor/protect_f"),
    ("/mnt/vendor/protect_s", "/vendor/protect_s"),
    ("/mnt/vendor/nvdata/mdota", "/vendor/mdota"),
    ("/mnt/vendor/nvdata/md3", "/vendor/md3"),
]


def log(msg: str) -> None:
    print(f"[cellular-bringup] {msg}", flush=True)


def setup_partitions() -> None:
    log("Setting up by-name symlinks...")
    by_name_dir = Path("/dev/block/by-name")
    by_name_dir.mkdir(parents=True, exist_ok=True)
    bootdevice_dir = Path("/dev/block/bootdevice")
    bootdevice_dir.mkdir(parents=True, exist_ok=True)

    bootdevice_link = bootdevice_dir / "by-name"
    if not bootdevice_link.is_symlink() and not bootdevice_link.exists():
        try:
            bootdevice_link.symlink_to("/dev/block/by-name")
        except OSError:
            pass

    for name, target in BY_NAME_MAP.items():
        link_path = by_name_dir / name
        try:
            if link_path.is_symlink() or link_path.exists():
                link_path.unlink()
            link_path.symlink_to(target)
        except Exception as exc:
            log(f"Warning: failed symlinking {name} -> {target}: {exc}")


def setup_mounts() -> None:
    log("Setting up vendor mounts and permissions...")
    # sdc10 (nvdata) is sometimes marked read-only by kernel/LK
    subprocess.run(["blockdev", "--setrw", "/dev/sdc10"], check=False)

    for dev, mountpoint in VENDOR_MOUNTS:
        Path(mountpoint).mkdir(parents=True, exist_ok=True)
        # Check if already mounted
        res = subprocess.run(["mountpoint", "-q", mountpoint], check=False)
        if res.returncode != 0:
            log(f"Mounting {dev} at {mountpoint}...")
            subprocess.run(["mount", "-t", "ext4", dev, mountpoint], check=False)

    # Ensure nvdata is mounted read-write
    subprocess.run(["mount", "-o", "remount,rw", "/mnt/vendor/nvdata"], check=False)

    Path("/vendor/etc").mkdir(parents=True, exist_ok=True)
    for target, link in VENDOR_SYMLINKS:
        link_p = Path(link)
        try:
            if not link_p.is_symlink() and not link_p.exists():
                link_p.symlink_to(target)
        except Exception as exc:
            log(f"Warning: symlink {link} -> {target} failed: {exc}")

    # fstab
    if Path("/fstab.mt6983").exists() and not Path("/vendor/etc/fstab.mt6983").exists():
        try:
            subprocess.run(["cp", "/fstab.mt6983", "/vendor/etc/fstab.mt6983"], check=False)
        except OSError:
            pass


def ensure_amms_fix() -> None:
    # Check if lynx_amms_fix is already loaded
    try:
        with open("/proc/modules") as f:
            if "lynx_amms_fix" in f.read():
                log("lynx_amms_fix already loaded.")
                return
    except OSError:
        pass

    log("Resolving kallsyms addresses for AMMS v2 patch...")
    sib_addr = None
    smem_addr = None
    try:
        with open("/proc/kallsyms") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 3:
                    if parts[2] == "sib_info" and "[ccci_util_lib]" in line:
                        sib_addr = f"0x{parts[0]}"
                    elif parts[2] == "smem_amms_pos_size" and "[ccci_util_lib]" in line:
                        smem_addr = f"0x{parts[0]}"
    except OSError as exc:
        log(f"Failed reading /proc/kallsyms: {exc}")
        return

    if sib_addr and smem_addr:
        mod_path = Path("/var/lib/noobia/modules/lynx_amms_fix.ko")
        if not mod_path.exists():
            mod_path = Path("/tmp/lynx_amms_fix.ko")
        if mod_path.exists():
            log(f"Inserting {mod_path} with sib_info_addr={sib_addr} smem_amms_pos_size_addr={smem_addr}...")
            subprocess.run([
                "insmod", str(mod_path),
                f"sib_info_addr={sib_addr}",
                f"smem_amms_pos_size_addr={smem_addr}",
            ], check=False)
        else:
            log("Warning: lynx_amms_fix.ko not found!")
    else:
        log(f"Warning: could not resolve both addresses (sib={sib_addr}, smem={smem_addr})")


def ensure_remoteproc() -> None:
    log("Ensuring remoteproc SCP is running...")
    fw_dir = Path("/lib/firmware")
    fw_dir.mkdir(parents=True, exist_ok=True)
    scp_fw = fw_dir / "remoteproc_scp"
    src_fw = Path("/usr/local/lib/lynx/camera-fw/remoteproc_scp")
    if src_fw.exists() and not scp_fw.exists():
        try:
            scp_fw.symlink_to(src_fw)
        except OSError:
            pass

    rproc_state = Path("/sys/class/remoteproc/remoteproc1/state")
    if rproc_state.exists():
        try:
            state = rproc_state.read_text().strip()
            if state != "running":
                log(f"Starting remoteproc1 (current state: {state})...")
                rproc_state.write_text("start")
        except Exception as exc:
            log(f"remoteproc1 state check/start notice: {exc}")


def restart_daemons() -> None:
    log("Checking CCCI daemons...")
    # Kill any existing ccci daemons to reset state
    subprocess.run(["killall", "-9", "ccci_mdinit", "ccci_rpcd"], check=False)
    time.sleep(0.5)

    bin_dir = "/var/lib/noobia/ccci/bin"
    lib_dir = "/var/lib/noobia/ccci/lib64"
    linker = f"{bin_dir}/linker64"
    shim = f"{lib_dir}/liblynx_props.so"

    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = lib_dir
    env["LD_PRELOAD"] = shim

    log("Starting ccci_rpcd 0...")
    with open("/var/log/ccci_rpcd.log", "a") as out:
        subprocess.Popen(
            [linker, f"{bin_dir}/ccci_rpcd", "0"],
            env=env,
            stdout=out,
            stderr=out,
            start_new_session=True,
        )

    time.sleep(0.5)

    log("Starting ccci_mdinit 0...")
    with open("/var/log/ccci_mdinit.log", "a") as out:
        subprocess.Popen(
            [linker, f"{bin_dir}/ccci_mdinit", "0"],
            env=env,
            stdout=out,
            stderr=out,
            start_new_session=True,
        )


def wait_for_modem(timeout: int = 25) -> bool:
    log(f"Waiting up to {timeout}s for modem boot (md1:4 / READY)...")
    boot_path = Path("/sys/kernel/ccci/boot")
    start = time.monotonic()
    last_state = ""
    while time.monotonic() - start < timeout:
        if boot_path.exists():
            try:
                state = boot_path.read_text().strip()
                if state != last_state:
                    log(f"Baseband status: {state}")
                    last_state = state
                if "md1:4" in state:
                    return True
            except OSError:
                pass
        time.sleep(1)
    return False


def send_at(fd: int, cmd: str, timeout: float = 3.0) -> list[str]:
    # Flush
    while True:
        r, _, _ = select.select([fd], [], [], 0.05)
        if not r:
            break
        try:
            os.read(fd, 4096)
        except OSError:
            break

    cmd_bytes = (cmd.strip() + "\r\n").encode("utf-8")
    try:
        os.write(fd, cmd_bytes)
    except OSError as exc:
        log(f"write error on {cmd}: {exc}")
        return []

    lines: list[str] = []
    buf = b""
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        r, _, _ = select.select([fd], [], [], 0.1)
        if not r:
            continue
        try:
            chunk = os.read(fd, 1024)
        except Exception:
            break
        if not chunk:
            break
        buf += chunk
        while b"\n" in buf:
            line_bytes, buf = buf.split(b"\n", 1)
            line = line_bytes.decode("utf-8", errors="replace").strip()
            if line:
                lines.append(line)
                if line in ("OK", "ERROR") or line.startswith("+CME ERROR:"):
                    return lines
    return lines


def configure_cellular(pin: str = "0000", apn: str = "internet.vivacom.bg") -> bool:
    tty_path = "/dev/ttyC0"
    if not Path(tty_path).exists():
        log(f"Error: {tty_path} not found.")
        return False

    log(f"Opening AT terminal on {tty_path}...")
    try:
        fd = os.open(tty_path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    except Exception as exc:
        log(f"Failed to open {tty_path}: {exc}")
        return False

    try:
        log("Testing AT...")
        res = send_at(fd, "AT")
        log(f"AT -> {res}")

        log("Activating full radio (AT+CFUN=1)...")
        res = send_at(fd, "AT+CFUN=1")
        log(f"CFUN=1 -> {res}")
        time.sleep(1.0)

        log("Checking PIN status (AT+CPIN?)...")
        res = send_at(fd, "AT+CPIN?")
        log(f"CPIN? -> {res}")
        if any("SIM PIN" in l for l in res):
            log(f"Unlocking SIM with PIN {pin}...")
            res = send_at(fd, f'AT+CPIN="{pin}"')
            log(f"CPIN result -> {res}")
            time.sleep(2.0)

        log(f"Configuring APN: {apn}...")
        res = send_at(fd, f'AT+CGDCONT=1,"IP","{apn}"')
        log(f"CGDCONT -> {res}")

        log("Attaching to packet domain (AT+CGATT=1)...")
        res = send_at(fd, "AT+CGATT=1", timeout=5.0)
        log(f"CGATT -> {res}")

        log("Activating PDP context (AT+CGACT=1,1)...")
        res = send_at(fd, "AT+CGACT=1,1", timeout=8.0)
        log(f"CGACT -> {res}")

        log("Querying assigned IP (AT+CGPADDR=1)...")
        res = send_at(fd, "AT+CGPADDR=1")
        log(f"CGPADDR -> {res}")

        ip_addr = None
        for l in res:
            if "+CGPADDR:" in l:
                parts = l.split(",")
                if len(parts) > 1:
                    ip_addr = parts[1].replace('"', '').strip()

        if ip_addr and re.match(r"^\d+\.\d+\.\d+\.\d+$", ip_addr):
            log(f"Acquired Cellular IP: {ip_addr}")
            # Configure network interface
            subprocess.run(["ip", "link", "set", "ccmni0", "up"], check=False)
            # Remove any stale IP on ccmni0
            subprocess.run(["ip", "addr", "flush", "dev", "ccmni0"], check=False)
            subprocess.run(["ip", "addr", "add", f"{ip_addr}/32", "dev", "ccmni0"], check=False)
            # Routing table 100 for cellular
            subprocess.run(["ip", "rule", "del", "from", ip_addr, "table", "100"], check=False)
            subprocess.run(["ip", "rule", "add", "from", ip_addr, "table", "100"], check=False)
            subprocess.run(["ip", "route", "replace", "default", "dev", "ccmni0", "table", "100"], check=False)
            log("Network interface ccmni0 successfully configured!")
            return True
        else:
            log(f"Notice: No valid IPv4 returned yet ({ip_addr}).")
            return False

    finally:
        os.close(fd)


def main() -> int:
    setup_partitions()
    setup_mounts()
    ensure_remoteproc()
    ensure_amms_fix()
    restart_daemons()
    ready = wait_for_modem(timeout=20)
    if not ready:
        log("Modem did not reach md1:4 within timeout. Checking status...")
    configured = configure_cellular(pin="0000", apn="internet.vivacom.bg")
    log(f"Cellular bringup completed: ready={ready}, configured={configured}")
    return 0 if configured else 1


if __name__ == "__main__":
    sys.exit(main())
