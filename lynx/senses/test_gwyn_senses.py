"""Offline tests for the senses Gwyn added on 2026-11-25 (Rose's backlog, from Banshee):
guard (LNX-60/71/101/103), netwatch (LNX-17/31/32/33/35/49), cell+location
(LNX-04-07/10-12/26-29/34/36), bluetooth (LNX-30), and the sense kit."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
os.environ["LYNX_REACTION_PRIORITY"] = "0"      # keep each event's own priority in tests


def _load(name, rel):
    import sys
    sys.path.insert(0, str((HERE / rel).parent))
    spec = importlib.util.spec_from_file_location(name, HERE / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


kit = _load("lynx_sense_kit", "common/lynx_sense_kit.py")
guard = _load("lynx_sense_guard", "security/lynx_sense_guard.py")
netwatch = _load("lynx_sense_netwatch", "netwatch/lynx_sense_netwatch.py")
cell = _load("lynx_sense_cell", "cell/lynx_sense_cell.py")
bt = _load("lynx_sense_bluetooth", "bluetooth/lynx_sense_bluetooth.py")


class Sense:
    """The real canonical formatter (names are validated), emits recorded."""
    def __init__(self):
        spec = importlib.util.spec_from_file_location("noobia_sense", REPO / "common/autonomy/sense.py")
        self.real = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.real)
        self.emits = []

    def format_line(self, *a, **k):
        return self.real.format_line(*a, **k)

    def emit(self, p, sense, event, fields=None, text=""):
        self.emits.append((sense, event, fields or {}, text))


def names(events):
    return [e.event for e in events]


# -- guard ---------------------------------------------------------------------------

def gobs(**over):
    o = {"resources": {"memory": 40.0, "file_handles": 1.0, "processes": 1.0, "load": 0.6,
                       "tcp_orphans": 0, "disks": {"/": 10.0, "/run": 56.0}},
         "config": {"/etc/passwd": "sha256:aa:644"}, "conn": {"listen": [22, 2222, 4243], "inbound": []},
         "counters": {"resets": 1000}, "preauth": {}, "offsets": {}, "trusted": list(guard.TRUSTED_DEFAULT)}
    o.update(over)
    return o


class GuardTest(unittest.TestCase):
    def test_baseline_is_quiet(self):
        ev, st = guard.detect({}, gobs(), 100.0)
        self.assertEqual(ev, [])
        self.assertEqual(st["resets"], 1000)

    def test_resource_alarm_then_recovery_with_hysteresis(self):
        r = gobs()["resources"]
        _, st = guard.detect({}, gobs(), 100)
        r2 = dict(r, disks={"/": 10.0, "/run": 93.0})
        ev, st = guard.detect(st, gobs(resources=r2), 130)
        self.assertEqual(names(ev), ["resource.exhaustion"])
        self.assertEqual(ev[0].fields["resource"], "disk:/run")
        self.assertTrue(ev[0].journal)
        ev, st = guard.detect(st, gobs(resources=dict(r, disks={"/": 10.0, "/run": 88.0})), 160)
        self.assertEqual(ev, [])                       # 88 % is above the 85 % clear line
        ev, st = guard.detect(st, gobs(resources=dict(r, disks={"/": 10.0, "/run": 80.0})), 190)
        self.assertEqual(names(ev), ["resource.recovered"])

    def test_config_change_names_paths_and_counts(self):
        _, st = guard.detect({}, gobs(), 100)
        st["config"] = {"/etc/passwd": "sha256:aa:644", "/etc/lynx/x.key": "meta:600:0:0"}
        cfg = {"/etc/passwd": "sha256:bb:644", "/etc/lynx/x.key": "meta:644:0:0", "/etc/sudoers.d/new": "sha256:cc:440"}
        ev, st = guard.detect(st, gobs(config=cfg), 130)
        self.assertEqual(names(ev), ["config.changed"])
        self.assertEqual(ev[0].fields["count"], 3)
        self.assertIn("/etc/lynx/x.key (permissions)", ev[0].text)
        self.assertIn("/etc/sudoers.d/new (added)", ev[0].text)

    def test_secrets_are_never_hashed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "etc/lynx").mkdir(parents=True)
            (root / "etc/lynx/brain.json").write_text("{}")
            (root / "etc/lynx/nexus-inference.key").write_text("SECRET")
            (root / "etc/lynx/nexus-inference.key").chmod(0o600)
            snap = guard.config_snapshot(root)
        self.assertTrue(snap["/etc/lynx/brain.json"].startswith("sha256:"))
        self.assertTrue(snap["/etc/lynx/nexus-inference.key"].startswith("meta:600:"))

    def test_untrusted_endpoint_but_not_nexus(self):
        _, st = guard.detect({}, gobs(), 100)
        conn = {"listen": [2222], "inbound": [{"port": 2222, "peer": "192.168.100.106"},
                                              {"port": 2222, "peer": "192.168.100.50"}]}
        ev, _ = guard.detect(st, gobs(conn=conn), 130)
        self.assertEqual(names(ev), ["endpoint.untrusted"])
        self.assertEqual(ev[0].fields["peer"], "192.168.100.50")
        self.assertEqual(ev[0].cooldown_s, 600)

    def test_probe_by_preauth_exits_and_by_reset_burst(self):
        _, st = guard.detect({}, gobs(), 100)
        ev, st = guard.detect(st, gobs(preauth={"192.168.100.66": 9, "192.168.100.106": 50},
                                       counters={"resets": 1500}), 130)
        self.assertEqual(sorted(e.fields.get("kind") for e in ev), ["closed_ports", "ssh_preauth"])
        ev, _ = guard.detect(dict(st, t=130), gobs(counters={"resets": 1900}), 1000)   # long gap
        self.assertEqual(ev, [])

    def test_preauth_parser_skips_addresses_that_logged_in(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write("x\n")
            path = f.name
        _, off = guard.preauth_exits({}, [path])
        with open(path, "a") as f:
            for _ in range(3):
                f.write("[1] Nov 25 Exit before auth from <192.168.100.66:5000>: Exited normally\n")
            f.write("[2] Nov 25 Exit before auth from <192.168.100.106:5000>: Exited normally\n")
            f.write("[2] Nov 25 Pubkey auth succeeded for 'root' with key from 192.168.100.106:5001\n")
        counts, _ = guard.preauth_exits(off, [path])
        os.unlink(path)
        self.assertEqual(counts, {"192.168.100.66": 3})

    def test_run_end_to_end_keeps_config_in_a_side_file(self):
        with tempfile.TemporaryDirectory() as d:
            sf, j, s = str(Path(d) / "guard/state.json"), Path(d) / "j.jsonl", Sense()
            r, code = guard.run(state_file=sf, now=100, sense_mod=s, observer=lambda: gobs(), journal_path=j)
            self.assertTrue(r["ok"], r)
            self.assertTrue((Path(d) / "guard/config.json").exists())
            self.assertNotIn("config", json.loads(Path(sf).read_text()))
            obs = gobs(config={"/etc/passwd": "sha256:zz:644"})
            r, _ = guard.run(state_file=sf, now=130, sense_mod=s, observer=lambda: obs, journal_path=j)
            self.assertEqual([e[:2] for e in s.emits], [("security", "config.changed")])
            self.assertEqual(json.loads(j.read_text().splitlines()[0])["event"], "config.changed")


# -- netwatch --------------------------------------------------------------------------

def nobs(**over):
    o = {"gateway": "192.168.100.1", "dev": "wlan0", "addr": "192.168.100.107/24",
         "bssid": "aa:bb:cc:dd:ee:01", "ssid": "Noobia", "neigh": {"192.168.100.1": "11:11:11:11:11:11",
                                                                   "192.168.100.106": "22:22:22:22:22:22"},
         "dns": ["8.8.8.8"], "gw_rtt": 3.0, "gw_loss": 0, "nexus_ms": 4.0}
    o.update(over)
    return o


class NetwatchTest(unittest.TestCase):
    def setUp(self):
        _, self.st = netwatch.detect({}, nobs(), 100)

    def test_baseline_quiet_and_quality_good(self):
        ev, st = netwatch.detect({}, nobs(), 100)
        self.assertEqual(ev, [])
        self.assertEqual(st["quality"], "good")

    def test_route_change(self):
        ev, _ = netwatch.detect(self.st, nobs(gateway="192.168.100.254"), 130)
        self.assertIn("route.change", names(ev))
        self.assertIn("gateway 192.168.100.1 -> 192.168.100.254", ev[0].text)

    def test_roam_and_network_change(self):
        ev, _ = netwatch.detect(self.st, nobs(bssid="aa:bb:cc:dd:ee:02"), 130)
        self.assertEqual([e.fields["kind"] for e in ev], ["roam"])
        ev, _ = netwatch.detect(self.st, nobs(bssid="aa:bb:cc:dd:ee:03", ssid="Cafe"), 130)
        self.assertEqual([e.fields["kind"] for e in ev], ["network"])

    def test_quality_needs_two_samples_and_explains_why(self):
        bad = nobs(nexus_ms=None)
        ev, st = netwatch.detect(self.st, bad, 130)
        self.assertEqual(ev, [])
        ev, st = netwatch.detect(st, bad, 160)
        self.assertEqual(names(ev), ["quality.change"])
        self.assertIn("Nexus 192.168.100.106:8080 does not", ev[0].text)
        ev, st = netwatch.detect(st, nobs(), 190)
        ev, st = netwatch.detect(st, nobs(), 220)
        self.assertEqual(ev[0].fields["quality"], "good")
        self.assertIn("improved", ev[0].text)

    def test_diagnosis_layers(self):
        self.assertIn("not connected", netwatch.diagnose(nobs(bssid=None)))
        self.assertIn("no IP address", netwatch.diagnose(nobs(addr=None)))
        self.assertIn("does not answer", netwatch.diagnose(nobs(gw_loss=100)))

    def test_anomalies(self):
        n = dict(nobs()["neigh"], **{"192.168.100.1": "66:66:66:66:66:66"})
        ev, _ = netwatch.detect(self.st, nobs(neigh=n), 130)
        self.assertEqual([e.fields["kind"] for e in ev], ["gateway_mac"])
        n = dict(nobs()["neigh"], **{"192.168.100.9": "11:11:11:11:11:11"})
        ev, _ = netwatch.detect(self.st, nobs(neigh=n), 130)
        self.assertEqual([e.fields["kind"] for e in ev], ["arp_conflict"])
        ev, _ = netwatch.detect(self.st, nobs(dns=["1.2.3.4"]), 130)
        self.assertEqual([e.fields["kind"] for e in ev], ["dns_change"])
        crowd = dict(nobs()["neigh"], **{f"192.168.100.{i}": f"00:00:00:00:00:{i:02x}" for i in range(20, 32)})
        ev, _ = netwatch.detect(self.st, nobs(neigh=crowd), 130)
        self.assertEqual([e.fields["kind"] for e in ev], ["neighbour_crowd"])


# -- cell + location -------------------------------------------------------------------

def cobs(cellsnap=None, gnss=None, b=0):
    return {"cell": cellsnap, "gnss": gnss, "bytes": b}


SNAP = {"t": 1, "registration": "registered", "operator": "A1", "rat": "LTE",
        "serving": {"id": "284-01-1-100", "pci": 1, "earfcn": 1850, "rsrp": -85, "sinr": 12},
        "neighbors": [{"pci": 7, "earfcn": 1850, "rsrp": -104}]}


class CellTest(unittest.TestCase):
    def test_no_source_is_quiet_but_counts_data(self):
        ev, st = cell.detect_cell({}, cobs(b=10), 0)
        self.assertEqual((ev, st["source"]), ([], "none"))
        ev, st = cell.detect_cell(st, cobs(b=150_000_010), 30)
        self.assertEqual(names(ev), ["data.usage"])
        ev, st = cell.detect_cell(st, cobs(b=5), 60)               # reboot: counters restart
        self.assertEqual(st["usage_total"], 150_000_005)

    def test_cell_events(self):
        _, st = cell.detect_cell({}, cobs(SNAP), 0)
        s2 = json.loads(json.dumps(SNAP))
        s2.update(rat="NR-NSA", registration="roaming")
        s2["serving"].update(id="284-01-1-200", rsrp=-104)
        ev, st = cell.detect_cell(st, cobs(s2), 30)
        self.assertEqual(sorted(names(ev)), ["handover", "registration.change", "technology.change",
                                             "tower.discovered"])
        ev, st = cell.detect_cell(st, cobs(s2), 60)                 # second weak sample
        self.assertEqual(names(ev), ["signal.change"])
        self.assertEqual(ev[0].fields["band"], "poor")

    def test_location_move_and_coverage_row(self):
        _, st = cell.detect_location({}, cobs(gnss={"fix": True, "lat": 42.0, "lon": 23.0}), 0)
        ev, st = cell.detect_location(st, cobs(gnss={"fix": True, "lat": 42.0002, "lon": 23.0}), 30)
        self.assertEqual(ev, [])                                    # ~22 m
        ev, st = cell.detect_location(st, cobs(gnss={"fix": True, "lat": 42.001, "lon": 23.0}), 60)
        self.assertEqual(names(ev), ["change"])
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "m.db"
            self.assertTrue(cell.record_coverage(cobs(SNAP, {"fix": True, "lat": 42.0, "lon": 23.0}), 5, db))
            self.assertFalse(cell.record_coverage(cobs(SNAP, None), 5, db))
            row = sqlite3.connect(db).execute("SELECT cell, rsrp, rat FROM cell_obs").fetchall()
        self.assertEqual(row, [("284-01-1-100", -85.0, "LTE")])

    def test_stale_file_is_absent(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"t": 1000}, f)
        self.assertIsNotNone(cell.read_fresh(Path(f.name), 1100))
        self.assertIsNone(cell.read_fresh(Path(f.name), 1200))
        os.unlink(f.name)

    def test_run_emits_with_real_line_format(self):
        with tempfile.TemporaryDirectory() as d:
            s = Sense()
            sf = str(Path(d) / "cell/state.json")
            r, _ = cell.run(state_file=sf, now=100, sense_mod=s, observer=lambda: cobs())
            self.assertTrue(r["ok"], r)
            self.assertEqual(r["source"], "none")


# -- bluetooth -------------------------------------------------------------------------

DBUS_OUT = '''method return time=1
   array [
      dict entry(
         object path "/org/bluez/hci0"
         array [
               dict entry(
                  string "Powered"
                  variant                         boolean true
               )
         ]
      )
      dict entry(
         object path "/org/bluez/hci0/dev_11_22_33_44_55_66"
         array [
               dict entry(
                  string "Address"
                  variant                         string "11:22:33:44:55:66"
               )
               dict entry(
                  string "Name"
                  variant                         string "Tom's watch"
               )
               dict entry(
                  string "RSSI"
                  variant                         int16 -61
               )
         ]
      )
   ]
'''


class BluetoothTest(unittest.TestCase):
    def test_parse_and_discover_once(self):
        devs = bt.devices(bt.parse_objects(DBUS_OUT))
        self.assertEqual(devs["11:22:33:44:55:66"]["RSSI"], -61)
        obs = {"devices": devs, "powered": True}
        ev, st = bt.detect({}, {"devices": {}, "powered": True}, 0)
        ev, st = bt.detect(st, obs, 30)
        self.assertEqual(names(ev), ["device.discovered"])
        self.assertIn("Tom's watch", ev[0].text)
        ev, _ = bt.detect(st, obs, 60)
        self.assertEqual(ev, [])

    def test_first_sight_baselines(self):
        devs = bt.devices(bt.parse_objects(DBUS_OUT))
        ev, _ = bt.detect({}, {"devices": devs, "powered": True}, 0)
        self.assertEqual(ev, [])


# -- kit -------------------------------------------------------------------------------

class KitTest(unittest.TestCase):
    def test_cooldown_and_band(self):
        with tempfile.TemporaryDirectory() as d:
            s, sf = Sense(), str(Path(d) / "x/state.json")

            def det(prev, obs, now):
                return [kit.Event("anomaly", {"kind": "x"}, "t", cooldown_s=100)], {"n": 1}
            for t in (0, 50, 150):
                kit.run_sense("netwatch", lambda: {}, det, state_file=sf, now=t, sense_mod=s)
            self.assertEqual(len(s.emits), 2)
        lv = [("low", 10), ("mid", 20), ("high", None)]
        self.assertEqual(kit.band(21, lv), "high")
        self.assertEqual(kit.band(21, lv, previous="mid", hysteresis=2), "mid")

    def test_read_failure_emits_nothing(self):
        def boom():
            raise OSError("no /proc")
        r, code = kit.run_sense("netwatch", boom, lambda *a: ([], {}), sense_mod=Sense())
        self.assertEqual((r["ok"], code), (False, 1))


class SecurityListenerTest(unittest.TestCase):
    """Banshee's S10 (Gwyn fix 2026-11-25): UDP client sockets are not listeners."""

    def test_ephemeral_and_connected_udp_skipped(self):
        sec = _load("lynx_sense_security", "security/lynx_sense_security.py")
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "net").mkdir()
            (d / "sys/net/ipv4").mkdir(parents=True)
            (d / "sys/net/ipv4/ip_local_port_range").write_text("32768\t60999\n")
            hdr = "  sl  local_address rem_address   st tx rx tr tm retr uid timeout inode\n"
            row = lambda l, r: f"   0: {l} {r} 07 00000000:00000000 00:00000000 00000000 0 0 1 2 0\n"
            (d / "net/udp").write_text(hdr + row("00000000:14E9", "00000000:0000")
                                       + row("00000000:C2AA", "00000000:0000")
                                       + row("6B64A8C0:0FA0", "0164A8C0:0035"))
            self.assertEqual([x["port"] for x in sec.read_listening_sockets(d)], [5353])


if __name__ == "__main__":
    unittest.main()
