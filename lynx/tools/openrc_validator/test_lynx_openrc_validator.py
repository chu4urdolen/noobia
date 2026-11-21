#!/usr/bin/env python3
"""Unit tests for the Lynx OpenRC service-tree validator (D28)."""

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

from lynx_openrc_validator import (
    EXPECTED_CHAIN,
    KNOWN_EXTERNAL,
    ParseError,
    ServiceDef,
    SpecError,
    parse_depend_block,
    parse_initd,
    parse_service_def,
    run_offline,
    validate_fixture,
    validate_tree,
)

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
TOOL = HERE / "lynx_openrc_validator.py"
WATCHDOG_INITD = HERE.parent / "watchdog_daemon" / "lynx-watchdogd.initd"
SURVIVAL_INITD = HERE.parent / "survival_daemon" / "lynx-survivald.initd"

GOOD_BLOCK = (
    '#!/openrc-bin/sh\n'
    'name=test\n'
    'depend() {\n'
    '\tneed bootmisc sysfs\n'
    '\tuse local\n'
    '\tafter lynx-watchdogd\n'
    '\tbefore net\n'
    '\tprovide testd\n'
    '}\n'
    'start() { :; }\n'
)


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        capture_output=True,
        text=True,
        timeout=30,
    )


def services_from(doc: dict):
    return {e["name"]: parse_service_def(e) for e in doc["services"]}


class TestParseDependBlock(unittest.TestCase):
    def test_full_block_parses(self):
        deps = parse_depend_block(GOOD_BLOCK, "test")
        self.assertEqual(deps["need"], ["bootmisc", "sysfs"])
        self.assertEqual(deps["use"], ["local"])
        self.assertEqual(deps["after"], ["lynx-watchdogd"])
        self.assertEqual(deps["before"], ["net"])
        self.assertEqual(deps["provide"], ["testd"])

    def test_comments_and_blank_lines_skipped(self):
        text = 'depend() {\n\t# a comment\n\n\tneed bootmisc\n}\n'
        self.assertEqual(parse_depend_block(text)["need"], ["bootmisc"])

    def test_unknown_directive_rejected(self):
        with self.assertRaises(ParseError):
            parse_depend_block('depend() {\n\twant bootmisc\n}', "t")

    def test_no_services_rejected(self):
        with self.assertRaises(ParseError):
            parse_depend_block('depend() {\n\tneed\n}', "t")

    def test_invalid_name_rejected(self):
        with self.assertRaises(ParseError):
            parse_depend_block('depend() {\n\tneed Bad-Name\n}', "t")

    def test_no_depend_block_rejected(self):
        with self.assertRaises(ParseError):
            parse_depend_block("name=x\nstart() { :; }\n", "t")

    def test_unterminated_rejected(self):
        with self.assertRaises(ParseError):
            parse_depend_block('depend() {\n\tneed bootmisc\n', "t")


class TestStagedInitds(unittest.TestCase):
    def test_watchdogd_initd_parses(self):
        svc = parse_initd(WATCHDOG_INITD.read_text(encoding="utf-8"), "lynx-watchdogd")
        self.assertEqual(svc.need, ("bootmisc", "sysfs"))
        self.assertEqual(svc.before, ("net",))
        self.assertIn("watchdog", svc.provides)

    def test_survivald_initd_parses(self):
        svc = parse_initd(SURVIVAL_INITD.read_text(encoding="utf-8"), "lynx-survivald")
        self.assertEqual(svc.need, ("bootmisc", "sysfs"))
        self.assertEqual(svc.after, ("lynx-watchdogd",))
        self.assertEqual(svc.before, ("net",))

    def test_staged_pair_validates_pass(self):
        services = {
            "lynx-watchdogd": parse_initd(WATCHDOG_INITD.read_text(encoding="utf-8"), "lynx-watchdogd"),
            "lynx-survivald": parse_initd(SURVIVAL_INITD.read_text(encoding="utf-8"), "lynx-survivald"),
        }
        report = validate_tree(services, KNOWN_EXTERNAL)
        self.assertEqual(report.verdict, "PASS")
        self.assertLess(report.startup_order.index("lynx-watchdogd"),
                        report.startup_order.index("lynx-survivald"))


