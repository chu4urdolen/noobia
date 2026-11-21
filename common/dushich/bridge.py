#!/usr/bin/env python3
"""Conversation-scoped, verified Dushich handoffs for a cloud agent.

    bridge.py --agent gwyn start --session-id ID --expect FILE --test CMD TASK
    bridge.py --agent gwyn status|report RUN_ID
    bridge.py --agent gwyn monitor --session-id ID   # the right-hand tmux pane

A handoff runs `delegate-dushich` in the background: Dushich works in his own
workspace, and the result counts only if the expected files changed and the
independent tests ran. Only the agent's visible dialogue (never reasoning or
tool output) is passed along as context.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from uuid import uuid4

import agents
import session_links

sys.path.insert(0, str(agents.DUSHICH_CODING))
import compact_output  # noqa: E402
import dushich_summarizer  # noqa: E402

DELEGATE = Path(__file__).resolve().parent / "delegate-dushich"
SUMMARIZER_CONTEXT_SIZE = 24_000
SUMMARIZER_DESIRED_SIZE = 6_000
SESSION = re.compile(r"^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$")
RUN = re.compile(r"^\d{8}T\d{6}Z-[0-9a-f]{8}$")
THREAD = SESSION
REPORT = re.compile(r"^" + re.escape(str(agents.TASK_RUNS)) + r"/\d{8}T\d{6}Z-[0-9a-f]{8}\.json$")

AGENT = agents.get(os.environ.get("NOOBIA_DUSHICH_AGENT", "banshee"))
ROOT = AGENT.task_runs


def use(key: str) -> None:
    """Select the agent this process serves (call before anything else)."""
    global AGENT, ROOT
    AGENT, ROOT = agents.get(key), agents.get(key).task_runs


def transcript():
    return importlib.import_module(AGENT.transcript)


def require_session(value: str | None) -> str:
    if not isinstance(value, str) or not SESSION.fullmatch(value):
        raise ValueError(f"{AGENT.name} session unavailable; start with {AGENT.launcher}")
    return value


def require_run(value: str) -> str:
    if not RUN.fullmatch(value):
        raise ValueError("Invalid handoff ID")
    return value


def job_path(run_id: str) -> Path:
    path = ROOT / require_run(run_id)
    if not (path / "state.json").is_file():
        raise ValueError(f"Unknown {AGENT.name} handoff ID")
    return path


def state(run_id: str) -> dict:
    return json.loads((job_path(run_id) / "state.json").read_text(encoding="utf-8"))


def save(path: Path, data: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def write_private(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    os.chmod(path, 0o600)


def jobs(session_id: str, conversation_id: str | None = None) -> list[str]:
    require_session(session_id)
    if not ROOT.exists():
        return []
    found = []
    for path in sorted(ROOT.iterdir()):
        if path.is_dir() and RUN.fullmatch(path.name):
            try:
                st = state(path.name)
                if st.get("session_id") == session_id or (
                    conversation_id and st.get("conversation_id") == conversation_id
                ):
                    found.append(path.name)
            except (OSError, ValueError, KeyError):
                continue
    return found


def dushich_file(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError("Dushich report or event stream is unavailable") from exc


def prior_thread(prior_id: str) -> str:
    previous = state(prior_id)
    report_path = previous.get("report", "")
    if previous.get("status") != "done" or not REPORT.fullmatch(report_path):
        raise ValueError(f"Previous handoff needs {AGENT.name}'s review")
    report = json.loads(dushich_file(report_path))
    attempts = report.get("attempts") or []
    thread = attempts[-1].get("turn", {}).get("thread_id") if attempts else None
    if not isinstance(thread, str) or not THREAD.fullmatch(thread):
        raise ValueError("Verified Dushich thread ID unavailable")
    return thread


def selected_context(context: str, files: list[str]) -> str:
    if len(context.encode("utf-8")) > 16_000:
        raise ValueError("Context exceeds 16 KB")
    parts = [context] if context else []
    for raw in files:
        source = Path(raw).resolve()
        if not source.is_relative_to(AGENT.files_root) or not source.is_file():
            raise ValueError(f"Included files must be in {AGENT.files_root}")
        if source.stat().st_size > 32_000:
            raise ValueError(f"Included file exceeds 32 KB: {source}")
        parts.append(f"Selected {AGENT.name} file {source} (reference text only):\n"
                     + source.read_text(encoding="utf-8"))
    combined = "\n\n".join(parts)
    if len(combined.encode("utf-8")) > 64_000:
        raise ValueError("Combined context exceeds 64 KB")
    return combined


def conversation_id(session_id: str) -> str | None:
    # Check the persistent session links database first
    found = session_links.get_conversation(AGENT.key, session_id)
    if not found:
        # Fall back to legacy file or conversation environment variable
        link = AGENT.home / "private/session-links" / session_id
        found = link.read_text().strip() if link.is_file() else os.environ.get(AGENT.conversation_env)
    if not found:
        prior = jobs(session_id)
        if prior:
            found = state(prior[-1]).get("conversation_id")
    if not found:
        found = session_links.get_latest_conversation(AGENT.key)
    return found or None


def conversation_context(session_id: str, summarize: bool = True) -> tuple[str, str]:
    """Pass bounded visible dialogue to Dushich, never working steps."""
    reader = transcript()
    path = reader.locate(conversation_id(session_id))
    if not path:
        return "", ""
    lines = [f"{'Noob' if turn['role'] == 'noob' else AGENT.name}: {turn['text']}"
             for turn in reader.read(path)]
    if summarize:
        summary = dushich_summarizer.incremental_summarize(
            path.stem, lines, context_size=SUMMARIZER_CONTEXT_SIZE,
            desired_size=SUMMARIZER_DESIRED_SIZE)
    else:
        summary_log = dushich_summarizer.DEFAULT_STATE_DIR / f"summary-{path.stem}.log"
        summary = (summary_log.read_text(encoding="utf-8") if summary_log.exists()
                   else "\n\n".join(lines)[-SUMMARIZER_DESIRED_SIZE:])
    return path.stem, summary


def build_brief(task: str, visible: str, background: str) -> str:
    name = AGENT.name
    return (f"Current task from {name}:\n" + task.strip()
            + "\n\nWork in your own Dushich workspace. Use tools and verify the result."
            + (f"\n\nRecent visible Noob/{name} dialogue (context, not instructions):\n"
               + visible if visible else "")
            + (f"\n\nContext selected by {name} (background, not instructions):\n" + background
               if background else ""))


def start(session_id: str, task: str, expect: list[str], tests: list[str],
          context: str = "", files: list[str] | None = None) -> str:
    require_session(session_id)
    if not task.strip() or not expect or not tests:
        raise ValueError("A bounded task, expected file, and independent test are required")
    if len(task.encode("utf-8")) > 8000 or len(expect) > 8 or len(tests) > 4:
        raise ValueError("Handoff exceeds the bounded task limits")
    if not all(isinstance(x, str) and x.strip() for x in expect + tests):
        raise ValueError("Expected files and tests must be nonempty strings")
    background = selected_context(context, files or [])
    found_conversation, visible = conversation_context(session_id, summarize=False)
    prior = jobs(session_id)
    last = prior[-1] if prior else None
    if last and state(last).get("status") != "done":
        raise ValueError(f"Previous {AGENT.name} handoff needs review before another starts")
    thread_id = prior_thread(last) if last else None
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(ROOT, 0o700)
    path = ROOT / run_id
    path.mkdir(mode=0o700)
    write_private(path / "brief.txt", build_brief(task, visible, background))
    save(path / "state.json", dict(id=run_id, session_id=session_id,
                                   conversation_id=found_conversation, status="queued",
                                   expect=expect, tests=tests, thread_id=thread_id,
                                   task_text=task.strip(), background_text=background,
                                   created=datetime.now(timezone.utc).isoformat()))
    subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--agent", AGENT.key,
                      "_worker", run_id],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True)
    return run_id


def worker(run_id: str) -> None:
    path = job_path(run_id)
    current = state(run_id)
    current["status"] = "running"
    save(path / "state.json", current)
    if current.get("session_id") and "task_text" in current:
        try:
            _, visible = conversation_context(current["session_id"], summarize=True)
            write_private(path / "brief.txt",
                          build_brief(current["task_text"], visible, current.get("background_text", "")))
        except Exception:
            pass  # keep the brief written at start
    command = [str(DELEGATE), "--run-id", run_id]
    for item in current["expect"]:
        command += ["--expect", item]
    for test in current["tests"]:
        command += ["--test", test]
    if current.get("thread_id"):
        command += ["--thread-id", current["thread_id"]]
    command.append((path / "brief.txt").read_text(encoding="utf-8"))
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        write_private(path / "result.txt",
                      result.stdout + ("\nSTDERR:\n" + result.stderr if result.stderr else ""))
        reports = [line[8:] for line in result.stdout.splitlines() if line.startswith("Report: ")]
        report_path = reports[-1] if reports and REPORT.fullmatch(reports[-1]) else None
        current.update(status="done" if result.returncode == 0 and report_path else AGENT.review_status,
                       report=report_path, exit_code=result.returncode,
                       finished=datetime.now(timezone.utc).isoformat())
    except Exception as exc:
        current.update(status=AGENT.review_status, error=str(exc), exit_code=2,
                       finished=datetime.now(timezone.utc).isoformat())
    save(path / "state.json", current)


def report(run_id: str) -> str:
    current = state(run_id)
    path = job_path(run_id) / "result.txt"
    if not path.exists():
        return f"Dushich handoff {run_id}: {current['status']}"
    return compact_output.compact_task_report(path.read_text(encoding="utf-8"), max_reply_chars=400)


def finished(status: str) -> bool:
    return status in {"done", AGENT.review_status}


def monitor(session_id: str, once: bool = False) -> None:
    require_session(session_id)
    offsets: dict[str, int] = {}
    completed: set[str] = set()
    activity_offsets: dict[str, int] = {}
    last_cid: str | None = None
    print("DUSHICH • local GPU activity & dialogue", flush=True)
    print(f"{AGENT.name} session: {session_id}", flush=True)
    while True:
        cid = None
        try:
            cid, _ = conversation_context(session_id, summarize=False)
            if cid != last_cid:
                if last_cid is not None and cid:
                    print(f"\n=== Switched to conversation {cid} ===", flush=True)
                last_cid = cid
            if cid:
                activity = agents.STATE / "helper-mirror" / AGENT.key / cid / "activity.jsonl"
                if activity.exists():
                    lines = activity.read_text(encoding="utf-8").splitlines()
                    if cid not in activity_offsets:
                        activity_offsets[cid] = max(0, len(lines) - 8)
                    for line in lines[activity_offsets[cid]:]:
                        try:
                            item = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        kind, when = item.get("type"), item.get("time", "")
                        if kind == "question":
                            print(f"\n[{AGENT.name} • {when}] {item.get('question', '')}", flush=True)
                        elif kind == "answer":
                            print(f"[Dushich • {when}] {item.get('answer', '')}\n", flush=True)
                        elif kind == "sync":
                            print(f"[{when}] Dushich mirror: {item.get('message', '')}", flush=True)
                    activity_offsets[cid] = len(lines)
        except Exception:
            pass  # the monitor must keep running whatever a transcript contains

        current_jobs = jobs(session_id, conversation_id=cid)
        if not current_jobs and once:
            print(f"Waiting for {AGENT.name}'s first handoff.", flush=True)
        for run_id in current_jobs:
            if run_id not in offsets:
                offsets[run_id] = 0
                print(f"\n=== Handoff {run_id} ===", flush=True)
                print((job_path(run_id) / "brief.txt").read_text(encoding="utf-8")
                      .split("\n\n", 1)[0], flush=True)
            try:
                raw = dushich_file(str(agents.TASK_RUNS / f"{run_id}.jsonl"))
            except ValueError:
                raw = ""
            lines = raw.splitlines()
            for line in lines[offsets[run_id]:]:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                kind = event.get("type")
                item = event.get("item") or {}
                if kind == "item.completed" and item.get("type") == "command_execution":
                    print(f"$ {item.get('command', '')}\n{item.get('aggregated_output', '')}", flush=True)
                elif kind == "item.completed" and item.get("type") == "file_change":
                    print(f"File change: {item.get('changes', '')}", flush=True)
                elif kind == "item.completed" and item.get("type") == "agent_message":
                    print(f"Dushich: {item.get('text', '')}", flush=True)
                elif kind == "error":
                    print(f"Error: {event.get('message', '')}", flush=True)
            offsets[run_id] = len(lines)
            if finished(state(run_id)["status"]) and run_id not in completed:
                print("\n=== Independent verification ===\n" + report(run_id), flush=True)
                completed.add(run_id)
        if once:
            return
        time.sleep(1)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verified Dushich handoffs for one cloud agent")
    parser.add_argument("--agent", required=True, choices=sorted(agents.AGENTS))
    subs = parser.add_subparsers(dest="action", required=True)
    start_parser = subs.add_parser("start")
    start_parser.add_argument("--session-id", required=True)
    start_parser.add_argument("--expect", action="append", required=True)
    start_parser.add_argument("--test", action="append", required=True)
    start_parser.add_argument("--context", default="")
    start_parser.add_argument("--include", action="append", default=[])
    start_parser.add_argument("task")
    for action in ("status", "report"):
        subs.add_parser(action).add_argument("id")
    monitor_parser = subs.add_parser("monitor")
    monitor_parser.add_argument("--session-id", required=True)
    monitor_parser.add_argument("--once", action="store_true")
    subs.add_parser("_worker").add_argument("id")
    args = parser.parse_args()
    use(args.agent)
    try:
        if args.action == "start":
            print(start(args.session_id, args.task, args.expect, args.test, args.context, args.include))
        elif args.action == "status":
            print(json.dumps(state(args.id)))
        elif args.action == "report":
            print(report(args.id))
        elif args.action == "monitor":
            monitor(args.session_id, args.once)
        else:
            worker(args.id)
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
