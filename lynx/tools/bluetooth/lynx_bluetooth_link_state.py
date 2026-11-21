#!/usr/bin/env python3
"""Agent-facing read-only Bluetooth link-state report parser and gate.

Designed on top of BT_STATUS (NRP 393) and lynx_bluetoothd.py.
Reports controller enumeration, power state, OpenRC supervisor health,
and active peer connection topologies without issuing radio actuation,
service start/stop commands, or device tree modifications.
"""

from dataclasses import dataclass, field
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict, List, Optional

DEFAULT_LYNX_HOST = "192.168.100.107"
DEFAULT_LYNX_PORT = 2222
SSH_TIMEOUT = 8


@dataclass
class ConnectedPeer:
    mac_address: str
    device_name: Optional[str] = None
    connected: bool = True
    paired: bool = False
    rssi_dbm: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mac_address": self.mac_address,
            "device_name": self.device_name,
            "connected": self.connected,
            "paired": self.paired,
            "rssi_dbm": self.rssi_dbm,
        }


@dataclass
class BluetoothLinkStateVerdict:
    status: str  # "RADIO_OFF", "READY_UNLINKED", "CONNECTED", "DEGRADED", "UNSAFE_CONFIG", "ABSENT"
    is_valid: bool
    radio_powered: bool
    supervisor_running: bool
    active_connections_count: int
    summary: str
    connected_peers: List[Dict[str, Any]] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)
    failures: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "is_valid": self.is_valid,
            "radio_powered": self.radio_powered,
            "supervisor_running": self.supervisor_running,
            "active_connections_count": self.active_connections_count,
            "summary": self.summary,
            "connected_peers": self.connected_peers,
            "details": self.details,
            "failures": self.failures,
        }


def parse_bluetoothctl_show(output: str) -> Dict[str, Any]:
    """Parse output of 'bluetoothctl show' into structured controller properties."""
    info: Dict[str, Any] = {
        "controller_mac": None,
        "powered": False,
        "discoverable": False,
        "pairable": False,
        "name": None,
    }
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("Controller "):
            parts = line.split()
            if len(parts) >= 2:
                info["controller_mac"] = parts[1]
        elif line.startswith("Powered:"):
            info["powered"] = "yes" in line.lower()
        elif line.startswith("Discoverable:"):
            info["discoverable"] = "yes" in line.lower()
        elif line.startswith("Pairable:"):
            info["pairable"] = "yes" in line.lower()
        elif line.startswith("Name:"):
            info["name"] = line.split(":", 1)[1].strip()
    return info


