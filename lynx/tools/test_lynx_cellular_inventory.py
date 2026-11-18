#!/usr/bin/env python3
"""Offline unit tests for lynx_cellular_inventory using temp fixtures.

These tests never touch a real device and never open a CCCI character device;
they exercise absent nodes, observed nodes, read-failure and permission-failure
paths against temporary fixtures with injected roots. The CLI tests mock
collect_inventory so the CLI can never redirect the /proc read.
"""

import contextlib
import io
import json
import os
import stat as stat_mod
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import lynx_cellular_inventory as inv


def _make_root(tmp):
    """Create an empty sysfs/dev skeleton under a temp root."""
    sysfs = Path(tmp) / "sysfs"
    (sysfs / "devices" / "platform").mkdir(parents=True)
    dev = Path(tmp) / "dev"
    dev.mkdir()
    return sysfs, dev


class TestClassifyInode(unittest.TestCase):
    def test_char_device(self):
        self.assertEqual(inv.classify_inode(stat_mod.S_IFCHR | 0o660), "char_device")

    def test_directory(self):
        self.assertEqual(inv.classify_inode(stat_mod.S_IFDIR | 0o755), "directory")

    def test_symlink(self):
        self.assertEqual(inv.classify_inode(stat_mod.S_IFLNK | 0o777), "symlink")

    def test_regular_file(self):
        self.assertEqual(inv.classify_inode(stat_mod.S_IFREG | 0o644), "file")

    def test_block_device(self):
        self.assertEqual(inv.classify_inode(stat_mod.S_IFBLK | 0o660), "block_device")

    def test_fifo(self):
        self.assertEqual(inv.classify_inode(stat_mod.S_IFIFO | 0o644), "fifo")


class TestAbsentNodes(unittest.TestCase):
    def test_all_nodes_absent_and_unreadable_is_not_claimed(self):
        with tempfile.TemporaryDirectory(prefix="lynx-sim-absent-") as tmp:
            sysfs, dev = _make_root(tmp)
            proc = Path(tmp) / "modules"
            proc.write_text("")  # readable but empty module list
            result = inv.collect_inventory(
                proc_modules=proc, sysfs_root=sysfs, dev_root=dev)
            self.assertEqual(result["label"], "inventory-only")
            self.assertFalse(result["cellular_function_validated"])
            self.assertEqual(result["modem_boot_status"], "unknown")
            self.assertEqual(result["sim_status"], "unknown")
            self.assertTrue(result["proc_modules"]["readable"])
            self.assertEqual(result["proc_modules"]["module_count"], 0)
            for node in result["sim_nodes"]:
                self.assertFalse(node["found"])
                self.assertIsNone(node["driver"])
                self.assertEqual(node["error"], "not_found")
            for node in result["ccci_devices"]:
                self.assertFalse(node["exists"])
                self.assertIsNone(node["type"])
                self.assertEqual(node["error"], "not_found")


