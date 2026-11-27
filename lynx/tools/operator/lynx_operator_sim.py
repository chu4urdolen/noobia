#!/usr/bin/env python3
"""Lynx Operator SIM and Cellular Registration Tool (Class O).

This tool is strictly an Operator-Only (Class O) tool for Noobia operators on Nexus.
It implements tasks LNX-01, LNX-02, and LNX-03 from Rose's development backlog:
  * LNX-01: SIM initialization and PIN management (PIN status, unlock, ICCID, IMSI)
  * LNX-02: Cellular registration and carrier configuration (CREG, COPS, signal)
  * LNX-03: Mobile internet, APN and IP configuration (CGDCONT, context)

This tool must NEVER be exposed in autonomous agent tool catalogues or MCP.
Operators and developer agents (Aria / Banshee) run it to interact with the
MediaTek MT6983 cellular baseband (MD1) on OnePlus Nord 3 (Lynx).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import select
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

DEFAULT_HOST = "192.168.100.107"
DEFAULT_PORT = 2222
DEFAULT_USER = "root"
DEFAULT_TTY = "/dev/ttyC0"
DEFAULT_CCCI_IOCTL0 = "/dev/ccci_ioctl0"
DEFAULT_CCCI_BOOT = "/sys/kernel/ccci/boot"

# CME ERROR mappings for operator clarity
CME_ERRORS = {
    "10": "SIM not inserted",
    "11": "SIM PIN required",
    "12": "SIM PUK required",
    "13": "SIM failure",
    "14": "SIM busy",
    "15": "SIM wrong",
    "16": "Incorrect password (PIN)",
    "17": "SIM PIN2 required",
    "18": "SIM PUK2 required",
    "30": "No network service",
    "32": "Network not allowed - emergency calls only",
}

# CREG/CEREG status codes
REG_STATUS = {
    0: "not registered, not searching",
    1: "registered, home network",
    2: "not registered, searching",
    3: "registration denied",
    4: "unknown",
    5: "registered, roaming",
}


def is_local_lynx() -> bool:
    """Return True if executing natively on the Lynx phone."""
    try:
        nodename = os.uname().nodename
        if "lynx" in nodename.lower():
            return True
    except (AttributeError, OSError):
        pass
    return Path("/sys/kernel/ccci").is_dir()


class ModemSerial:
    """Direct AT command session handler for /dev/ttyC0 on device."""

    def __init__(self, tty_path: str = DEFAULT_TTY, timeout: float = 5.0):
        self.tty_path = tty_path
        self.timeout = timeout
        self.fd: Optional[int] = None

    def __enter__(self):
        try:
            self.fd = os.open(self.tty_path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        except OSError as exc:
            raise RuntimeError(f"Failed to open AT port {self.tty_path}: {exc}") from exc
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None

    def send_at(self, command: str, wait_timeout: Optional[float] = None) -> List[str]:
        """Send an AT command and return response lines until OK, ERROR, or timeout."""
        if self.fd is None:
            raise RuntimeError("AT port is not open")

        timeout = wait_timeout if wait_timeout is not None else self.timeout
        cmd_bytes = (command.strip() + "\r\n").encode("utf-8")

        # Flush any pending incoming data
        while True:
            r, _, _ = select.select([self.fd], [], [], 0.05)
            if not r:
                break
            try:
                os.read(self.fd, 4096)
            except OSError:
                break

        # Write command
        os.write(self.fd, cmd_bytes)

        lines: List[str] = []
        buf = b""
        start_time = time.monotonic()

        while time.monotonic() - start_time < timeout:
            r, _, _ = select.select([self.fd], [], [], 0.2)
            if not r:
                continue
            try:
                chunk = os.read(self.fd, 1024)
            except BlockingIOError:
                continue
            except OSError as exc:
                lines.append(f"ERROR: read exception: {exc}")
                break

            if not chunk:
                break

            buf += chunk
            while b"\n" in buf:
                line_bytes, buf = buf.split(b"\n", 1)
                line = line_bytes.decode("utf-8", errors="replace").strip()
                if line:
                    lines.append(line)
                    if line in ("OK", "ERROR") or line.startswith("+CME ERROR:") or line.startswith("+CMS ERROR:"):
                        return lines

        if not lines:
            lines.append("TIMEOUT: no response from modem")
        return lines


def run_remote_python(code: str, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, user: str = DEFAULT_USER) -> Tuple[int, str, str]:
    """Execute Python code on the remote Lynx device via SSH."""
    cmd = [
        "ssh", "-p", str(port), f"{user}@{host}",
        "python3", "-c", code
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return proc.returncode, proc.stdout, proc.stderr


def get_ccci_boot_state() -> str:
    """Read /sys/kernel/ccci/boot directly on device."""
    try:
        return Path(DEFAULT_CCCI_BOOT).read_text(encoding="utf-8").strip()
    except Exception as exc:
        return f"unknown ({exc})"


def parse_cpin_response(lines: List[str]) -> Dict[str, Any]:
    """Parse AT+CPIN? response."""
    result: Dict[str, Any] = {"raw": lines, "status": "UNKNOWN", "ready": False, "error": None}
    for line in lines:
        if line.startswith("+CPIN:"):
            state = line.split(":", 1)[1].strip()
            result["status"] = state
            result["ready"] = (state == "READY")
        elif line.startswith("+CME ERROR:"):
            code = line.split(":", 1)[1].strip()
            result["error"] = CME_ERRORS.get(code, f"CME ERROR {code}")
            result["status"] = "ERROR"
    return result


def parse_cops_response(lines: List[str]) -> Dict[str, Any]:
    """Parse AT+COPS? response."""
    result: Dict[str, Any] = {"raw": lines, "mode": None, "format": None, "operator": None, "act": None}
    for line in lines:
        if line.startswith("+COPS:"):
            # Format: +COPS: <mode>[,<format>,"<oper>"[,<Act>]]
            payload = line.split(":", 1)[1].strip()
            parts = re.split(r",(?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)", payload)
            if parts:
                try:
                    result["mode"] = int(parts[0])
                except ValueError:
                    pass
            if len(parts) > 1:
                try:
                    result["format"] = int(parts[1])
                except ValueError:
                    pass
            if len(parts) > 2:
                result["operator"] = parts[2].strip('"')
            if len(parts) > 3:
                try:
                    result["act"] = int(parts[3])  # 0=GSM, 2=UTRAN, 7=LTE, 12=NR5G
                except ValueError:
                    pass
    return result


def parse_csq_response(lines: List[str]) -> Dict[str, Any]:
    """Parse AT+CSQ response."""
    result: Dict[str, Any] = {"raw": lines, "rssi": None, "ber": None, "dbm": None}
    for line in lines:
        if line.startswith("+CSQ:"):
            payload = line.split(":", 1)[1].strip()
            parts = [p.strip() for p in payload.split(",")]
            if len(parts) >= 2:
                try:
                    rssi = int(parts[0])
                    ber = int(parts[1])
                    result["rssi"] = rssi
                    result["ber"] = ber
                    if rssi == 99:
                        result["dbm"] = "not detectable"
                    elif 0 <= rssi <= 31:
                        result["dbm"] = -113 + (rssi * 2)
                except ValueError:
                    pass
    return result


def parse_reg_response(lines: List[str], prefix: str = "+CREG:") -> Dict[str, Any]:
    """Parse +CREG / +CGREG / +CEREG response."""
    result: Dict[str, Any] = {"raw": lines, "n": None, "stat": None, "description": "unknown"}
    for line in lines:
        if line.startswith(prefix):
            payload = line.split(":", 1)[1].strip()
            parts = [p.strip() for p in payload.split(",")]
            if len(parts) == 1:
                try:
                    stat = int(parts[0])
                    result["stat"] = stat
                    result["description"] = REG_STATUS.get(stat, "unknown")
                except ValueError:
                    pass
            elif len(parts) >= 2:
                try:
                    result["n"] = int(parts[0])
                    stat = int(parts[1])
                    result["stat"] = stat
                    result["description"] = REG_STATUS.get(stat, "unknown")
                except ValueError:
                    pass
    return result


def op_status_local() -> Dict[str, Any]:
    """Run status probe on local Lynx device."""
    ccci_boot = get_ccci_boot_state()
    tty_present = Path(DEFAULT_TTY).is_char_device() if hasattr(Path, "is_char_device") else os.path.exists(DEFAULT_TTY)

    status_data: Dict[str, Any] = {
        "device": "lynx",
        "ccci_boot": ccci_boot,
        "tty_present": tty_present,
        "modem_ready": ("md1:4" in ccci_boot),
        "at_communicating": False,
        "sim_status": None,
    }

    if not tty_present:
        status_data["note"] = f"AT character device {DEFAULT_TTY} is not present (modem not booted to READY state)."
        return status_data

    try:
        with ModemSerial(DEFAULT_TTY, timeout=3.0) as modem:
            cpin_lines = modem.send_at("AT+CPIN?")
            status_data["at_communicating"] = True
            status_data["sim_status"] = parse_cpin_response(cpin_lines)
    except Exception as exc:
        status_data["error"] = str(exc)

    return status_data


def op_sim_info_local() -> Dict[str, Any]:
    """Query SIM identifiers (ICCID, IMSI, MSISDN) locally."""
    info: Dict[str, Any] = {
        "iccid": None,
        "imsi": None,
        "msisdn": None,
        "errors": []
    }
    with ModemSerial(DEFAULT_TTY, timeout=4.0) as modem:
        # 1. ICCID query (AT+CCID or AT+CRSM=176,12258,0,0,10)
        lines = modem.send_at("AT+CCID")
        for line in lines:
            if line.startswith("+CCID:") or line.startswith("+QCCID:"):
                info["iccid"] = line.split(":", 1)[1].strip().strip('"')
            elif re.fullmatch(r"[0-9]{18,20}[0-9A-Fa-f]?", line):
                info["iccid"] = line.strip()

        if not info["iccid"]:
            # Fallback to EF_ICCID read via CRSM
            crsm_lines = modem.send_at("AT+CRSM=176,12258,0,0,10")
            for line in crsm_lines:
                if line.startswith("+CRSM:"):
                    # +CRSM: 144,0,"<hex>"
                    m = re.search(r'"([0-9A-Fa-f]{20})"', line)
                    if m:
                        raw_hex = m.group(1)
                        # Swap nibbles
                        swapped = "".join(raw_hex[i+1] + raw_hex[i] for i in range(0, len(raw_hex), 2))
                        info["iccid"] = swapped.rstrip("Ff")

        # 2. IMSI query (AT+CIMI)
        cimi_lines = modem.send_at("AT+CIMI")
        for line in cimi_lines:
            if re.fullmatch(r"[0-9]{14,15}", line.strip()):
                info["imsi"] = line.strip()

        # 3. Phone number / MSISDN (AT+CNUM)
        cnum_lines = modem.send_at("AT+CNUM")
        for line in cnum_lines:
            if line.startswith("+CNUM:"):
                info["msisdn"] = line.split(":", 1)[1].strip()

    return info


def op_unlock_pin_local(pin: str) -> Dict[str, Any]:
    """Send AT+CPIN="<pin>" to unlock SIM."""
    with ModemSerial(DEFAULT_TTY, timeout=6.0) as modem:
        lines = modem.send_at(f'AT+CPIN="{pin}"')
        parsed = parse_cpin_response(lines)
        if "OK" in lines:
            parsed["unlocked"] = True
            parsed["message"] = "PIN accepted; SIM unlocked."
        else:
            parsed["unlocked"] = False
            parsed["message"] = parsed.get("error") or "Failed to unlock SIM."
        return parsed


def op_carrier_status_local() -> Dict[str, Any]:
    """Check carrier registration, signal strength, and operator."""
    result: Dict[str, Any] = {}
    with ModemSerial(DEFAULT_TTY, timeout=5.0) as modem:
        cops = modem.send_at("AT+COPS?")
        result["operator"] = parse_cops_response(cops)

        creg = modem.send_at("AT+CREG?")
        result["cs_registration"] = parse_reg_response(creg, "+CREG:")

        cereg = modem.send_at("AT+CEREG?")
        result["eps_registration"] = parse_reg_response(cereg, "+CEREG:")

        csq = modem.send_at("AT+CSQ")
        result["signal"] = parse_csq_response(csq)

    return result


def op_set_apn_local(apn: str, cid: int = 1, proto: str = "IP") -> Dict[str, Any]:
    """Define PDP context with APN."""
    with ModemSerial(DEFAULT_TTY, timeout=5.0) as modem:
        cmd = f'AT+CGDCONT={cid},"{proto}","{apn}"'
        lines = modem.send_at(cmd)
        ok = "OK" in lines
        return {
            "command": cmd,
            "success": ok,
            "apn": apn,
            "cid": cid,
            "proto": proto,
            "raw": lines
        }


def op_send_raw_at_local(cmd_str: str) -> List[str]:
    """Send raw AT command."""
    with ModemSerial(DEFAULT_TTY, timeout=5.0) as modem:
        return modem.send_at(cmd_str)


# Dispatcher when invoked from Nexus host (over SSH)
def run_remote(command_name: str, *args: str, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> Dict[str, Any]:
    """Run command on Lynx by invoking this script on the phone."""
    script_content = Path(__file__).read_text(encoding="utf-8")
    
    # We pipe the script to python3 on Lynx and pass arguments
    args_quoted = " ".join(f"'{a}'" for a in (command_name, *args))
    remote_cmd = (
        f"python3 - --local {args_quoted}"
        if port == 2222
        else f"chroot /run/lynx/persistent-alpine python3 - --local {args_quoted}"
    )
    ssh_cmd = [
        "ssh",
        "-i", "/noobia/lynx/secrets/nexus_lynx_ed25519",
        "-o", "IdentitiesOnly=yes",
        "-o", "StrictHostKeyChecking=no",
        "-p", str(port),
        f"root@{host}",
        remote_cmd
    ]
    proc = subprocess.run(ssh_cmd, input=script_content, capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        return {
            "ok": False,
            "exit_code": proc.returncode,
            "error": proc.stderr.strip() or proc.stdout.strip() or "SSH execution failed"
        }
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {
            "ok": True,
            "raw_output": proc.stdout.strip(),
            "stderr": proc.stderr.strip()
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lynx-operator-sim",
        description="Class O Operator SIM and Cellular Registration Tool for OnePlus Nord 3 (Lynx)."
    )
    parser.add_argument("--local", action="store_true", help="Force local execution on phone.")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Lynx IP address (default: {DEFAULT_HOST}).")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"SSH port (default: {DEFAULT_PORT}).")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # status
    subparsers.add_parser("status", help="Probe modem boot state and SIM status.")

    # sim-info
    subparsers.add_parser("sim-info", help="Query ICCID, IMSI, and subscriber information.")

    # unlock <PIN>
    p_unlock = subparsers.add_parser("unlock", help="Unlock SIM card with PIN.")
    p_unlock.add_argument("pin", help="SIM PIN (typically 4 digits).")

    # carrier
    subparsers.add_parser("carrier", help="Query serving carrier, registration, and signal strength.")

    # apn <apn_name> [--cid 1] [--proto IP]
    p_apn = subparsers.add_parser("apn", help="Configure APN for mobile internet.")
    p_apn.add_argument("apn_name", help="Access Point Name (e.g., internet, fast.t-mobile.com).")
    p_apn.add_argument("--cid", type=int, default=1, help="Context ID (default: 1).")
    p_apn.add_argument("--proto", default="IP", choices=["IP", "IPV6", "IPV4V6"], help="Protocol (default: IP).")

    # at <command>
    p_at = subparsers.add_parser("at", help="Send arbitrary raw AT command to modem.")
    p_at.add_argument("at_cmd", help="AT command string (e.g. AT+CSQ, AT+COPS=?).")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    is_local = args.local or is_local_lynx()

    if not is_local:
        # Running from Nexus: forward command to Lynx
        extra_args: List[str] = []
        if args.command == "unlock":
            extra_args = [args.pin]
        elif args.command == "apn":
            extra_args = [args.apn_name, "--cid", str(args.cid), "--proto", args.proto]
        elif args.command == "at":
            extra_args = [args.at_cmd]

        result = run_remote(args.command, *extra_args, host=args.host, port=args.port)
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok", True) else 1

    # Local execution on Lynx
    res: Any = {}
    try:
        if args.command == "status":
            res = op_status_local()
        elif args.command == "sim-info":
            res = op_sim_info_local()
        elif args.command == "unlock":
            res = op_unlock_pin_local(args.pin)
        elif args.command == "carrier":
            res = op_carrier_status_local()
        elif args.command == "apn":
            res = op_set_apn_local(args.apn_name, cid=args.cid, proto=args.proto)
        elif args.command == "at":
            res = {"command": args.at_cmd, "lines": op_send_raw_at_local(args.at_cmd)}
        else:
            res = {"error": f"Unknown command: {args.command}"}
    except Exception as exc:
        res = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
