#!/usr/bin/env python3
"""What is Dushich doing right now, and for whom?  (`dushich-status`)

Read-only and cheap: it scans /proc for Dushich's minds (every non-interactive
`codex --oss ... exec` and every `dushich_summarizer.py`), attributes each to
the agent that asked by walking its parent processes, and asks Ollama whether
it answers and whether Qwen is loaded. It starts nothing and writes nothing.

States, per agent (Aria, Banshee, Gwyn):
  task | answering | reading | exploring | summarizing | working
                  this agent's job is the oldest live Dushich job
  queued #N       this agent's job waits behind N older jobs (Qwen serves one
                  request at a time; order is by process start, an estimate)
  loading         this agent's job is first but Qwen is not in VRAM yet
  needs <agent>   no live job; this agent's last handoff ended blocked < 12 h ago
  idle · busy     nothing for this agent, but other agents keep Dushich busy
  idle            nothing running
  offline         Ollama does not answer on 127.0.0.1:11434

Solo Dushich (the interactive Codex) is not counted: its own quadrant shows it.

    dushich-status                 # one line per agent
    dushich-status --agent gwyn    # one line
    dushich-status --json          # jobs and per-agent states
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.request

NOOBIA = Path(os.environ.get("NOOBIA", "/noobia"))
HOME = Path(os.environ.get("HOME", "/home/aria"))
OLLAMA = "http://127.0.0.1:11434"
MODEL = "qwen3.8:27b"
AGENTS = ("aria", "banshee", "gwyn")
REVIEW_HOURS = 12
RUN = re.compile(r"^\d{8}T\d{6}Z-[0-9a-f]{8}$")
LABELS = {"task": "task", "ask": "answering", "mirror": "reading", "explore": "exploring",
          "summarize": "summarizing", "exec": "working", "other": "busy"}


# -- processes ----------------------------------------------------------------
def read_processes(proc: str = "/proc") -> dict[int, dict]:
    """pid -> {ppid, start (clock ticks since boot), argv} for every readable process."""
    found = {}
    for entry in os.scandir(proc):
        if not entry.name.isdigit():
            continue
        try:
            with open(f"{entry.path}/stat", "rb") as stream:
                stat = stream.read().decode("utf-8", "replace")
            with open(f"{entry.path}/cmdline", "rb") as stream:
                argv = [a.decode("utf-8", "replace") for a in stream.read().split(b"\0") if a]
        except OSError:
            continue
        fields = stat[stat.rfind(")") + 2:].split()  # the command name may hold spaces or ')'
        try:
            found[int(entry.name)] = {"ppid": int(fields[1]), "start": int(fields[19]), "argv": argv}
        except (IndexError, ValueError):
            continue
    return found


def is_mind(argv: list[str]) -> bool:
    """A process that is Dushich thinking on the GPU on someone's behalf."""
    if not argv:
        return False
    if os.path.basename(argv[0]) == "codex" and "--oss" in argv and "exec" in argv:
        return True
    return any(a.endswith("dushich_summarizer.py") for a in argv[:2])


def _agent_flag(argv: list[str]) -> str:
    for i, arg in enumerate(argv[:-1]):
        if arg == "--agent":
            return argv[i + 1].lower()
    return ""


def classify(argv: list[str]) -> tuple[str, str] | None:
    """(agent, kind) when this ancestor tells who asked Dushich and why, else None."""
    joined = " ".join(argv[:3])
    if "bridge.py" in joined and "--agent" in argv:
        return _agent_flag(argv), ("task" if "_worker" in argv else "ask")
    if "aria/dushich-bridge" in joined:
        return "aria", ("task" if "_worker" in argv else "ask")
    if "helper_mirror.py" in joined:
        return "aria", "mirror"
    if "helper_banshee.py" in joined:
        return "banshee", ("mirror" if "watch" in argv or "sync" in argv else "ask")
    if "helper_gwyn.py" in joined:
        return "gwyn", "ask"
    if "dushich_explore.py" in joined:
        return "", "explore"
    if "mcp.py" in joined and "--agent" in argv:
        return _agent_flag(argv), "ask"
    return None


def jobs(procs: dict[int, dict]) -> list[dict]:
    """Live Dushich jobs, oldest first; a mind started inside another mind is the same job."""
    clis = {p["ppid"]: _agent_flag(p["argv"]) for p in procs.values()
            if "mcp.py" in " ".join(p["argv"][:3]) and "--agent" in p["argv"]}
    minds = {pid for pid, p in procs.items() if is_mind(p["argv"])}
    found = []
    for pid in minds:
        agent, kind, nested = "", "other", False
        summarizer = not os.path.basename(procs[pid]["argv"][0]) == "codex"
        cursor, seen = procs[pid]["ppid"], set()
        while cursor > 1 and cursor in procs and cursor not in seen:
            seen.add(cursor)
            if cursor in minds:
                nested = True
                break
            hit = classify(procs[cursor]["argv"])
            if hit:
                agent, kind = hit
                break
            if cursor in clis:  # `dushich exec` straight from an agent's own shell
                agent, kind = clis[cursor], "exec"
                break
            cursor = procs[cursor]["ppid"]
        if nested:
            continue
        if summarizer and kind in ("other", "exec"):
            kind = "summarize"
        found.append({"pid": pid, "agent": agent, "kind": kind, "start": procs[pid]["start"]})
    return sorted(found, key=lambda j: (j["start"], j["pid"]))