def evaluate_bluetooth_link_state(
    data: Optional[Dict[str, Any]],
) -> BluetoothLinkStateVerdict:
    """Pure evaluation function classifying a Bluetooth telemetry snapshot."""
    if not data:
        return BluetoothLinkStateVerdict(
            status="ABSENT",
            is_valid=False,
            radio_powered=False,
            supervisor_running=False,
            active_connections_count=0,
            summary="Link-state data is missing or empty",
            failures=["missing_data"],
        )

    failures: List[str] = []
    details: Dict[str, Any] = {}

    # 1. Runlevel Safety Check
    runlevel_default = data.get("runlevel_default_services", [])
    if "lynx-bluetooth" in runlevel_default:
        failures.append("lynx-bluetooth_in_default_runlevel_forbidden")

    # 2. Kernel & Hardware Layer
    modules = data.get("modules", [])
    bt_driver_loaded = "bt_drv_6983" in modules
    wmt_loaded = "wmt_drv" in modules or "btif_drv" in modules
    stpbt_exists = data.get("device_nodes", {}).get("stpbt", False)
    hci0_exists = data.get("hci_interfaces", {}).get("hci0", False)

    details["hardware"] = {
        "bt_driver_loaded": bt_driver_loaded,
        "stpbt_node_present": stpbt_exists,
        "hci0_interface_present": hci0_exists,
    }

    # 3. OpenRC Supervisor & Services Layer
    services = data.get("services", {})
    supervisor_status = services.get("lynx-bluetooth", "stopped")
    supervisor_running = supervisor_status == "started"
    bluez_running = services.get("bluetooth", "stopped") == "started"
    dbus_running = services.get("dbus", "stopped") == "started"
    runtime_ready_flag = data.get("runtime_ready_flag", False)

    details["services"] = {
        "supervisor_status": supervisor_status,
        "bluez_status": services.get("bluetooth", "stopped"),
        "dbus_status": services.get("dbus", "stopped"),
        "runtime_ready_flag": runtime_ready_flag,
    }

    # 4. Controller State & Connected Devices
    controller = data.get("controller", {})
    powered = controller.get("powered", False)
    pairable = controller.get("pairable", False)
    if pairable:
        failures.append("pairable_mode_is_active_expected_disabled")

    peers_raw = data.get("connected_devices", [])
    peers: List[ConnectedPeer] = []
    for p in peers_raw:
        if isinstance(p, dict) and p.get("mac_address"):
            peers.append(
                ConnectedPeer(
                    mac_address=p["mac_address"],
                    device_name=p.get("device_name"),
                    connected=p.get("connected", True),
                    paired=p.get("paired", False),
                    rssi_dbm=p.get("rssi_dbm"),
                )
            )

    peer_dicts = [p.to_dict() for p in peers]
    conn_count = len([p for p in peers if p.connected])

    details["controller"] = controller
    details["connected_peers_count"] = conn_count

    # 5. Security & Battery Safety Policy
    battery = data.get("battery", {})
    cap = battery.get("capacity_percent")
    if cap is not None and cap < 15 and powered:
        failures.append(f"radio_powered_under_low_battery_threshold_{cap}%")

    if failures:
        return BluetoothLinkStateVerdict(
            status="UNSAFE_CONFIG" if any("runlevel" in f or "pairable" in f for f in failures) else "DEGRADED",
            is_valid=False,
            radio_powered=powered,
            supervisor_running=supervisor_running,
            active_connections_count=conn_count,
            summary=f"Bluetooth state validation failed: {', '.join(failures)}",
            connected_peers=peer_dicts,
            details=details,
            failures=failures,
        )

    # Classification logic
    if not hci0_exists and not supervisor_running and not powered:
        return BluetoothLinkStateVerdict(
            status="RADIO_OFF",
            is_valid=True,
            radio_powered=False,
            supervisor_running=False,
            active_connections_count=0,
            summary="Bluetooth radio is completely powered off and service is stopped (quiescent)",
            connected_peers=[],
            details=details,
            failures=[],
        )
    elif supervisor_running and runtime_ready_flag and powered and hci0_exists:
        if conn_count > 0:
            return BluetoothLinkStateVerdict(
                status="CONNECTED",
                is_valid=True,
                radio_powered=True,
                supervisor_running=True,
                active_connections_count=conn_count,
                summary=f"Bluetooth radio active with {conn_count} connected peer(s)",
                connected_peers=peer_dicts,
                details=details,
                failures=[],
            )
        else:
            return BluetoothLinkStateVerdict(
                status="READY_UNLINKED",
                is_valid=True,
                radio_powered=True,
                supervisor_running=True,
                active_connections_count=0,
                summary="Bluetooth radio and GATT service ready, awaiting peer connection",
                connected_peers=[],
                details=details,
                failures=[],
            )
    else:
        # Inconsistent state (e.g. hci0 up without supervisor or vice versa)
        return BluetoothLinkStateVerdict(
            status="DEGRADED",
            is_valid=False,
            radio_powered=powered,
            supervisor_running=supervisor_running,
            active_connections_count=conn_count,
            summary="Bluetooth state is degraded (inconsistent supervisor or controller state)",
            connected_peers=peer_dicts,
            details=details,
            failures=["inconsistent_service_or_controller_state"],
        )


def collect_live_bluetooth_link_state(
    host: str = DEFAULT_LYNX_HOST,
    port: int = DEFAULT_LYNX_PORT,
    timeout: int = SSH_TIMEOUT,
) -> Dict[str, Any]:
    """Execute bounded read-only inspection of Bluetooth link state on Lynx."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    known_hosts = repo_root / "secrets/lynx_known_hosts"
    key_file = repo_root / "secrets/nexus_lynx_ed25519"

    sh_script = r"""
