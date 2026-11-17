#!/usr/bin/env python3
"""Summarize Lynx's captured NMEA without releasing invalid coordinates."""

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import struct

NMEA = re.compile(rb"\$[A-Z0-9]{5},[^\r\n\x00]*\*[0-9A-Fa-f]{2}")


def checksum_ok(sentence):
    body, expected = sentence[1:].rsplit(b"*", 1)
    actual = 0
    for byte in body:
        actual ^= byte
    return actual == int(expected, 16)


def coordinate(raw, hemisphere):
    if not raw or hemisphere not in ("N", "S", "E", "W"):
        raise ValueError("missing NMEA coordinate")
    degrees_length = 2 if hemisphere in ("N", "S") else 3
    degrees = int(raw[:degrees_length])
    minutes = float(raw[degrees_length:])
    limit = 90 if hemisphere in ("N", "S") else 180
    if not 0 <= minutes < 60 or degrees > limit or (degrees == limit and minutes):
        raise ValueError("invalid NMEA minutes")
    result = degrees + minutes / 60
    return -result if hemisphere in ("S", "W") else result


def summarize(receipt):
    messages = receipt["sandbox"].get("mnl_messages", [])
    sentences = []
    invalid = 0
    for event in messages:
        if event.get("event") != "message":
            continue
        payload = bytes.fromhex(event["hex"])
        if len(payload) < 8 or struct.unpack_from("<II", payload) != (1, 104):
            continue
        for match in NMEA.finditer(payload):
            sentence = match.group()
            if checksum_ok(sentence):
                sentences.append(sentence.decode("ascii"))
            else:
                invalid += 1
    types = Counter(sentence[1:6] for sentence in sentences)
    gga = [s.split(",") for s in sentences if s[1:6] in ("GNGGA", "GPGGA")]
    rmc = [s.split(",") for s in sentences if s[1:6] in ("GNRMC", "GPRMC")]
    latest_gga = gga[-1] if gga else None
    latest_rmc = next((item for item in reversed(rmc) if latest_gga and
                       len(item) > 2 and len(latest_gga) > 7 and
                       item[1].split(".")[0] == latest_gga[1].split(".")[0]), None)
    quality = int(latest_gga[6]) if latest_gga and len(latest_gga) > 6 and latest_gga[6].isdigit() else 0
    satellites = int(latest_gga[7]) if latest_gga and len(latest_gga) > 7 and latest_gga[7].isdigit() else 0
    rmc_valid = bool(latest_rmc and latest_rmc[2] == "A")
    result = {"nmea_sentences": len(sentences), "invalid_checksums": invalid,
              "sentence_types": dict(types), "gga_fix_quality": quality,
              "gga_satellites_in_use": satellites, "rmc_valid": rmc_valid,
              "position_fix": False}
    # A receiver can lose its fix near the end of a trial. Keep the last
    # independently valid GGA/RMC pair, while reporting the latest status above.
    rmc_by_second = {item[1].split(".")[0]: item for item in rmc
                     if len(item) > 6 and item[2] == "A"}
    for item in reversed(gga):
        try:
            matching = rmc_by_second[item[1].split(".")[0]]
            if int(item[6]) <= 0 or int(item[7]) <= 0:
                continue
            lat, lon = coordinate(item[2], item[3]), coordinate(item[4], item[5])
            rmc_lat = coordinate(matching[3], matching[4])
            rmc_lon = coordinate(matching[5], matching[6])
            if abs(lat - rmc_lat) > 0.01 or abs(lon - rmc_lon) > 0.01:
                continue
            result.update(position_fix=True, latitude=lat, longitude=lon,
                          utc_time=item[1], fix_satellites_in_use=int(item[7]))
            break
        except (ValueError, IndexError, KeyError):
            continue
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--save", type=Path)
    args = parser.parse_args()
    result = summarize(json.loads(args.receipt.read_text()))
    output = json.dumps(result, indent=2) + "\n"
    if args.save:
        args.save.write_text(output)
        args.save.chmod(0o600)
    print(output, end="")


if __name__ == "__main__":
    main()
