#!/usr/bin/env python3
"""lynx-exposure-audit on a fake /proc: expected, unexpected and weakened listeners."""
import os
from pathlib import Path
import socket
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lynx_exposure_audit as a  # noqa: E402

HEADER = "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"


def hexaddr(ip: str, port: int) -> str:
    return "%08X:%04X" % (struct.unpack("<I", socket.inet_aton(ip))[0], port)


class FakeLynx:
    def __init__(self, root: Path):
        self.root, self.proc, self.sys = root, root / "proc", root / "sys"
        (self.proc / "net").mkdir(parents=True)
        (self.proc / "sys" / "net" / "ipv4").mkdir(parents=True)
        (self.proc / "sys" / "net" / "ipv6" / "conf" / "all").mkdir(parents=True)
        (self.proc / "sys" / "kernel").mkdir(parents=True)
        (self.sys / "class" / "net" / "lo").mkdir(parents=True)
        (self.proc / "sys" / "net" / "ipv4" / "ip_forward").write_text("0\n")
        (self.proc / "sys" / "net" / "ipv6" / "conf" / "all" / "disable_ipv6").write_text("0\n")
        (self.proc / "sys" / "kernel" / "osrelease").write_text("5.10.149-test\n")
        (self.sys / "class" / "net" / "lo" / "operstate").write_text("down\n")
        self.tcp, self.inode = [HEADER], 1000
        for f in ("tcp6", "udp", "udp6"):
            (self.proc / "net" / f).write_text(HEADER)

    def listen(self, ip, port, cmdline, pid):
        self.inode += 1
        self.tcp.append(f"   0: {hexaddr(ip, port)} 00000000:0000 0A 00000000:00000000 00:00000000 00000000 0 0 {self.inode} 1\n")
        (self.proc / "net" / "tcp").write_text("".join(self.tcp))
        d = self.proc / str(pid)
        (d / "fd").mkdir(parents=True)
        (d / "cmdline").write_bytes("\0".join(cmdline).encode() + b"\0")
        os.symlink(f"socket:[{self.inode}]", d / "fd" / "3")

    def audit(self, firewall=()):
        return a.audit(self.proc, which=lambda t: f"/usr/sbin/{t}" if t in firewall else None,
                       run=lambda *x, **k: type("R", (), {"stdout": "Dropbear v2025.88", "stderr": ""})(),
                       sys_root=self.sys)


LAN = "192.168.100.107"
SSH = ["/usr/sbin/dropbear", "-E", "-s", "-j", "-k", "-p", f"{LAN}:2222"]
RESCUE = ["/usr/sbin/dropbear", "-F", "-E", "-s", "-j", "-k", "-p", f"{LAN}:22"]
NRP = ["/usr/bin/python3", "/usr/local/bin/lynx-noobd", "--port", "4243", "--peer", "192.168.100.106",
       "--nexus-key-file", "/etc/lynx/nrp-nexus.key"]


class AuditTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.lynx = FakeLynx(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def ids(self, report):
        return {f["id"].split(":")[0] for f in report["findings"]}

    def test_todays_lynx_is_ok_with_warnings(self):
        for i, cmd in enumerate((SSH, RESCUE, NRP)):
            self.lynx.listen(LAN, [2222, 22, 4243][i], cmd, 100 + i)
        r = self.lynx.audit()
        self.assertTrue(r["ok"], r["findings"])
        self.assertEqual({l["service"] for l in r["listeners"]},
                         {"Alpine SSH (dropbear)", "early-boot rescue SSH (dropbear)", "NRP daemon to Nexus (lynx-noobd)"})
        self.assertEqual(self.ids(r), {"rescue-ssh-still-open", "no-firewall", "loopback-down"})
        self.assertIn("password logins disabled", r["listeners"][0]["protections"])
        self.assertEqual(r["versions"]["kernel"], "5.10.149-test")

    def test_unexpected_listener_is_high(self):
        self.lynx.listen("0.0.0.0", 8000, ["/usr/bin/python3", "-m", "http.server"], 200)
        r = self.lynx.audit(firewall=("nft",))
        self.assertFalse(r["ok"])
        self.assertIn("unexpected-listener", self.ids(r))
        self.assertIn("wide-bind", self.ids(r))
        self.assertNotIn("no-firewall", self.ids(r))

    def test_ssh_with_passwords_is_high(self):
        self.lynx.listen(LAN, 2222, ["/usr/sbin/dropbear", "-p", f"{LAN}:2222"], 300)
        r = self.lynx.audit()
        self.assertFalse(r["ok"])
        self.assertTrue(any("password logins disabled" in f["text"] for f in r["findings"]))

    def test_text_report_is_short_and_says_why(self):
        self.lynx.listen(LAN, 2222, SSH, 100)
        text = a.text_report(self.lynx.audit())
        self.assertTrue(text.startswith("Lynx exposure audit: OK"))
        self.assertIn("no firewall tool", text)


if __name__ == "__main__":
    unittest.main()
