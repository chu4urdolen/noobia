"""Position gate checks against NMEA fields and checksums."""

import struct
import unittest

from parse_lynx_mnl_nmea import summarize


def sentence(body):
    checksum = 0
    for byte in body.encode():
        checksum ^= byte
    return f"${body}*{checksum:02X}".encode()


def receipt(*sentences):
    return {"sandbox": {"mnl_messages": [{"event": "message",
        "hex": (struct.pack("<II", 1, 104) + item).hex()} for item in sentences]}}


class NMEATest(unittest.TestCase):
    def test_valid_position_requires_both_gga_and_rmc(self):
        gga = sentence("GNGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,")
        rmc = sentence("GNRMC,123519,A,4807.038,N,01131.000,E,0.0,0.0,230394,,,A")
        result = summarize(receipt(gga, rmc))
        self.assertTrue(result["position_fix"])
        self.assertAlmostEqual(result["latitude"], 48.1173, places=4)
        self.assertAlmostEqual(result["longitude"], 11.5166667, places=4)

    def test_coordinates_in_invalid_gga_are_hidden(self):
        gga = sentence("GNGGA,123519,4807.038,N,01131.000,E,0,00,0.9,545.4,M,46.9,M,,")
        rmc = sentence("GNRMC,123519,V,4807.038,N,01131.000,E,0.0,0.0,230394,,,A")
        result = summarize(receipt(gga, rmc))
        self.assertFalse(result["position_fix"])
        self.assertNotIn("latitude", result)
        self.assertNotIn("longitude", result)

    def test_last_valid_pair_survives_later_fix_loss(self):
        fixed = sentence("GNGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,")
        valid = sentence("GNRMC,123519,A,4807.038,N,01131.000,E,0.0,0.0,230394,,,A")
        lost = sentence("GNGGA,123520,4807.038,N,01131.000,E,0,00,0.9,545.4,M,46.9,M,,")
        result = summarize(receipt(fixed, valid, lost))
        self.assertTrue(result["position_fix"])
        self.assertEqual(result["gga_fix_quality"], 0)
        self.assertEqual(result["fix_satellites_in_use"], 8)

    def test_mismatched_rmc_position_is_rejected(self):
        gga = sentence("GNGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,")
        rmc = sentence("GNRMC,123519,A,4707.038,N,01131.000,E,0.0,0.0,230394,,,A")
        self.assertFalse(summarize(receipt(gga, rmc))["position_fix"])


if __name__ == "__main__":
    unittest.main()
