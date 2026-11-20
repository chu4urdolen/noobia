#!/usr/bin/env python3
"""Ask local Dushich to find things on Nexus, remembering them in forge.db.

Dushich first checks the path atlas (`forge-db search`), explores only if it
does not already know, records what he finds with `forge-db path set`, and
answers briefly. He runs on the local GPU, so exploring costs no cloud tokens.
Dushich is not sandboxed: the brief asks for read-only exploration, and the
result lists every atlas row he wrote so the asker can check it.

    dushich-explore start "Where does Lynx handle Bluetooth auth?" --by Gwyn
    dushich-explore wait ID          # up to --timeout seconds, then "running"
    dushich-explore ask "..." --by Aria --timeout 600   # start + wait
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from uuid import uuid4

HOME = os.path.expanduser("~")

ROOT = Path(HOME + "/.codex/dushich-bridge/explore")
NOOBIA = Path(os.environ.get("NOOBIA", "/noobia"))
FORGE_DB = str(NOOBIA / "common/tools/forge-db")
DUSHICH = str(NOOBIA / "dushich/coding/dushich-launcher")
JOB = re.compile(r"^\d{8}T\d{6}Z-[0-9a-f]{8}$")
WORK_TIMEOUT = 1200

BRIEF = """You are Dushich the Explorer, helping {asker} find things on Nexus.

Question from {asker}:
{question}

How to work:
1. First run `forge-db search <a few keywords>` (and `forge-db project list` if
   the question is about a project). The atlas may already know the answer,
   but a recorded path can be stale or wrong: check each one you rely on
   briefly (ls -ld, head) and, if it is right, count it with
   `forge-db path hit PATH --by Dushich`. Fix or remove a wrong row.
2. Only if it does not, explore /noobia (or the rest of Nexus if needed) with
   read-only commands such as rg, ls, find, head, and sed -n. Do not create,
   edit, move, or delete any file, and do not start or stop services. The only
   thing you write is the atlas, through forge-db.
3. Record each important path you discover or confirm, and fix any recorded
   description you find wrong:
   forge-db path set PATH -k KIND -o OWNER -d "what it is, one line" -t "tags" --by Dushich
   KIND is one of: dir file tool service db config doc device log link other.
   Add --project NAME when the path belongs to a project from `forge-db project list`,
   and --tag NAME for fitting tags from `forge-db tag list` (repeatable).
   Record directories and key entry files, not every file.
4. Finish with a short answer (under 1500 characters): the answer first, then
   the key paths, one line each. Say plainly if you could not find it."""


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def job_dir(job_id: str) -> Path:
    if not JOB.fullmatch(job_id):
        raise ValueError("Invalid explore job ID")
    path = ROOT / job_id
    if not (path / "state.json").is_file():
        raise ValueError(f"Unknown explore job: {job_id}")
    return path


def read_state(job_id: str) -> dict:
    return json.loads((job_dir(job_id) / "state.json").read_text())


def save_state(path: Path, state: dict) -> None:
    temporary = path / "state.tmp"
    temporary.write_text(json.dumps(state, indent=1) + "\n")
    os.chmod(temporary, 0o600)
    temporary.replace(path / "state.json")


def start(question: str, asker: str) -> str:
    if not question.strip() or len(question) > 4000:
        raise ValueError("Ask a question of up to 4000 characters")
    if not re.fullmatch(r"[A-Za-z][\w -]{0,40}", asker or ""):
        raise ValueError("--by must be your Noob name")
    job_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = ROOT / job_id
    path.mkdir(mode=0o700)
    save_state(path, {"id": job_id, "asker": asker, "question": question.strip(),
                      "status": "queued", "created": stamp()})
    subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "_worker", job_id],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True)
    return job_id


def worker(job_id: str) -> None:
    path = job_dir(job_id)
    state = read_state(job_id)
    state.update(status="running", started=stamp())
    save_state(path, state)
    prompt = BRIEF.format(asker=state["asker"], question=state["question"])
    try:
        process = subprocess.run([DUSHICH, "exec", "--json", "-"], input=prompt,
                                 capture_output=True, text=True, timeout=WORK_TIMEOUT, check=False)
        (path / "events.jsonl").write_text(process.stdout)
        events = []
        for line in process.stdout.splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        replies = [e["item"].get("text", "").strip() for e in events
                   if e.get("type") == "item.completed" and (e.get("item") or {}).get("type") == "agent_message"]
        commands = sum(1 for e in events if e.get("type") == "item.completed"
                       and (e.get("item") or {}).get("type") == "command_execution")
        answer = replies[-1] if replies and replies[-1] else ""
        state.update(status="done" if answer else "failed", answer=answer, commands=commands,
                     exit_code=process.returncode, error=process.stderr.strip()[-800:] if not answer else "")
    except subprocess.TimeoutExpired:
        state.update(status="failed", error=f"Dushich did not finish within {WORK_TIMEOUT} s")
    except OSError as exc:
        state.update(status="failed", error=str(exc))
    changes = subprocess.run([FORGE_DB, "--json", "changes", "--since", state["started"]],
                             capture_output=True, text=True, timeout=120, check=False)
    try:
        written = json.loads(changes.stdout)
        state["recorded"] = [row["path"] for row in written["paths"] if row["updated_by"] == "Dushich"]
    except (json.JSONDecodeError, KeyError):
        state["recorded"] = []
    state["finished"] = stamp()
    save_state(path, state)


def report(state: dict) -> str:
    if state["status"] in ("queued", "running"):
        return f"Explore job {state['id']}: {state['status']} (since {state.get('started', state['created'])})"
    lines = [f"Explore job {state['id']}: {state['status']}"
             + (f", {state.get('commands', 0)} commands" if state["status"] == "done" else "")]
    lines.append(state.get("answer") or state.get("error") or "No answer.")
    if state.get("recorded"):
        lines.append(f"Atlas rows written by Dushich ({len(state['recorded'])}): " + ", ".join(state["recorded"]))
    return "\n".join(lines)


def wait(job_id: str, timeout: int) -> dict:
    deadline = time.monotonic() + max(0, timeout)
    while True:
        state = read_state(job_id)
        if state["status"] not in ("queued", "running") or time.monotonic() >= deadline:
            return state
        time.sleep(2)


def main() -> int:
    parser = argparse.ArgumentParser(prog="dushich-explore", description=__doc__.split("\n")[0])
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("start", "ask"):
        command = sub.add_parser(name)
        command.add_argument("question")
        command.add_argument("--by", required=True, help="your Noob name")
        if name == "ask":
            command.add_argument("--timeout", type=int, default=300)
    w = sub.add_parser("wait")
    w.add_argument("id")
    w.add_argument("--timeout", type=int, default=60)
    sub.add_parser("status").add_argument("id")
    sub.add_parser("_worker").add_argument("id")
    args = parser.parse_args()
    try:
        if args.cmd == "_worker":
            worker(args.id)
            return 0
        if args.cmd == "start":
            job_id = start(args.question, args.by)
            print(json.dumps({"id": job_id}) if args.json else
                  f"Explore job {job_id} started; check with: dushich-explore wait {job_id}")
            return 0
        if args.cmd == "ask":
            state = wait(start(args.question, args.by), args.timeout)
        elif args.cmd == "wait":
            state = wait(args.id, args.timeout)
        else:
            state = read_state(args.id)
    except (OSError, ValueError) as exc:
        print(f"dushich-explore: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(state) if args.json else report(state))
    return 1 if state["status"] == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())
