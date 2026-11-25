#!/usr/bin/env python3
"""LNX-73: the broker runs only catalogued tools with schema-valid arguments, for allowed callers."""
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lynx_tool_broker as b  # noqa: E402
import lynx_agent  # noqa: E402
import lynx_agent_worker as w  # noqa: E402


def make_tool(root: Path, name: str, props: dict, required=(), body='cat'):
    (root / f"{name}.json").write_text(json.dumps({"description": name, "timeout": 5, "inputSchema": {
        "type": "object", "properties": props, "required": list(required), "additionalProperties": False}}))
    (root / f"{name}.sh").write_text(f"#!/bin/sh\n{body}\n")


class BrokerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tools = Path(self.tmp.name) / "tools"
        self.tools.mkdir()
        make_tool(self.tools, "lynx_speech", {"text": {"type": "string"}}, ["text"])
        make_tool(self.tools, "lynx_media_play", {"kind": {"type": "string", "enum": ["sound", "image"]},
                                                  "item": {"type": "string"}}, ["kind", "item"])
        make_tool(self.tools, "lynx_codex", {"prompt": {"type": "string"}}, ["prompt"])

    def tearDown(self):
        self.tmp.cleanup()

    def run_tool(self, tool, args, exclude=()):
        return b.run_tool({"tool": tool, "args": args, "exclude": list(exclude)}, self.tools)

    def test_runs_a_catalogued_tool_with_json_on_stdin(self):
        r = self.run_tool("lynx_speech", {"text": "Hello"})
        self.assertTrue(r["ok"], r)
        self.assertEqual(json.loads(r["output"]), {"text": "Hello"})

    def test_refuses_what_the_schema_does_not_allow(self):
        self.assertIn("missing", self.run_tool("lynx_speech", {})["error"])
        self.assertIn("unknown argument", self.run_tool("lynx_speech", {"text": "x", "cmd": "rm"})["error"])
        self.assertIn("must be string", self.run_tool("lynx_speech", {"text": 5})["error"])
        self.assertIn("one of", self.run_tool("lynx_media_play", {"kind": "shell", "item": "x"})["error"])

    def test_refuses_unknown_paths_symlinks_and_excluded_tools(self):
        self.assertEqual(self.run_tool("../../bin/sh", {})["error"], "invalid tool name")
        self.assertEqual(self.run_tool("lynx_nothing", {})["error"], "unknown tool")
        os.symlink("/bin/true", self.tools / "lynx_evil.sh")
        (self.tools / "lynx_evil.json").write_text(json.dumps({"inputSchema": {"type": "object"}}))
        self.assertEqual(self.run_tool("lynx_evil", {})["error"], "unknown tool")
        self.assertIn("not available", self.run_tool("lynx_codex", {"prompt": "x"}, exclude=["lynx_codex"])["error"])

    def serve(self, allowed):
        sock = Path(self.tmp.name) / "broker.sock"
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(str(sock))
        srv.listen(4)
        log = Path(self.tmp.name) / "broker.jsonl"
        old = b.LOG
        b.LOG = log

        def loop():
            while True:
                try:
                    conn, _ = srv.accept()
                except OSError:
                    return
                b.handle(conn, allowed, self.tools)
        threading.Thread(target=loop, daemon=True).start()

        def stop():
            srv.close()
            b.LOG = old
        self.addCleanup(stop)
        return sock, log

    def test_round_trip_over_the_socket_with_peer_uid(self):
        sock, log = self.serve({os.getuid()})
        r = b.call("lynx_speech", {"text": "Hi"}, path=sock)
        self.assertTrue(r["ok"], r)
        r2 = lynx_agent.broker_call("lynx_speech", {"text": "Hi again"}, path=sock)   # the agent's client
        self.assertEqual(json.loads(r2["output"]), {"text": "Hi again"})
        time.sleep(0.1)
        rows = [json.loads(l) for l in log.read_text().splitlines()]
        self.assertEqual([(r["tool"], r["ok"], r["uid"]) for r in rows],
                         [("lynx_speech", True, os.getuid())] * 2)
        self.assertNotIn("Hi", log.read_text(), "arguments are never logged")

    def test_other_uids_are_refused(self):
        sock, _ = self.serve({os.getuid() + 12345})
        self.assertEqual(b.call("lynx_speech", {"text": "Hi"}, path=sock)["error"], "caller not allowed")

    def test_missing_broker_is_an_honest_error(self):
        r = lynx_agent.broker_call("lynx_speech", {"text": "x"}, path=Path(self.tmp.name) / "none.sock", timeout=2)
        self.assertIn("broker unavailable", r["error"])

    def test_unprivileged_catalog_fails_closed_when_broker_is_absent(self):
        catalog = lynx_agent.Catalog(self.tools)
        with patch.object(lynx_agent.os, "geteuid", return_value=1000), \
             patch.object(lynx_agent, "BROKER", Path(self.tmp.name) / "none.sock"):
            result = catalog.run("lynx_speech", {"text": "Hello"})
        self.assertFalse(result["ok"])
        self.assertIn("broker unavailable", result["error"])


class WorkerTest(unittest.TestCase):
    def test_agent_runs_unprivileged_when_a_user_is_set(self):
        self.assertEqual(w.agent_command(), ["/usr/bin/python3", w.AGENT, "--stdin"])
        self.assertEqual(w.agent_privileges(""), {})
        import pwd
        me = pwd.getpwuid(os.getuid()).pw_name if os.getuid() else "nobody"
        kw = w.agent_privileges(me)
        self.assertEqual(kw["user"], pwd.getpwnam(me).pw_uid)
        self.assertEqual(kw["extra_groups"], [])
        self.assertIs(kw["preexec_fn"], w._no_new_privs)
        with self.assertRaises(ValueError):
            w.agent_privileges("root")

    def test_no_new_privs_really_applies(self):
        import subprocess, sys
        r = subprocess.run([sys.executable, "-c", "print(open('/proc/self/status').read())"],
                           capture_output=True, text=True, preexec_fn=w._no_new_privs)
        self.assertIn("NoNewPrivs:\t1", r.stdout)

if __name__ == "__main__":
    unittest.main()
