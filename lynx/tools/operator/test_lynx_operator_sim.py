#!/usr/bin/env python3
"""Unit tests for lynx_operator_sim.py."""

import unittest
from unittest.mock import MagicMock, patch
import json
import sys
from pathlib import Path

# Add operator tools dir to sys.path
OPERATOR_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(OPERATOR_DIR))

import lynx_operator_sim as op_sim


class TestOperatorSim(unittest.TestCase):

    def test_parse_cpin_ready(self):
        lines = ["+CPIN: READY", "OK"]
        res = op_sim.parse_cpin_response(lines)
        self.assertEqual(res["status"], "READY")
        self.assertTrue(res["ready"])
        self.assertIsNone(res["error"])

    def test_parse_cpin_pin_required(self):
        lines = ["+CPIN: SIM PIN", "OK"]
        res = op_sim.parse_cpin_response(lines)
        self.assertEqual(res["status"], "SIM PIN")
        self.assertFalse(res["ready"])

    def test_parse_cpin_error(self):
        lines = ["+CME ERROR: 16"]
        res = op_sim.parse_cpin_response(lines)
        self.assertEqual(res["status"], "ERROR")
        self.assertFalse(res["ready"])
        self.assertIn("Incorrect password", res["error"])

    def test_parse_cops(self):
        lines = ['+COPS: 0,0,"Telia EE",7', "OK"]
        res = op_sim.parse_cops_response(lines)
        self.assertEqual(res["mode"], 0)
        self.assertEqual(res["format"], 0)
        self.assertEqual(res["operator"], "Telia EE")
        self.assertEqual(res["act"], 7)

    def test_parse_csq(self):
        lines = ["+CSQ: 21,99", "OK"]
        res = op_sim.parse_csq_response(lines)
        self.assertEqual(res["rssi"], 21)
        self.assertEqual(res["ber"], 99)
        self.assertEqual(res["dbm"], -71)  # -113 + 21*2

        # Test undetectable
        lines_undetectable = ["+CSQ: 99,99", "OK"]
        res_und = op_sim.parse_csq_response(lines_undetectable)
        self.assertEqual(res_und["dbm"], "not detectable")

    def test_parse_reg(self):
        # 1 = registered, home network
        lines = ["+CREG: 0,1", "OK"]
        res = op_sim.parse_reg_response(lines, "+CREG:")
        self.assertEqual(res["stat"], 1)
        self.assertEqual(res["description"], "registered, home network")

        # 5 = registered, roaming
        lines_roam = ["+CEREG: 1,5", "OK"]
        res_roam = op_sim.parse_reg_response(lines_roam, "+CEREG:")
        self.assertEqual(res_roam["stat"], 5)
        self.assertEqual(res_roam["description"], "registered, roaming")

    @patch("lynx_operator_sim.ModemSerial")
    def test_op_sim_info(self, mock_serial_cls):
        mock_serial = MagicMock()
        mock_serial_cls.return_value.__enter__.return_value = mock_serial

        def mock_send(cmd):
            if cmd == "AT+CCID":
                return ["893720123456789012F", "OK"]
            elif cmd == "AT+CIMI":
                return ["248011234567890", "OK"]
            elif cmd == "AT+CNUM":
                return ['+CNUM: "MyNumber","+3725551234",145', "OK"]
            return ["OK"]

        mock_serial.send_at.side_effect = mock_send

        info = op_sim.op_sim_info_local()
        self.assertEqual(info["iccid"], "893720123456789012F")
        self.assertEqual(info["imsi"], "248011234567890")
        self.assertIn("+3725551234", info["msisdn"])

    @patch("lynx_operator_sim.ModemSerial")
    def test_op_unlock_pin(self, mock_serial_cls):
        mock_serial = MagicMock()
        mock_serial_cls.return_value.__enter__.return_value = mock_serial
        mock_serial.send_at.return_value = ["OK"]

        res = op_sim.op_unlock_pin_local("1234")
        self.assertTrue(res["unlocked"])
        mock_serial.send_at.assert_called_with('AT+CPIN="1234"')

    @patch("lynx_operator_sim.ModemSerial")
    def test_op_set_apn(self, mock_serial_cls):
        mock_serial = MagicMock()
        mock_serial_cls.return_value.__enter__.return_value = mock_serial
        mock_serial.send_at.return_value = ["OK"]

        res = op_sim.op_set_apn_local("internet.emt.ee", cid=1, proto="IP")
        self.assertTrue(res["success"])
        self.assertEqual(res["apn"], "internet.emt.ee")
        mock_serial.send_at.assert_called_with('AT+CGDCONT=1,"IP","internet.emt.ee"')


if __name__ == "__main__":
    unittest.main()