cat /proc/sys/kernel/random/boot_id 2>/dev/null || echo "UNKNOWN_BOOT"
echo "===RUNLEVEL==="
rc-update show default 2>/dev/null
echo "===MODULES==="
lsmod
echo "===DEVICES==="
test -e /dev/stpbt && echo "STPBT_EXISTS" || echo "STPBT_ABSENT"
test -d /sys/class/bluetooth/hci0 && echo "HCI0_EXISTS" || echo "HCI0_ABSENT"
test -f /run/lynx/bluetooth/ready && echo "READY_FLAG_EXISTS" || echo "READY_FLAG_ABSENT"
echo "===SERVICES==="
rc-service lynx-bluetooth status 2>&1
echo "---"
rc-service bluetooth status 2>&1
echo "---"
rc-service dbus status 2>&1
echo "===BTCTL_SHOW==="
bluetoothctl show 2>/dev/null || echo "BTCTL_FAILED"
echo "===BTCTL_DEVICES==="
bluetoothctl devices Connected 2>/dev/null || echo "NO_DEVICES"
echo "===BATTERY==="
cat /sys/class/power_supply/battery/capacity 2>/dev/null || echo "0"
"""
    cmd = [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", "IdentitiesOnly=yes",
        "-o", "StrictHostKeyChecking=yes",
        "-o", "GlobalKnownHostsFile=/dev/null",
        "-o", "HostKeyAlias=lynx",
        "-o", f"UserKnownHostsFile={known_hosts}",
        "-o", "ConnectTimeout=5",
        "-i", str(key_file),
        "-p", str(port),
        f"root@{host}",
        "sh", "-s",
    ]

    res = subprocess.run(cmd, input=sh_script, capture_output=True, text=True, timeout=timeout)
    if res.returncode != 0:
        return {"error": f"SSH returned {res.returncode}: {res.stderr.strip()}"}

    out = res.stdout
    parts = out.split("===RUNLEVEL===")
    boot_id = parts[0].strip()

    p_run = parts[1].split("===MODULES===")
    runlevel_default = [line.split("|")[0].strip() for line in p_run[0].splitlines() if line.strip()]

    p_mod = p_run[1].split("===DEVICES===")
    modules = [line.split()[0] for line in p_mod[0].splitlines() if line.split()]

    p_dev = p_mod[1].split("===SERVICES===")
    dev_lines = p_dev[0].strip().splitlines()
    stpbt = any("STPBT_EXISTS" in l for l in dev_lines)
    hci0 = any("HCI0_EXISTS" in l for l in dev_lines)
    ready_flag = any("READY_FLAG_EXISTS" in l for l in dev_lines)

    p_srv = p_dev[1].split("===BTCTL_SHOW===")
    srv_blocks = p_srv[0].split("---")
    lynx_bt_status = "started" if "status: started" in srv_blocks[0].lower() else "stopped"
    bluez_status = "started" if len(srv_blocks) > 1 and "status: started" in srv_blocks[1].lower() else "stopped"
    dbus_status = "started" if len(srv_blocks) > 2 and "status: started" in srv_blocks[2].lower() else "stopped"

    p_show = p_srv[1].split("===BTCTL_DEVICES===")
    btctl_show_text = p_show[0].strip()
    controller_info = parse_bluetoothctl_show(btctl_show_text)

    p_conn = p_show[1].split("===BATTERY===")
    conn_lines = p_conn[0].strip().splitlines()
    connected_devices = []
    for line in conn_lines:
        line = line.strip()
        if line.startswith("Device "):
            parts_d = line.split(" ", 2)
            if len(parts_d) >= 2:
                connected_devices.append({
                    "mac_address": parts_d[1],
                    "device_name": parts_d[2] if len(parts_d) > 2 else None,
                    "connected": True,
                })

    bat_str = p_conn[1].strip() if len(p_conn) > 1 else "0"
    try:
        battery_cap = int(bat_str)
    except ValueError:
        battery_cap = 0

    return {
        "platform": "OnePlus Nord 3 5G CPH2493 (MT6983 / 22823 'Vitamin')",
        "boot_id": boot_id,
        "runlevel_default_services": runlevel_default,
        "modules": modules,
        "device_nodes": {"stpbt": stpbt},
        "hci_interfaces": {"hci0": hci0},
        "runtime_ready_flag": ready_flag,
        "services": {
            "lynx-bluetooth": lynx_bt_status,
            "bluetooth": bluez_status,
            "dbus": dbus_status,
        },
        "controller": controller_info,
        "connected_devices": connected_devices,
        "battery": {"capacity_percent": battery_cap},
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Agent-facing read-only Bluetooth link-state report parser"
    )
    parser.add_argument(
        "fixture",
        type=Path,
        nargs="?",
        default=None,
        help="Path to link-state JSON fixture",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Query running Bluetooth link-state on Lynx via SSH (requires --allow-live)",
    )
    parser.add_argument(
        "--allow-live",
        action="store_true",
        help="Explicit confirmation to query running Bluetooth link state",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_LYNX_HOST,
        help="Lynx host IP for live query",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_LYNX_PORT,
        help="Lynx SSH port for live query",
    )
    args = parser.parse_args()

    if args.live:
        if not args.allow_live:
            err = {"error": "refusing live execution without both --live and --allow-live"}
            print(json.dumps(err, indent=2), file=sys.stderr)
            sys.exit(2)

        data = collect_live_bluetooth_link_state(host=args.host, port=args.port)
        if "error" in data:
            print(json.dumps({"status": "FAILED", "error": data["error"]}, indent=2))
            sys.exit(1)

        verdict = evaluate_bluetooth_link_state(data)
        print(json.dumps(verdict.to_dict(), indent=2))
        sys.exit(0 if verdict.is_valid else 1)

    if not args.fixture:
        parser.print_help(file=sys.stderr)
        sys.exit(2)

    if not args.fixture.exists():
        print(f"Error: file not found: {args.fixture}", file=sys.stderr)
        sys.exit(2)

    try:
        data = json.loads(args.fixture.read_text())
    except Exception as exc:
        print(f"Error: JSON parse failed: {exc}", file=sys.stderr)
        sys.exit(1)

    verdict = evaluate_bluetooth_link_state(data)
    print(json.dumps(verdict.to_dict(), indent=2))
    sys.exit(0 if verdict.is_valid else 1)


if __name__ == "__main__":
    main()
