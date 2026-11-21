#!/usr/bin/env python3
"""Offline NCI (NFC Controller Interface) frame parser and trial receipt decoder.

Implements NCI 1.0/2.0 protocol packet parsing for the NXP SN110 NFC/eSE controller
on the OnePlus Nord 3 (CPH2493).

Decodes:
- Control Packets (Command, Response, Notification):
  - CORE_RESET (GID 0x00, OID 0x00)
  - CORE_INIT (GID 0x00, OID 0x01)
  - RF_DISCOVER (GID 0x01, OID 0x03)
  - RF_INTF_ACTIVATED (GID 0x01, OID 0x05)
  - RF_DEACTIVATE (GID 0x01, OID 0x06)
- Data Packets (MT 0x00) for logical data exchange.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple, Union

# NCI Message Types (bits 7-5)
MT_DATA = 0x00
MT_CMD = 0x01
MT_RSP = 0x02
MT_NTF = 0x03

MT_NAMES = {
    MT_DATA: "DATA",
    MT_CMD: "CMD",
    MT_RSP: "RSP",
    MT_NTF: "NTF",
}

# NCI Group Identifiers (GID, bits 3-0 of byte 0 for control packets)
GID_CORE = 0x00
GID_RF_MANAGE = 0x01
GID_NFCEE_MANAGE = 0x02
GID_PROPRIETARY = 0x0F

GID_NAMES = {
    GID_CORE: "CORE",
    GID_RF_MANAGE: "RF_MANAGE",
    GID_NFCEE_MANAGE: "NFCEE",
    GID_PROPRIETARY: "PROPRIETARY",
}

# Core Opcodes (GID 0x00)
OID_CORE_RESET = 0x00
OID_CORE_INIT = 0x01
OID_CORE_SET_CONFIG = 0x02
OID_CORE_GET_CONFIG = 0x03
OID_CORE_CONN_CREATE = 0x04
OID_CORE_CONN_CLOSE = 0x05
OID_CORE_CONN_CREDITS = 0x06
OID_CORE_GENERIC_ERROR = 0x07
OID_CORE_INTERFACE_ERROR = 0x08

# RF Management Opcodes (GID 0x01)
OID_RF_DISCOVER_MAP = 0x00
OID_RF_SET_LISTEN_MODE_ROUTING = 0x01
OID_RF_GET_LISTEN_MODE_ROUTING = 0x02
OID_RF_DISCOVER = 0x03
OID_RF_DISCOVER_SELECT = 0x04
OID_RF_INTF_ACTIVATED = 0x05
OID_RF_DEACTIVATE = 0x06
OID_RF_FIELD_INFO = 0x07
OID_RF_T3T_POLLING = 0x08
OID_RF_EE_ACTION = 0x09
OID_RF_EE_DISCOVERY_REQ = 0x0A
OID_RF_PARAMETER_UPDATE = 0x0B

OPCODE_NAMES: Dict[Tuple[int, int], str] = {
    (GID_CORE, OID_CORE_RESET): "CORE_RESET",
    (GID_CORE, OID_CORE_INIT): "CORE_INIT",
    (GID_CORE, OID_CORE_SET_CONFIG): "CORE_SET_CONFIG",
    (GID_CORE, OID_CORE_GET_CONFIG): "CORE_GET_CONFIG",
    (GID_CORE, OID_CORE_CONN_CREATE): "CORE_CONN_CREATE",
    (GID_CORE, OID_CORE_CONN_CLOSE): "CORE_CONN_CLOSE",
    (GID_CORE, OID_CORE_CONN_CREDITS): "CORE_CONN_CREDITS",
    (GID_CORE, OID_CORE_GENERIC_ERROR): "CORE_GENERIC_ERROR",
    (GID_CORE, OID_CORE_INTERFACE_ERROR): "CORE_INTERFACE_ERROR",
    (GID_RF_MANAGE, OID_RF_DISCOVER_MAP): "RF_DISCOVER_MAP",
    (GID_RF_MANAGE, OID_RF_SET_LISTEN_MODE_ROUTING): "RF_SET_LISTEN_MODE_ROUTING",
    (GID_RF_MANAGE, OID_RF_GET_LISTEN_MODE_ROUTING): "RF_GET_LISTEN_MODE_ROUTING",
    (GID_RF_MANAGE, OID_RF_DISCOVER): "RF_DISCOVER",
    (GID_RF_MANAGE, OID_RF_DISCOVER_SELECT): "RF_DISCOVER_SELECT",
    (GID_RF_MANAGE, OID_RF_INTF_ACTIVATED): "RF_INTF_ACTIVATED",
    (GID_RF_MANAGE, OID_RF_DEACTIVATE): "RF_DEACTIVATE",
    (GID_RF_MANAGE, OID_RF_FIELD_INFO): "RF_FIELD_INFO",
    (GID_RF_MANAGE, OID_RF_T3T_POLLING): "RF_T3T_POLLING",
    (GID_RF_MANAGE, OID_RF_EE_ACTION): "RF_EE_ACTION",
    (GID_RF_MANAGE, OID_RF_EE_DISCOVERY_REQ): "RF_EE_DISCOVERY_REQ",
    (GID_RF_MANAGE, OID_RF_PARAMETER_UPDATE): "RF_PARAMETER_UPDATE",
}

# RF Technologies and Modes
RF_TECH_MODES = {
    0x00: "NFC_A_PASSIVE_POLL_MODE",
    0x01: "NFC_B_PASSIVE_POLL_MODE",
    0x02: "NFC_F_PASSIVE_POLL_MODE",
    0x03: "NFC_ACTIVE_POLL_MODE",
    0x06: "NFC_V_PASSIVE_POLL_MODE",
    0x80: "NFC_A_PASSIVE_LISTEN_MODE",
    0x81: "NFC_B_PASSIVE_LISTEN_MODE",
    0x82: "NFC_F_PASSIVE_LISTEN_MODE",
    0x83: "NFC_ACTIVE_LISTEN_MODE",
    0x86: "NFC_V_PASSIVE_LISTEN_MODE",
}

# RF Protocols
RF_PROTOCOLS = {
    0x00: "UNDETERMINED",
    0x01: "T1T",
    0x02: "T2T",
    0x03: "T3T",
    0x04: "ISO_DEP",
    0x05: "NFC_DEP",
    0x06: "T5T",
    0x80: "MIFARE_CLASSIC",
}

# RF Interfaces
RF_INTERFACES = {
    0x00: "NFCEE_DIRECT",
    0x01: "FRAME_RF",
    0x02: "ISO_DEP",
    0x03: "NFC_DEP",
}

# Known Manufacturer Identifiers
MANUFACTURER_IDS = {
    0x04: "NXP Semiconductors",
    0x02: "Broadcom",
    0x01: "Sony",
    0x05: "STMicroelectronics",
    0x08: "Renesas",
}


@dataclass
class NciPacket:
    raw_hex: str
    mt: int
    mt_name: str
    pbf: bool
    payload_len: int
    payload_hex: str
    gid: Optional[int] = None
    gid_name: Optional[str] = None
    oid: Optional[int] = None
    conn_id: Optional[int] = None
    packet_name: str = "UNKNOWN"
    details: Dict[str, Any] = field(default_factory=dict)
    parse_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_hex": self.raw_hex,
            "mt": self.mt,
            "mt_name": self.mt_name,
            "pbf": self.pbf,
            "gid": self.gid,
            "gid_name": self.gid_name,
            "oid": self.oid,
            "conn_id": self.conn_id,
            "packet_name": self.packet_name,
            "payload_len": self.payload_len,
            "payload_hex": self.payload_hex,
            "details": self.details,
            "parse_error": self.parse_error,
        }


def _clean_hex_to_bytes(raw: Union[bytes, str]) -> bytes:
    if isinstance(raw, bytes):
        return raw
    cleaned = "".join(c for c in raw if c in "0123456789abcdefABCDEF")
    if len(cleaned) % 2 != 0:
        raise ValueError(f"Odd number of hex digits: '{raw}'")
    return bytes.fromhex(cleaned)


def parse_nci_packet(raw: Union[bytes, str]) -> NciPacket:
    """Parse a single raw NCI frame into a structured NciPacket."""
    try:
        data = _clean_hex_to_bytes(raw)
    except Exception as exc:
        return NciPacket(
            raw_hex=str(raw),
            mt=0,
            mt_name="INVALID",
            pbf=False,
            payload_len=0,
            payload_hex="",
            parse_error=f"Hex decode failed: {exc}",
        )

    if len(data) < 3:
        return NciPacket(
            raw_hex=data.hex(" ").upper(),
            mt=0,
            mt_name="INVALID",
            pbf=False,
            payload_len=0,
            payload_hex="",
            parse_error=f"Packet too short ({len(data)} bytes, min header is 3)",
        )

    b0 = data[0]
    mt = (b0 >> 5) & 0x07
    pbf = bool((b0 >> 4) & 0x01)
    mt_name = MT_NAMES.get(mt, f"UNKNOWN_MT_{mt}")
    payload_len = data[2]
    payload = data[3 : 3 + payload_len]

    if len(payload) != payload_len:
        err = f"Header payload_len {payload_len} mismatch actual trailing bytes {len(payload)}"
    else:
        err = None

    raw_hex_str = data.hex(" ").upper()
    payload_hex_str = payload.hex(" ").upper()

    if mt == MT_DATA:
        conn_id = b0 & 0x0F
        rfu = data[1]
        pkt = NciPacket(
            raw_hex=raw_hex_str,
            mt=mt,
            mt_name="DATA",
            pbf=pbf,
            conn_id=conn_id,
            packet_name=f"DATA (ConnID {conn_id})",
            payload_len=payload_len,
            payload_hex=payload_hex_str,
            details={"conn_id": conn_id, "rfu": rfu, "payload_bytes": len(payload)},
            parse_error=err,
        )
        return pkt

    # Control Packet (CMD, RSP, NTF)
    gid = b0 & 0x0F
    oid = data[1] & 0x3F
    gid_name = GID_NAMES.get(gid, f"GID_{gid}")
    opcode_base_name = OPCODE_NAMES.get((gid, oid), f"UNKNOWN_OPCODE_{gid}_{oid}")
    packet_name = f"{opcode_base_name}_{mt_name}"

    details: Dict[str, Any] = {}

    if err is None:
        try:
            if gid == GID_CORE and oid == OID_CORE_RESET:
                _parse_core_reset(mt, payload, details)
            elif gid == GID_CORE and oid == OID_CORE_INIT:
                _parse_core_init(mt, payload, details)
            elif gid == GID_RF_MANAGE and oid == OID_RF_DISCOVER:
                _parse_rf_discover(mt, payload, details)
            elif gid == GID_RF_MANAGE and oid == OID_RF_INTF_ACTIVATED:
                _parse_rf_intf_activated(mt, payload, details)
            elif gid == GID_RF_MANAGE and oid == OID_RF_DEACTIVATE:
                _parse_rf_deactivate(mt, payload, details)
        except Exception as exc:
            err = f"Payload parser error: {exc}"

    return NciPacket(
        raw_hex=raw_hex_str,
        mt=mt,
        mt_name=mt_name,
        pbf=pbf,
        gid=gid,
        gid_name=gid_name,
        oid=oid,
        packet_name=packet_name,
        payload_len=payload_len,
        payload_hex=payload_hex_str,
        details=details,
        parse_error=err,
    )


def _parse_core_reset(mt: int, payload: bytes, details: Dict[str, Any]) -> None:
    if mt == MT_CMD and len(payload) >= 1:
        reset_type = payload[0]
        details["reset_type"] = reset_type
        details["reset_type_desc"] = (
            "KEEP_CONFIGURATION" if reset_type == 0x01 else "RESET_CONFIGURATION"
        )
    elif mt == MT_RSP and len(payload) >= 1:
        details["status"] = payload[0]
        details["status_desc"] = "STATUS_OK" if payload[0] == 0x00 else f"STATUS_ERR_0x{payload[0]:02X}"
        if len(payload) >= 3:
            details["nci_version"] = f"0x{payload[1]:02X}"
            details["config_status"] = payload[2]
            details["config_status_desc"] = (
                "CONFIG_KEPT" if payload[2] == 0x01 else "CONFIG_RESET"
            )
    elif mt == MT_NTF and len(payload) >= 2:
        details["reset_trigger"] = payload[0]
        details["config_status"] = payload[1]


def _parse_core_init(mt: int, payload: bytes, details: Dict[str, Any]) -> None:
    if mt == MT_CMD:
        details["init_cmd_length"] = len(payload)
    elif mt == MT_RSP and len(payload) >= 1:
        status = payload[0]
        details["status"] = status
        details["status_desc"] = "STATUS_OK" if status == 0x00 else f"STATUS_ERR_0x{status:02X}"
        if status == 0x00 and len(payload) >= 13:
            details["nfcc_features"] = payload[1:5].hex().upper()
            details["max_logical_connections"] = payload[5]
            details["max_routing_table_size"] = int.from_bytes(payload[6:8], "little")
            details["max_control_payload_size"] = payload[8]
            details["max_data_payload_static_hci"] = payload[9]
            details["num_credits_static_hci"] = payload[10]
            details["max_data_payload"] = payload[11]
            num_interfaces = payload[12]
            offset = 13
            interfaces = []
            for _ in range(num_interfaces):
                if offset < len(payload):
                    iface_id = payload[offset]
                    interfaces.append(RF_INTERFACES.get(iface_id, f"INTERFACE_0x{iface_id:02X}"))
                    offset += 1
            details["supported_rf_interfaces"] = interfaces

            # Manufacturer info
            if offset < len(payload):
                mfg_id = payload[offset]
                details["manufacturer_id"] = mfg_id
                details["manufacturer"] = MANUFACTURER_IDS.get(mfg_id, f"UNKNOWN_0x{mfg_id:02X}")
                mfg_data = payload[offset + 1 :]
                details["manufacturer_specific_info_hex"] = mfg_data.hex().upper()
                # NXP SN110 detection
                if mfg_id == 0x04 and len(mfg_data) >= 4:
                    details["nxp_chip_type"] = f"0x{mfg_data[0]:02X}"
                    details["nxp_rom_version"] = f"0x{mfg_data[1]:02X}"
                    details["nxp_fw_version"] = f"0x{mfg_data[2]:02X}.{mfg_data[3]:02X}"
                    if mfg_data[0] == 0xA4:
                        details["nxp_controller_family"] = "NXP SN110T"


def _parse_rf_discover(mt: int, payload: bytes, details: Dict[str, Any]) -> None:
    if mt == MT_CMD and len(payload) >= 1:
        num_configs = payload[0]
        details["num_configurations"] = num_configs
        configs = []
        offset = 1
        for _ in range(num_configs):
            if offset + 2 <= len(payload):
                tech_mode = payload[offset]
                freq = payload[offset + 1]
                configs.append(
                    {
                        "tech_mode_code": tech_mode,
                        "tech_mode": RF_TECH_MODES.get(tech_mode, f"0x{tech_mode:02X}"),
                        "frequency": freq,
                    }
                )
                offset += 2
        details["configurations"] = configs
    elif mt == MT_RSP and len(payload) >= 1:
        details["status"] = payload[0]
        details["status_desc"] = "STATUS_OK" if payload[0] == 0x00 else f"STATUS_ERR_0x{payload[0]:02X}"


def _parse_rf_intf_activated(mt: int, payload: bytes, details: Dict[str, Any]) -> None:
    if mt != MT_NTF or len(payload) < 6:
        return

    discovery_id = payload[0]
    rf_interface = payload[1]
    rf_protocol = payload[2]
    activation_tech_mode = payload[3]
    max_payload = payload[4]
    initial_credits = payload[5]

    details["discovery_id"] = discovery_id
    details["rf_interface"] = RF_INTERFACES.get(rf_interface, f"0x{rf_interface:02X}")
    details["rf_protocol"] = RF_PROTOCOLS.get(rf_protocol, f"0x{rf_protocol:02X}")
    details["activation_tech_mode"] = RF_TECH_MODES.get(
        activation_tech_mode, f"0x{activation_tech_mode:02X}"
    )
    details["max_data_packet_payload_size"] = max_payload
    details["initial_credits"] = initial_credits

    if len(payload) > 6:
        params_len = payload[6]
        params = payload[7 : 7 + params_len]
        details["tech_specific_params_len"] = params_len

        # NFC-A Poll specific parameters
        if activation_tech_mode == 0x00 and len(params) >= 3:
            sens_res = int.from_bytes(params[0:2], "little")
            uid_len = params[2]
            details["sens_res_atqa"] = f"0x{sens_res:04X}"
            details["uid_len"] = uid_len
            if len(params) >= 3 + uid_len:
                uid_bytes = params[3 : 3 + uid_len]
                details["uid_hex"] = ":".join(f"{b:02X}" for b in uid_bytes)
                details["uid_compact"] = uid_bytes.hex().upper()
                sak_offset = 3 + uid_len
                if len(params) > sak_offset:
                    sak = params[sak_offset]
                    details["sel_res_sak"] = f"0x{sak:02X}"


def _parse_rf_deactivate(mt: int, payload: bytes, details: Dict[str, Any]) -> None:
    if mt == MT_CMD and len(payload) >= 1:
        deact_type = payload[0]
        details["deactivation_type"] = deact_type
        desc = {0x00: "IDLE_MODE", 0x01: "SLEEP_MODE", 0x02: "SLEEP_AF_MODE", 0x03: "DISCOVERY"}.get(
            deact_type, f"0x{deact_type:02X}"
        )
        details["deactivation_type_desc"] = desc
    elif mt == MT_RSP and len(payload) >= 1:
        details["status"] = payload[0]
        details["status_desc"] = "STATUS_OK" if payload[0] == 0x00 else f"STATUS_ERR_0x{payload[0]:02X}"


def parse_nci_trial_receipt(receipt: Dict[str, Any]) -> Dict[str, Any]:
    """Parse an attended NFC trial receipt containing a sequence of raw NCI frames."""
    frames_raw = receipt.get("frames", [])
    parsed_packets: List[NciPacket] = []
    errors: List[str] = []

    controller_info: Dict[str, Any] = {}
    polling_configs: List[Dict[str, Any]] = []
    tag_activated: Optional[Dict[str, Any]] = None
    data_packet_count = 0
    core_reset_ok = False
    core_init_ok = False
    rf_discover_ok = False
    rf_deactivated_cleanly = False

    for idx, f in enumerate(frames_raw):
        hex_data = f.get("hex") if isinstance(f, dict) else str(f)
        pkt = parse_nci_packet(hex_data)
        parsed_packets.append(pkt)

        if pkt.parse_error:
            errors.append(f"Frame {idx}: {pkt.parse_error}")
            continue

        if pkt.packet_name == "CORE_RESET_RSP" and pkt.details.get("status") == 0x00:
            core_reset_ok = True
        elif pkt.packet_name == "CORE_INIT_RSP" and pkt.details.get("status") == 0x00:
            core_init_ok = True
            for k in (
                "manufacturer",
                "nxp_controller_family",
                "nxp_chip_type",
                "nxp_rom_version",
                "nxp_fw_version",
            ):
                if k in pkt.details:
                    controller_info[k] = pkt.details[k]
        elif pkt.packet_name == "RF_DISCOVER_CMD":
            if "configurations" in pkt.details:
                polling_configs.extend(pkt.details["configurations"])
        elif pkt.packet_name == "RF_DISCOVER_RSP" and pkt.details.get("status") == 0x00:
            rf_discover_ok = True
        elif pkt.packet_name == "RF_INTF_ACTIVATED_NTF":
            tag_activated = pkt.details
        elif pkt.packet_name.startswith("DATA"):
            data_packet_count += 1
        elif pkt.packet_name == "RF_DEACTIVATE_RSP" and pkt.details.get("status") == 0x00:
            rf_deactivated_cleanly = True

    if tag_activated and tag_activated.get("uid_hex"):
        verdict = "TAG_EXCHANGE_VERIFIED"
    elif rf_discover_ok and not tag_activated:
        verdict = "DISCOVERY_ACTIVE_NO_TAG"
    elif errors:
        verdict = "PARSING_FAILED"
    else:
        verdict = "INCOMPLETE_SEQUENCE"

    return {
        "verdict": verdict,
        "trial_id": receipt.get("trial_id", "unknown"),
        "boot_id": receipt.get("boot_id", ""),
        "total_frames_parsed": len(parsed_packets),
        "core_reset_verified": core_reset_ok,
        "core_init_verified": core_init_ok,
        "controller_info": controller_info,
        "rf_discovery_configured": rf_discover_ok,
        "polling_configurations": polling_configs,
        "tag_detected": bool(tag_activated),
        "tag_details": tag_activated,
        "data_packets_exchanged": data_packet_count,
        "rf_deactivated_cleanly": rf_deactivated_cleanly,
        "errors": errors,
        "parsed_packets": [p.to_dict() for p in parsed_packets],
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Offline NCI frame parser & trial receipt decoder")
    parser.add_argument("--parse-hex", type=str, help="Parse a single raw NCI frame hex string")
    parser.add_argument("--parse-receipt", type=Path, help="Parse and decode an attended trial receipt JSON file")
    args = parser.parse_args()

    if args.parse_hex:
        pkt = parse_nci_packet(args.parse_hex)
        print(json.dumps(pkt.to_dict(), indent=2))
        sys.exit(0 if not pkt.parse_error else 1)

    if args.parse_receipt:
        if not args.parse_receipt.exists():
            print(f"Error: file not found {args.parse_receipt}", file=sys.stderr)
            sys.exit(2)
        receipt_data = json.loads(args.parse_receipt.read_text())
        summary = parse_nci_trial_receipt(receipt_data)
        print(json.dumps(summary, indent=2))
        sys.exit(0 if not summary["errors"] else 1)

    parser.print_help()


if __name__ == "__main__":
    main()