class TestObservedNodes(unittest.TestCase):
    def test_sim_and_ccci_nodes_are_reported(self):
        with tempfile.TemporaryDirectory(prefix="lynx-sim-obs-") as tmp:
            platform = Path(tmp) / "sysfs" / "devices" / "platform"
            platform.mkdir(parents=True)

            # Node 1: a real device directory with a driver symlink.
            n1 = platform / "MD1_SIM1_HOT_PLUG_EINT"
            n1.mkdir()
            os.symlink("../../drivers/mt-sim1-detect", n1 / "driver")

            # Node 2: a symlink node; driver is resolved through the target.
            real2 = platform / "real2-device"
            real2.mkdir()
            os.symlink("../../drivers/mt-sim2-detect", real2 / "driver")
            os.symlink("real2-device", platform / "MD1_SIM2_HOT_PLUG_EINT")

            # Node 3: present directory, no driver symlink.
            (platform / "odm:oplus_sim_detect").mkdir()

            dev = Path(tmp) / "dev"
            dev.mkdir()
            for name in ("ccci_md1_sta", "ccci_ioctl0"):
                (dev / name).write_text("fixture\n")

            proc = Path(tmp) / "modules"
            proc.write_text(
                "ccci_md_all 20480 12 - Live 0x0\n"
                "ccci_auxadc 110592 4 - Live 0x0\n"
                "ccci_util_lib 12288 0 - Live 0x0\n"
                "mddp 133120 2 - Live 0x0\n"
                "snd_hrtimer 131072 1 - Live 0x0\n"
                "ccci_c2k_agps 8192 0 - Live 0x0\n")

            result = inv.collect_inventory(
                proc_modules=proc,
                sysfs_root=Path(tmp) / "sysfs",
                dev_root=dev)

            # /proc/modules: readable, count correct, cellular subset filtered.
            self.assertTrue(result["proc_modules"]["readable"])
            self.assertEqual(result["proc_modules"]["module_count"], 6)
            self.assertEqual(
                set(result["proc_modules"]["cellular_modules"]),
                {"ccci_md_all", "ccci_auxadc", "ccci_util_lib", "mddp",
                 "ccci_c2k_agps"})
            self.assertNotIn("snd_hrtimer", result["proc_modules"]["cellular_modules"])

            by_name = {n["name"]: n for n in result["sim_nodes"]}
            self.assertEqual(by_name["MD1_SIM1_HOT_PLUG_EINT"]["found"], True)
            self.assertEqual(by_name["MD1_SIM1_HOT_PLUG_EINT"]["type"], "directory")
            self.assertEqual(
                by_name["MD1_SIM1_HOT_PLUG_EINT"]["driver"],
                "../../drivers/mt-sim1-detect")
            self.assertEqual(by_name["MD1_SIM2_HOT_PLUG_EINT"]["type"], "symlink")
            self.assertEqual(
                by_name["MD1_SIM2_HOT_PLUG_EINT"]["driver"],
                "../../drivers/mt-sim2-detect")
            self.assertEqual(by_name["odm:oplus_sim_detect"]["type"], "directory")
            self.assertIsNone(by_name["odm:oplus_sim_detect"]["driver"])

            ccci = {n["name"]: n for n in result["ccci_devices"]}
            self.assertTrue(ccci["ccci_md1_sta"]["exists"])
            self.assertIn(ccci["ccci_md1_sta"]["type"], inv.VALID_TYPES)
            self.assertTrue(ccci["ccci_ioctl0"]["exists"])
            self.assertFalse(ccci["ccci_ioctl1"]["exists"])
            self.assertIsNone(ccci["ccci_ioctl2"]["type"])

            # Still inventory-only, never a functional claim.
            self.assertFalse(result["cellular_function_validated"])
            self.assertFalse(result["ccci_device_opened"])
            self.assertFalse(result["radio_activated"])


class TestReadFailure(unittest.TestCase):
    def test_unreadable_proc_modules_directory(self):
        with tempfile.TemporaryDirectory(prefix="lynx-sim-fail-") as tmp:
            sysfs, dev = _make_root(tmp)
            bad_proc = Path(tmp) / "sysfs"  # a directory: open() must fail
            result = inv.collect_inventory(
                proc_modules=bad_proc, sysfs_root=sysfs, dev_root=dev)
            self.assertFalse(result["proc_modules"]["readable"])
            self.assertEqual(result["proc_modules"]["module_count"], 0)
            self.assertIsInstance(result["proc_modules"]["error"], str)
            self.assertIn("IsADirectoryError", result["proc_modules"]["error"])
            self.assertFalse(result["cellular_function_validated"])

    def test_missing_proc_modules_path(self):
        with tempfile.TemporaryDirectory(prefix="lynx-sim-miss-") as tmp:
            sysfs, dev = _make_root(tmp)
            missing = Path(tmp) / "does_not_exist"
            result = inv.collect_inventory(
                proc_modules=missing, sysfs_root=sysfs, dev_root=dev)
            self.assertFalse(result["proc_modules"]["readable"])
            self.assertIsInstance(result["proc_modules"]["error"], str)
            self.assertIn("FileNotFoundError", result["proc_modules"]["error"])


