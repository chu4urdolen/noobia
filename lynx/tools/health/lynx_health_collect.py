#!/usr/bin/env python3
"""Read-only collector: Lynx facts -> portable-health/1 snapshot.

Solo Dushich's collection seam for the portable health board (forge notes
#82, #101, #112). It runs up to THREE bounded, read-only commands on Lynx
over the existing pinned-SSH route (BatchMode, pinned key, port 2222 by
default). The three commands share ONE total timeout budget, and each one
feeds a different part of the snapshot:

  1. ``/usr/local/bin/lynx-status``
     the phone's own status JSON (schema 2) -> the common facts
     (battery, thermal, storage, network, services);
  2. ``/usr/local/bin/lynx-platform-status cellular``
     the phone's read-only CCCI inventory -> the machine fact
     ``modem_md1_state`` (from ``evidence.md1_state_code``, an int parsed
     from ``/sys/kernel/ccci/boot`` — no CCCI ioctl, no radio);
  3. ``/usr/local/bin/lynx-agent-health``
     a read-only scan of ``/var/lib/lynx-agent`` -> the machine facts
     ``pending``, ``running``, ``oldest_pending_seconds``.

Guarantees, per the task briefs (#101, #103, #112):
  * per-command AND total timeouts (one shared deadline), with an output
    cap on captured stdout;
  * a missing, failing, timed-out, runner-error, or unparseable source
    leaves that section of the facts *absent* — the evaluator then reports
    ``unknown``, never ``ok``. Nothing is fabricated;
  * only these read-only commands; no writes on Lynx, no prompts, no
    interactive input (BatchMode), no other commands;
  * no exception from the runner escapes ``collect()`` (Aria #103): a
    runner failure is recorded on the command entry and its facts stay
    absent;
  * Nexus-specific GPU/RAM/SMART facts are deliberately NOT collected
    here; that stays a separate seam (Aigel's Nexus board owns it).

Known limit (Aria #103, documented): ``subprocess.run(capture_output=True)``
buffers the complete output before the cap is applied, so memory use is
not strictly bounded by ``max_output`` for a pathological command. The
three commands are the phone's own bounded status tools; the cap is a
guard, not a memory guarantee.

The runner is injectable, so the offline test suite never touches the
network. The default runner reuses the house pinned-SSH pattern
(``lynx_wifi_v19_contact.ssh_command`` + the ``-p PORT`` splice), exactly
like ``lynx_remote.py``.

CLI:
  lynx_health_collect.py                     # snapshot JSON on stdout
  lynx_health_collect.py --evaluate          # snapshot -> report JSON; exit = verdict
  lynx_health_collect.py --evaluate --max-age 300
Exit codes for --evaluate: 0 ok, 1 warn, 2 fail, 3 unknown, 4 invalid.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections import namedtuple
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from portable_health import SCHEMA, evaluate  # noqa: E402

TOOLS_DIR = Path(__file__).resolve().parent.parent

DEFAULT_IP = "192.168.100.107"
DEFAULT_PORT = 2222
DEFAULT_PER_CMD_TIMEOUT = 15.0
DEFAULT_TOTAL_TIMEOUT = 45.0
DEFAULT_MAX_OUTPUT = 12000

LINUX_STATUS_CMD = "/usr/local/bin/lynx-status"
CELLULAR_CMD = "/usr/local/bin/lynx-platform-status cellular"
AGENT_HEALTH_CMD = "/usr/local/bin/lynx-agent-health"

# (label, command): three bounded read-only commands, one shared deadline.
COMMANDS = (
    ("lynx-status", LINUX_STATUS_CMD),
    ("cellular", CELLULAR_CMD),
    ("agent-queue", AGENT_HEALTH_CMD),
)

RunnerResult = namedtuple("RunnerResult", ["exit", "stdout", "stderr"])


class RunnerTimeout(Exception):
    """The remote command did not finish within its allotted time."""


def make_ssh_runner(ip: str, port: int):
    """Default runner: one pinned-SSH command on Lynx, batch-mode only."""
    sys.path.insert(0, str(TOOLS_DIR))
    from lynx_wifi_v19_contact import ssh_command  # lazy: tests never need it

    def runner(command: str, timeout: float) -> RunnerResult:
        argv = ssh_command(ip, command)
        argv[-2:-2] = ["-p", str(port)]
        try:
            result = subprocess.run(argv, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise RunnerTimeout(command) from exc
        return RunnerResult(
            result.returncode,
            result.stdout.decode(errors="replace"),
            result.stderr.decode(errors="replace"),
        )

    return runner


def _clip(text: str, limit: int) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n[... clipped {len(text) - limit} chars]"


def _num(value):
    """int/float (not bool, not strings) -> float; anything else -> None."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _int(value):
    """int (not bool), or an integral float -> int; anything else -> None."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def map_lynx_status(state: dict):
    """Map phone-side lynx-status JSON (schema 2) to evaluator facts.

    Only fields that are present and correctly typed pass through; unit
    conversions are explicit (milli-degrees C -> degrees C; milliamps stay
    milliamps under the evaluator's name ``current_ma``). Missing fields
    are simply omitted: absence is what makes the evaluator say ``unknown``.
    Returns (facts, notes).
    """
    facts: dict = {}
    notes: list = []

    battery = state.get("battery")
    if isinstance(battery, dict):
        b: dict = {}
        cap = _num(battery.get("capacity_percent"))
        if cap is not None:
            b["capacity_percent"] = cap
        cur = _num(battery.get("current_mA_signed"))
        if cur is not None:
            b["current_ma"] = cur
        # Keep the phone's native milli-degrees in the _mc field: no
        # lossy conversion, and the field name says "mc" (milli-celsius).
        temp_mc = _num(battery.get("temperature_mC"))
        if temp_mc is not None:
            b["temperature_mc"] = temp_mc
        read_errors = battery.get("read_errors")
        if isinstance(read_errors, dict) and read_errors:
            values = [_num(v) for v in read_errors.values()]
            if all(v is not None for v in values):
                b["gauge_read_errors"] = sum(values)
            else:
                notes.append("battery: some gauge read-error counters missing; "
                             "gauge_read_errors left unknown")
        if b:
            facts["battery"] = b
        notes.append("battery: charging state is not reported by lynx-status; "
                     "the evaluator treats it as absent")

    thermal = state.get("thermal")
    if isinstance(thermal, dict):
        t: dict = {}
        max_mc = _num(thermal.get("max_mC"))
        if max_mc is not None:
            t["max_c"] = max_mc / 1000.0
        cooling = thermal.get("cooling_states")
        if isinstance(cooling, dict):
            states = [_num(v) for v in cooling.values()]
            states = [v for v in states if v is not None]
            if states and any(v > 0 for v in states):
                t["throttled"] = True
                notes.append("thermal: throttled derived from a nonzero "
                             "cpufreq cooling state")
        if t:
            facts["thermal"] = t

    storage: dict = {}
    free = _num(state.get("root_free_mib"))
    if free is not None:
        storage["free_mib"] = free
    rootfs = state.get("root_filesystem")
    if isinstance(rootfs, dict):
        errors = _num(rootfs.get("ext4_errors_count"))
        if errors is not None:
            storage["fs_errors"] = errors
    if storage:
        facts["storage"] = storage
        notes.append("storage: used_percent is not reported by lynx-status; "
                     "the evaluator judges free space")

    wifi = state.get("wifi")
    if isinstance(wifi, dict):
        carrier = wifi.get("carrier")
        ipv4 = wifi.get("ipv4")
        n: dict = {}
        if isinstance(carrier, bool):
            n["carrier"] = carrier
            n["link_state"] = "wifi" if carrier else "none"
            if not carrier:
                notes.append("network: link_state=none reflects the wifi interface; "
                             "a USB link (if the host reached Lynx over USB) is not "
                             "observable from this snapshot")
        if isinstance(ipv4, str) and ipv4.strip():
            n["ipv4"] = ipv4.strip()
        if n:
            facts["network"] = n

    services = state.get("services_running")
    if isinstance(services, dict) and services:
        required = [str(k) for k in services]
        running = [str(k) for k, v in services.items() if v is True]
        failed = [str(k) for k, v in services.items() if v is not True]
        facts["services"] = {"required": required, "running": running,
                             "failed": failed}

    return facts, notes


def map_cellular(component):
    """Map the phone's ``lynx-platform-status cellular`` component.

    Only a well-typed non-negative integer ``md1_state_code`` passes
    through, as ``modem_md1_state``. The phone reports
    ``validated: false``: the CCCI nodes and the MD1 boot code are
    interface evidence, not proof of a working modem — and no CCCI ioctl
    or radio is used, consistent with the MD1 no-go. Returns
    (machine_facts, notes).
    """
    notes: list = []
    if not isinstance(component, dict):
        return {}, ["cellular: output is not the expected component object; "
                    "modem state stays unknown"]
    if component.get("error"):
        return {}, [f"cellular: phone reported {component['error']!r}; "
                    "modem state stays unknown"]
    evidence = component.get("evidence")
    if not isinstance(evidence, dict):
        return {}, ["cellular: no evidence object; modem state stays unknown"]
    md1 = _int(evidence.get("md1_state_code"))
    if md1 is None or md1 < 0:
        return {}, ["cellular: md1_state_code absent or not a non-negative "
                    "integer; modem state stays unknown"]
    notes.append(
        f"cellular: interface_ready={component.get('interface_ready')!r}, "
        f"ccci_nodes={evidence.get('ccci_node_count')!r}; modem runtime "
        "remains unverified (md1 read from /sys/kernel/ccci/boot; no CCCI "
        "ioctl, no radio)")
    return {"modem_md1_state": md1}, notes


def map_agent_queue(data):
    """Map the phone's ``lynx-agent-health`` JSON.

    ``counts.pending/running`` and ``oldest_pending_seconds`` are read-only
    facts about ``/var/lib/lynx-agent``; only well-typed non-negative
    integers pass through. ``stopped`` and ``issues`` are context notes,
    not judged facts. Returns (machine_facts, notes).
    """
    notes: list = []
    machine: dict = {}
    if not isinstance(data, dict):
        return {}, ["agent-queue: output is not a JSON object; queue facts "
                    "stay unknown"]
    counts = data.get("counts")
    if not isinstance(counts, dict):
        notes.append("agent-queue: no counts object; pending/running stay unknown")
    else:
        for key in ("pending", "running"):
            value = _int(counts.get(key))
            if value is None or value < 0:
                notes.append(f"agent-queue: counts.{key} absent or malformed; "
                             "left unknown")
            else:
                machine[key] = value
        done = _int(counts.get("done"))
        if done is not None and done >= 0:
            notes.append(f"agent-queue: {done} finished job(s) on disk")
    oldest = _int(data.get("oldest_pending_seconds"))
    if oldest is not None and oldest >= 0:
        machine["oldest_pending_seconds"] = oldest
    if data.get("stopped") is True:
        notes.append("agent-queue: stop marker present (lynx-agentctl stop "
                     "was issued)")
    issues = data.get("issues")
    if isinstance(issues, list) and issues:
        notes.append("agent-queue: " + ", ".join(str(i) for i in issues[:8]))
    return machine, notes


def collect(runner, *, ip: str = DEFAULT_IP, port: int = DEFAULT_PORT,
            per_cmd_timeout: float = DEFAULT_PER_CMD_TIMEOUT,
            total_timeout: float = DEFAULT_TOTAL_TIMEOUT,
            max_output: int = DEFAULT_MAX_OUTPUT, now=None) -> dict:
    """Run the bounded read-only commands and build a snapshot.

    The commands in ``COMMANDS`` share one total timeout budget; when the
    budget is spent, the remaining commands are skipped and their facts
    stay absent. ``runner(command, timeout)`` must return a RunnerResult
    or raise — RunnerTimeout or any other exception — and no exception
    from the runner escapes this function (Aria #103): a failed command
    simply leaves its facts unknown.

    ``now`` may be a datetime or an ISO-8601 string (handy for
    deterministic tests); the snapshot records the moment of collection.
    """
    deadline = time.monotonic() + total_timeout
    source = {"transport": "ssh-pinned-key", "ip": ip, "port": port,
              "commands": [], "issues": [], "notes": []}
    parsed: dict = {}

    for label, command in COMMANDS:
        entry: dict = {"name": command, "exit": None, "stdout_bytes": 0,
                       "truncated": False, "ok": False}
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            entry["error"] = "total timeout budget exhausted before the command"
        else:
            timeout = min(per_cmd_timeout, max(remaining, 0.01))
            try:
                result = runner(command, timeout)
            except RunnerTimeout:
                entry["error"] = f"timeout after {timeout:.1f}s"
                source["notes"].append(f"{label}: timed out; its facts are unknown")
            except Exception as exc:  # noqa: BLE001 - runner failure must not escape
                entry["error"] = f"runner failed: {type(exc).__name__}"
                source["notes"].append(f"{label}: runner failure; its facts are unknown")
            else:
                entry["exit"] = result.exit
                entry["stdout_bytes"] = len(result.stdout or "")
                raw = _clip(result.stdout, max_output)
                if raw != result.stdout:
                    entry["truncated"] = True
                if result.exit == 0:
                    try:
                        value = json.loads(raw)
                        if not isinstance(value, dict):
                            raise ValueError("output is not a JSON object")
                    except ValueError as exc:
                        entry["error"] = f"malformed output: {exc}"
                        source["notes"].append(f"{label}: output was not a JSON object")
                    else:
                        parsed[label] = value
                        entry["ok"] = True
                else:
                    entry["error"] = f"command exited {result.exit}"
                    stderr = (result.stderr or "").strip()
                    if stderr:
                        entry["stderr"] = _clip(stderr, 500)
        source["commands"].append(entry)

    facts: dict = {}
    if "lynx-status" in parsed:
        state = parsed["lynx-status"]
        issues = state.get("issues")
        if isinstance(issues, list):
            source["issues"] = [str(i) for i in issues[:32]]
        facts, mapping_notes = map_lynx_status(state)
        source["notes"].extend(mapping_notes)

    machine: dict = {}
    for label, mapper in (("cellular", map_cellular),
                          ("agent-queue", map_agent_queue)):
        if label in parsed:
            facts_slice, mapper_notes = mapper(parsed[label])
            machine.update(facts_slice)
            source["notes"].extend(mapper_notes)

    captured = now
    if isinstance(captured, str):
        captured = datetime.fromisoformat(captured.replace("Z", "+00:00"))
    captured = captured or datetime.now(timezone.utc)

    return {
        "schema": SCHEMA,
        "host": "lynx",
        "profile": "lynx",
        "captured_at": captured.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "collector": "lynx_health_collect/2",
        "route": {"ip": ip, "port": port, "transport": "ssh-pinned-key"},
        "source": source,
        "facts": facts,
        # modem MD1 state and agent-queue facts: present only when their
        # read-only commands succeeded; absent means unknown, never ok.
        "machine": {"lynx": machine},
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Collect a read-only Lynx health snapshot over pinned SSH.")
    parser.add_argument("--ip", default=DEFAULT_IP)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--per-cmd-timeout", type=float, default=DEFAULT_PER_CMD_TIMEOUT)
    parser.add_argument("--total-timeout", type=float, default=DEFAULT_TOTAL_TIMEOUT)
    parser.add_argument("--max-output", type=int, default=DEFAULT_MAX_OUTPUT)
    parser.add_argument("--evaluate", action="store_true",
                        help="also run the offline evaluator; exit code = verdict")
    parser.add_argument("--max-age", type=float, default=None, metavar="SECONDS",
                        help="with --evaluate: flag the report stale beyond this age")
    args = parser.parse_args(argv)

    runner = make_ssh_runner(args.ip, args.port)
    snapshot = collect(runner, ip=args.ip, port=args.port,
                       per_cmd_timeout=args.per_cmd_timeout,
                       total_timeout=args.total_timeout,
                       max_output=args.max_output)
    if not args.evaluate:
        print(json.dumps(snapshot, indent=2, sort_keys=True))
        return 0
    try:
        report = evaluate(snapshot, max_age_seconds=args.max_age)
    except ValueError as exc:
        print(f"lynx_health_collect: invalid snapshot: {exc}", file=sys.stderr)
        return 4
    print(json.dumps(report, indent=2, sort_keys=True))
    return {"ok": 0, "warn": 1, "fail": 2, "unknown": 3}[report["verdict"]]


if __name__ == "__main__":
    raise SystemExit(main())
