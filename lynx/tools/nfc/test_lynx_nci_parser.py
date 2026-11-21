#!/usr/bin/env python3
"""Unit tests for offline NCI frame parser and trial receipt decoder."""

import json
from pathlib import Path
import unittest

from lynx_nci_parser import (
    parse_nci_packet,
    parse_nci_trial_receipt,
    MT_CMD,
    MT_RSP,
    MT_NTF,
    MT_DATA,
    GID_CORE,
    GID_RF_MANAGE,
    OID_CORE_RESET,
    OID_CORE_INIT,
    OID_RF_DISCOVER,
    OID_RF_INTF_ACTIVATED,
    OID_RF_DEACTIVATE,
)

FIXTURES = Path(__file__).parent / "fixtures"


class TestLynxNciParser(unittest.TestCase):
    def test_parse_core_reset_cmd(self):
        pkt = parse_nci_packet("20 00 01 01")
        self.assertIsNone(pkt.parse_error)
        self.assertEqual(pkt.mt, MT_CMD)
        self.assertEqual(pkt.mt_name, "CMD")
        self.assertEqual(pkt.gid, GID_CORE)
        self.assertEqual(pkt.oid, OID_CORE_RESET)
        self.assertEqual(pkt.packet_name, "CORE_RESET_CMD")
        self.assertEqual(pkt.details["reset_type"], 0x01)
        self.assertEqual(pkt.details["reset_type_desc"], "KEEP_CONFIGURATION")

    def test_parse_core_reset_rsp(self):
        pkt = parse_nci_packet("40 00 03 00 10 01")
        self.assertIsNone(pkt.parse_error)
        self.assertEqual(pkt.mt, MT_RSP)
        self.assertEqual(pkt.packet_name, "CORE_RESET_RSP")
        self.assertEqual(pkt.details["status"], 0x00)
        self.assertEqual(pkt.details["status_desc"], "STATUS_OK")
        self.assertEqual(pkt.details["nci_version"], "0x10")
        self.assertEqual(pkt.details["config_status_desc"], "CONFIG_KEPT")

    def test_parse_core_init_rsp_nxp_sn110(self):
        # NXP SN110: mfg ID 0x04, chip A4, rom 01, fw 10.68
        raw = "40 01 16 00 01 02 03 04 04 01 f4 ff ff 01 ff 04 01 02 03 00 04 a4 01 10 68"
        pkt = parse_nci_packet(raw)
        self.assertIsNone(pkt.parse_error)
        self.assertEqual(pkt.packet_name, "CORE_INIT_RSP")
        self.assertEqual(pkt.details["status"], 0x00)
        self.assertEqual(pkt.details["manufacturer"], "NXP Semiconductors")
        self.assertEqual(pkt.details["nxp_controller_family"], "NXP SN110T")
        self.assertEqual(pkt.details["nxp_chip_type"], "0xA4")
        self.assertEqual(pkt.details["nxp_rom_version"], "0x01")
        self.assertEqual(pkt.details["nxp_fw_version"], "0x10.68")

    def test_parse_rf_discover_cmd_and_rsp(self):
        cmd = parse_nci_packet("21 03 03 01 00 01")
        self.assertIsNone(cmd.parse_error)
        self.assertEqual(cmd.packet_name, "RF_DISCOVER_CMD")
        self.assertEqual(cmd.details["num_configurations"], 1)
        self.assertEqual(cmd.details["configurations"][0]["tech_mode"], "NFC_A_PASSIVE_POLL_MODE")

        rsp = parse_nci_packet("41 03 01 00")
        self.assertIsNone(rsp.parse_error)
        self.assertEqual(rsp.packet_name, "RF_DISCOVER_RSP")
        self.assertEqual(rsp.details["status"], 0x00)

    def test_parse_rf_intf_activated_ntf_7byte_uid(self):
        # 7-byte UID NTAG215
        raw = "61 05 13 01 01 02 00 ff 01 0c 44 00 07 04 a1 b2 c3 d4 e5 f6 00 00"
        pkt = parse_nci_packet(raw)
        self.assertIsNone(pkt.parse_error)
        self.assertEqual(pkt.packet_name, "RF_INTF_ACTIVATED_NTF")
        self.assertEqual(pkt.details["rf_interface"], "FRAME_RF")
        self.assertEqual(pkt.details["rf_protocol"], "T2T")
        self.assertEqual(pkt.details["activation_tech_mode"], "NFC_A_PASSIVE_POLL_MODE")
        self.assertEqual(pkt.details["sens_res_atqa"], "0x0044")
        self.assertEqual(pkt.details["uid_len"], 7)
        self.assertEqual(pkt.details["uid_hex"], "04:A1:B2:C3:D4:E5:F6")
        self.assertEqual(pkt.details["sel_res_sak"], "0x00")

    def test_parse_rf_intf_activated_ntf_4byte_uid(self):
        # 4-byte UID Mifare Classic 1K
        raw = "61 05 10 01 01 80 00 ff 01 09 04 00 04 12 34 56 78 08 00"
        pkt = parse_nci_packet(raw)
        self.assertIsNone(pkt.parse_error)
        self.assertEqual(pkt.packet_name, "RF_INTF_ACTIVATED_NTF")
        self.assertEqual(pkt.details["rf_protocol"], "MIFARE_CLASSIC")
        self.assertEqual(pkt.details["uid_len"], 4)
        self.assertEqual(pkt.details["uid_hex"], "12:34:56:78")
        self.assertEqual(pkt.details["sel_res_sak"], "0x08")

    def test_parse_data_packet(self):
        # Data packet: ConnID 0, Length 2, payload 30 04 (READ block 4)
        pkt = parse_nci_packet("00 00 02 30 04")
        self.assertIsNone(pkt.parse_error)
        self.assertEqual(pkt.mt, MT_DATA)
        self.assertEqual(pkt.conn_id, 0)
        self.assertEqual(pkt.payload_len, 2)
        self.assertEqual(pkt.payload_hex, "30 04")

    def test_parse_rf_deactivate(self):
        cmd = parse_nci_packet("21 06 01 00")
        self.assertIsNone(cmd.parse_error)
        self.assertEqual(cmd.packet_name, "RF_DEACTIVATE_CMD")
        self.assertEqual(cmd.details["deactivation_type_desc"], "IDLE_MODE")

        rsp = parse_nci_packet("41 06 01 00")
        self.assertIsNone(rsp.parse_error)
        self.assertEqual(rsp.packet_name, "RF_DEACTIVATE_RSP")
        self.assertEqual(rsp.details["status"], 0x00)

    def test_corrupted_packets(self):
        # Too short
        pkt_short = parse_nci_packet("20 00")
        self.assertIsNotNone(pkt_short.parse_error)

        # Length mismatch
        pkt_len = parse_nci_packet("40 00 05 00")
        self.assertIsNotNone(pkt_len.parse_error)

    def test_fixture_ntag215_trial(self):
        receipt = json.loads((FIXTURES / "nci-tag-trial-ntag215-receipt.json").read_text())
        summary = parse_nci_trial_receipt(receipt)
        self.assertEqual(summary["verdict"], "TAG_EXCHANGE_VERIFIED")
        self.assertTrue(summary["core_reset_verified"])
        self.assertTrue(summary["core_init_verified"])
        self.assertTrue(summary["rf_discovery_configured"])
        self.assertTrue(summary["tag_detected"])
        self.assertEqual(summary["tag_details"]["uid_hex"], "04:A1:B2:C3:D4:E5:F6")
        self.assertEqual(summary["tag_details"]["rf_protocol"], "T2T")
        self.assertEqual(summary["controller_info"]["nxp_controller_family"], "NXP SN110T")
        self.assertEqual(summary["data_packets_exchanged"], 2)
        self.assertTrue(summary["rf_deactivated_cleanly"])
        self.assertEqual(len(summary["errors"]), 0)

    def test_fixture_mifare_classic_trial(self):
        receipt = json.loads((FIXTURES / "nci-tag-trial-mifare-classic-receipt.json").read_text())
        summary = parse_nci_trial_receipt(receipt)
        self.assertEqual(summary["verdict"], "TAG_EXCHANGE_VERIFIED")
        self.assertTrue(summary["tag_detected"])
        self.assertEqual(summary["tag_details"]["uid_hex"], "12:34:56:78")
        self.assertEqual(summary["tag_details"]["rf_protocol"], "MIFARE_CLASSIC")

    def test_fixture_timeout_no_tag_trial(self):
        receipt = json.loads((FIXTURES / "nci-tag-trial-timeout-no-tag-receipt.json").read_text())
        summary = parse_nci_trial_receipt(receipt)
        self.assertEqual(summary["verdict"], "DISCOVERY_ACTIVE_NO_TAG")
        self.assertFalse(summary["tag_detected"])
        self.assertTrue(summary["rf_discovery_configured"])
        self.assertTrue(summary["rf_deactivated_cleanly"])

    def test_fixture_corrupted_receipt(self):
        receipt = json.loads((FIXTURES / "nci-corrupted-frame-receipt.json").read_text())
        summary = parse_nci_trial_receipt(receipt)
        self.assertEqual(summary["verdict"], "PARSING_FAILED")
        self.assertGreater(len(summary["errors"]), 0)


if __name__ == "__main__":
    unittest.main()