class TestSimNodePermissionError(unittest.TestCase):
    """lstat failures other than "not found" must be reported explicitly."""

    def _make(self, tmp):
        sysfs = Path(tmp) / "sysfs"
        (sysfs / "devices").mkdir(parents=True)
        (sysfs / "bus" / "platform" / "devices").mkdir(parents=True)
        dev = Path(tmp) / "dev"
        dev.mkdir()
        proc = Path(tmp) / "modules"
        proc.write_text("")
        return sysfs, dev, proc

    @unittest.skipIf(os.geteuid() == 0, "root ignores directory mode bits")
    def test_permission_denied_is_reported_not_not_found(self):
        with tempfile.TemporaryDirectory(prefix="lynx-sim-perm-") as tmp:
            sysfs, dev, proc = self._make(tmp)
            # Both candidate parents untraversable -> EACCES, not ENOENT.
            os.chmod(sysfs / "devices", 0)
            os.chmod(sysfs / "bus", 0)
            try:
                resolved, error = inv._resolve_sim_node(
                    sysfs, "MD1_SIM1_HOT_PLUG_EINT", inv.DEFAULT_SIM_NODE_DIRS)
                result = inv.collect_inventory(
                    proc_modules=proc, sysfs_root=sysfs, dev_root=dev)
            finally:
                os.chmod(sysfs / "devices", 0o755)
                os.chmod(sysfs / "bus", 0o755)
            self.assertIsNone(resolved)
            self.assertNotEqual(error, "not_found")
            self.assertIn("PermissionError", error)
            self.assertTrue(result["sim_nodes"])
            for node in result["sim_nodes"]:
                self.assertFalse(node["found"])
                self.assertNotEqual(node["error"], "not_found")
                self.assertIn("PermissionError", node["error"])

    @unittest.skipIf(os.geteuid() == 0, "root ignores directory mode bits")
    def test_found_node_wins_over_earlier_permission_error(self):
        with tempfile.TemporaryDirectory(prefix="lynx-sim-perm-ok-") as tmp:
            sysfs, dev, proc = self._make(tmp)
            target = (sysfs / "bus" / "platform" / "devices"
                      / "MD1_SIM2_HOT_PLUG_EINT")
            target.mkdir(parents=True)
            os.chmod(sysfs / "devices", 0)  # blocks candidate 1 only
            try:
                resolved, error = inv._resolve_sim_node(
                    sysfs, "MD1_SIM2_HOT_PLUG_EINT", inv.DEFAULT_SIM_NODE_DIRS)
                result = inv.collect_inventory(
                    proc_modules=proc, sysfs_root=sysfs, dev_root=dev)
            finally:
                os.chmod(sysfs / "devices", 0o755)
            self.assertEqual(resolved, target)
            self.assertIsNone(error)
            entry = next(n for n in result["sim_nodes"]
                         if n["name"] == "MD1_SIM2_HOT_PLUG_EINT")
            self.assertTrue(entry["found"])
            self.assertIsNone(entry["error"])


class TestMainCli(unittest.TestCase):
    """CLI must stay mock-verified: it can never redirect the proc read."""

    def _readable_fixture(self):
        return {
            "schema": inv.SCHEMA,
            "tool": inv.TOOL,
            "label": "inventory-only",
            "cellular_function_validated": False,
            "ccci_device_opened": False,
            "radio_activated": False,
            "constraints": {
                "no_subprocess": True,
                "no_ccci_device_open": True,
            },
            "proc_modules": {
                "readable": True,
                "module_count": 1,
                "cellular_modules": ["ccci_md_all"],
                "error": None,
            },
            "sim_nodes": [],
            "ccci_devices": [],
        }

    def test_main_uses_fixed_roots_and_prints_compact_json(self):
        with mock.patch.object(inv, "collect_inventory",
                               return_value=self._readable_fixture()) as spy:
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                rc = inv.main([])
        # Called with no arguments: the CLI can never redirect the proc read.
        spy.assert_called_once_with()
        self.assertEqual(rc, 0)
        output = buffer.getvalue().strip()
        self.assertEqual(output.count("\n"), 0)  # compact single line
        data = json.loads(output)
        self.assertEqual(data["schema"], inv.SCHEMA)
        self.assertEqual(data["label"], "inventory-only")
        self.assertFalse(data["cellular_function_validated"])
        self.assertFalse(data["ccci_device_opened"])
        self.assertFalse(data["radio_activated"])
        self.assertTrue(data["constraints"]["no_subprocess"])
        self.assertTrue(data["constraints"]["no_ccci_device_open"])

    def test_main_rejects_path_override_options(self):
        with mock.patch.object(inv, "collect_inventory") as spy:
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                with self.assertRaises(SystemExit) as caught:
                    inv.main(["--proc-modules", "/dev/ccci_md1_sta"])
        self.assertNotEqual(caught.exception.code, 0)
        spy.assert_not_called()
        self.assertEqual(buffer.getvalue(), "")

    def test_main_exits_nonzero_with_error_json_when_proc_unreadable(self):
        fixture = self._readable_fixture()
        fixture["proc_modules"] = {
            "readable": False,
            "module_count": 0,
            "cellular_modules": [],
            "error": "PermissionError: [Errno 13] Permission denied",
        }
        with mock.patch.object(inv, "collect_inventory",
                               return_value=fixture) as spy:
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                rc = inv.main([])
        spy.assert_called_once_with()
        self.assertEqual(rc, 1)
        data = json.loads(buffer.getvalue().strip())
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "proc_modules_unreadable")
        self.assertEqual(data["path"], str(inv.DEFAULT_PROC_MODULES))
        self.assertIn("PermissionError", data["detail"])


if __name__ == "__main__":
    unittest.main()