class TestValidatorClassification(unittest.TestCase):
    def test_clean_chain_passes_with_expected_order(self):
        doc = load("openrc-chain-pass.json")
        report = validate_tree(services_from(doc), tuple(doc["known_external"]))
        self.assertEqual(report.verdict, "PASS")
        self.assertEqual(report.startup_order, list(EXPECTED_CHAIN))
        self.assertEqual(report.shutdown_order, list(reversed(EXPECTED_CHAIN)))
        self.assertEqual(report.hard_cycles, [])
        self.assertEqual(report.missing_prerequisites, [])

    def test_need_cycle_is_hard_deadlock(self):
        doc = load("openrc-chain-hard-deadlock.json")
        report = validate_tree(services_from(doc), tuple(doc["known_external"]))
        self.assertEqual(report.verdict, "FAIL")
        self.assertIn(["lynx-agent", "lynx-presence"], report.hard_cycles)

    def test_missing_prerequisite_flagged(self):
        doc = load("openrc-chain-hard-deadlock.json")
        report = validate_tree(services_from(doc), tuple(doc["known_external"]))
        self.assertIn(["lynx-agent", "lynx-gateway"], report.missing_prerequisites)

    def test_weak_conflict_flagged(self):
        doc = load("openrc-chain-order-conflict.json")
        report = validate_tree(services_from(doc), tuple(doc["known_external"]))
        self.assertEqual(report.verdict, "FAIL")
        self.assertIn(["lynx-survivald", "lynx-watchdogd"], report.order_conflicts)

    def test_weak_consistent_cycle_is_informative(self):
        services = {
            "alpha": ServiceDef("alpha", before=("beta",)),
            "beta": ServiceDef("beta", before=("gamma",)),
            "gamma": ServiceDef("gamma", before=("alpha",)),
        }
        report = validate_tree(services, ())
        self.assertEqual(report.verdict, "PASS")
        self.assertIn(["alpha", "beta", "gamma"], report.weak_cycles)

    def test_self_need_is_deadlock(self):
        services = {"solo": ServiceDef("solo", need=("solo",))}
        report = validate_tree(services, ())
        self.assertEqual(report.verdict, "FAIL")
        self.assertIn(["solo"], report.hard_cycles)

    def test_self_weak_is_order_conflict(self):
        services = {"solo": ServiceDef("solo", before=("solo",))}
        report = validate_tree(services, ())
        self.assertEqual(report.verdict, "FAIL")
        self.assertIn(["solo"], report.order_conflicts)

    def test_provided_name_resolves_to_provider(self):
        services = {
            "lynx-watchdogd": ServiceDef("lynx-watchdogd", provides=("watchdog",)),
            "lynx-agent": ServiceDef("lynx-agent", need=("watchdog",)),
        }
        report = validate_tree(services, ())
        self.assertEqual(report.missing_prerequisites, [])
        self.assertLess(
            report.startup_order.index("lynx-watchdogd"),
            report.startup_order.index("lynx-agent"))

    def test_shutdown_is_reverse_of_startup(self):
        doc = load("openrc-chain-pass.json")
        report = validate_tree(services_from(doc), tuple(doc["known_external"]))
        self.assertEqual(report.shutdown_order, list(reversed(report.startup_order)))


class TestSpecValidation(unittest.TestCase):
    def test_missing_platform_rejected(self):
        doc = load("openrc-chain-pass.json")
        del doc["platform"]
        with self.assertRaises(SpecError):
            validate_fixture(doc)

    def test_duplicate_service_names_rejected(self):
        doc = load("openrc-chain-pass.json")
        doc["services"].append({"name": "bootmisc"})
        with self.assertRaises(SpecError) as ctx:
            validate_fixture(doc)
        self.assertTrue(any("duplicate" in r for r in ctx.exception.reasons))

    def test_bad_verdict_rejected(self):
        doc = load("openrc-chain-pass.json")
        doc["expected"]["verdict"] = "MAYBE"
        with self.assertRaises(SpecError):
            validate_fixture(doc)

    def test_empty_services_rejected(self):
        doc = load("openrc-chain-pass.json")
        doc["services"] = []
        with self.assertRaises(SpecError):
            validate_fixture(doc)

    def test_bad_service_name_rejected(self):
        doc = load("openrc-chain-pass.json")
        doc["services"][0]["name"] = "Boot-Misc"
        with self.assertRaises(SpecError):
            validate_fixture(doc)


class TestCli(unittest.TestCase):
    def test_fixture_pass_exit_zero(self):
        proc = run_cli("--validate", str(FIXTURES / "openrc-chain-pass.json"))
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_fixture_hard_deadlock_exit_zero(self):
        proc = run_cli("--validate", str(FIXTURES / "openrc-chain-hard-deadlock.json"))
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_fixture_order_conflict_exit_zero(self):
        proc = run_cli("--validate", str(FIXTURES / "openrc-chain-order-conflict.json"))
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_live_requires_double_flag(self):
        proc = run_cli("--live")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("REFUSED", proc.stderr)

    def test_live_double_flag_exit_zero(self):
        proc = run_cli("--live", "--allow-live")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("INSPECTED", proc.stdout)

    def test_no_args_help_exit_two(self):
        proc = run_cli()
        self.assertEqual(proc.returncode, 2)
        self.assertIn("usage:", proc.stdout)

    def test_missing_fixture_exit_one(self):
        proc = run_cli("--validate", "/no/such/fixture.json")
        self.assertEqual(proc.returncode, 1)

    def test_malformed_json_exit_one(self):
        bad = Path("/tmp/d28_test_bad_fixture.json")
        bad.write_text("{ not json", encoding="utf-8")
        proc = run_cli("--validate", str(bad))
        self.assertEqual(proc.returncode, 1)


class TestSafetyBoundaries(unittest.TestCase):
    SRC = TOOL.read_text(encoding="utf-8")

    def test_no_os_module_at_all(self):
        self.assertNotIn("import os", self.SRC)
        self.assertNotIn("os.", self.SRC)

    def test_no_forbidden_runtime_tokens(self):
        for token in (
            "subprocess", "socket", "threading", "multiprocessing", "shutil",
            "urllib", "requests", "ctypes", "eval(", "exec(", "fork",
            "systemctl", "rm -rf", "curl ", "wget ", "iptables", "open(",
        ):
            self.assertNotIn(token, self.SRC, token)

    def test_no_path_mutations(self):
        for token in (".mkdir(", ".makedirs(", ".unlink(", ".rmdir(",
                      ".chmod(", ".chown(", ".symlink(", ".rename("):
            self.assertNotIn(token, self.SRC, token)

    def test_broker_path_constant_only(self):
        occurrences = [m.start() for m in re.finditer(re.escape("/tmp/lynx_openrc_state.json"), self.SRC)]
        self.assertEqual(len(occurrences), 1)
        self.assertIn("DEFAULT_STATE_FILE", self.SRC)

    def test_never_touches_etc_initd(self):
        self.assertNotIn("/etc/init.d", self.SRC)

    def test_no_initd_staged_here(self):
        # D28 ships the validator only; the staged initds it reads live in
        # the D25/D26 tool directories.
        self.assertFalse(any(p.suffix == ".initd" for p in HERE.iterdir()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