# -- Ollama and handoffs ---------------------------------------------------------
_OLLAMA_CACHE: list = [0.0, None]


def ollama_state(timeout: float = 0.5, ttl: float = 15.0) -> dict:
    """{'up': bool, 'loaded': bool} from /api/ps, cached for `ttl` seconds."""
    now = time.monotonic()
    if _OLLAMA_CACHE[1] is not None and now - _OLLAMA_CACHE[0] < ttl:
        return _OLLAMA_CACHE[1]
    try:
        with urllib.request.urlopen(OLLAMA + "/api/ps", timeout=timeout) as reply:
            models = json.loads(reply.read().decode("utf-8")).get("models") or []
        value = {"up": True, "loaded": any((m.get("name") or m.get("model")) == MODEL for m in models)}
    except (OSError, ValueError):
        value = {"up": False, "loaded": False}
    _OLLAMA_CACHE[:] = [now, value]
    return value


def handoff_dirs(agent: str) -> Path:
    if agent == "aria":
        return HOME / ".codex/dushich-bridge"
    return NOOBIA / ("gwyn-app-nub" if agent == "gwyn" else agent) / "private/task-runs"


def blocked_handoff(agent: str, hours: float = REVIEW_HOURS, now: datetime | None = None) -> bool:
    """True when the agent's newest handoff ended as needs_<agent> within `hours`."""
    root = handoff_dirs(agent)
    try:
        runs = sorted(p for p in root.iterdir() if p.is_dir() and RUN.fullmatch(p.name))
    except OSError:
        return False
    if not runs:
        return False
    try:
        state = json.loads((runs[-1] / "state.json").read_text(encoding="utf-8"))
        finished = datetime.fromisoformat(state.get("finished") or "")
    except (OSError, ValueError):
        return False
    now = now or datetime.now(timezone.utc)
    return state.get("status") == f"needs_{agent}" and (now - finished).total_seconds() < hours * 3600


# -- states ---------------------------------------------------------------------------
def agent_state(agent: str, live: list[dict], ollama: dict, blocked: bool) -> dict:
    """One agent's helper state: {'state', 'text', 'level'}; level picks the colour."""
    agent = agent.lower()
    if not ollama["up"]:
        return {"state": "offline", "text": "Dushich: offline", "level": "error"}
    mine = [i for i, j in enumerate(live) if j["agent"] == agent]
    if mine:
        first = mine[0]
        kind = live[first]["kind"]
        if first > 0:
            return {"state": "queued", "text": f"Dushich: queued #{first + 1}", "level": "wait",
                    "kind": kind, "ahead": first}
        if not ollama["loaded"]:
            return {"state": "loading", "text": "Dushich: loading", "level": "wait", "kind": kind}
        return {"state": "working", "text": f"Dushich: {LABELS[kind]}", "level": "busy", "kind": kind}
    if blocked:
        return {"state": "needs_review", "text": f"Dushich: needs {agent.capitalize()}", "level": "wait"}
    if live:
        return {"state": "idle_busy", "text": "Dushich: idle · busy", "level": "idle_busy",
                "others": len(live)}
    return {"state": "idle", "text": "Dushich: idle", "level": "idle"}


def solo_state(live: list[dict], ollama: dict) -> dict:
    """For the Solo quadrant: how busy the helper side of Dushich is."""
    if not ollama["up"]:
        return {"state": "offline", "text": "Helpers: offline", "level": "error"}
    if live:
        return {"state": "working", "text": f"Helpers: {len(live)} job" + ("s" if len(live) > 1 else ""),
                "level": "busy"}
    return {"state": "idle", "text": "Helpers: idle", "level": "idle"}


def snapshot() -> dict:
    live = jobs(read_processes())
    ollama = ollama_state()
    states = {a: agent_state(a, live, ollama, blocked_handoff(a)) for a in AGENTS}
    return {"ollama": ollama, "jobs": live, "agents": states, "solo": solo_state(live, ollama)}


def status_line(agent: str) -> dict:
    """The Forge's entry point: the helper line for one quadrant's agent."""
    live = jobs(read_processes())
    ollama = ollama_state()
    if agent.lower() == "dushich":
        return solo_state(live, ollama)
    return agent_state(agent, live, ollama, blocked_handoff(agent.lower()))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dushich-status", description=__doc__.split("\n")[0])
    parser.add_argument("--agent", choices=AGENTS + ("dushich",))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        value = status_line(args.agent) if args.agent else snapshot()
    except OSError as exc:
        print(f"dushich-status: {exc}")
        return 1
    if args.json:
        print(json.dumps(value))
    elif args.agent:
        print(value["text"])
    else:
        for name, state in value["agents"].items():
            print(f"{name}: {state['text'].split(': ', 1)[1]}")
        print(f"jobs: {len(value['jobs'])}" + "".join(
            f"\n  pid {j['pid']} {j['agent'] or '?'} {j['kind']}" for j in value["jobs"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
