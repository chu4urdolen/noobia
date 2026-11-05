#!/usr/bin/env python3
"""Run one local Codex coding task and verify its observable result."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from uuid import uuid4


WORKSPACE = Path("/noobia/dushich/workspace")
CODEX_HOME = Path("/home/dushich/.codex")
CODEX = Path("/opt/noobia/dushich-codex/node_modules/.bin/codex")
MODEL = "gpt-oss:20b"
os.environ["GIT_DIR"] = str(WORKSPACE / ".dushich-git")
os.environ["GIT_WORK_TREE"] = str(WORKSPACE)


def run(argv: list[str], timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv, cwd=WORKSPACE, capture_output=True, text=True, timeout=timeout, check=False
    )


def git(*args: str) -> str:
    result = run(["git", *args])
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def codex_turn(prompt: str, thread_id: str | None, timeout: int,
               events_path: Path) -> dict:
    args = [str(CODEX), "--oss", "--local-provider", "ollama", "--model", MODEL, "exec"]
    if thread_id:
        args += ["resume", thread_id]
    args += ["--json", prompt]
    offset = events_path.stat().st_size if events_path.exists() else 0
    stderr_path = events_path.with_suffix(".stderr")
    stderr_offset = stderr_path.stat().st_size if stderr_path.exists() else 0
    timed_out = False
    blocked_reason = ""
    with events_path.open("ab") as log, stderr_path.open("ab") as errors:
        os.chmod(events_path, 0o600)
        os.chmod(stderr_path, 0o600)
        process = subprocess.Popen(
            args, cwd=WORKSPACE, stdin=subprocess.DEVNULL,
            stdout=log, stderr=errors, start_new_session=True,
        )
        deadline = time.monotonic() + timeout
        while process.poll() is None:
            try:
                process.wait(timeout=min(1, max(0.1, deadline - time.monotonic())))
            except subprocess.TimeoutExpired:
                pass
            with events_path.open("rb") as progress_log:
                progress_log.seek(offset)
                live = progress_log.read().decode("utf-8", errors="replace")
            syntax_errors = 0
            for line in live.splitlines():
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                item = event.get("item", {})
                if (event.get("type") == "item.completed"
                        and item.get("type") == "command_execution"
                        and item.get("exit_code") != 0):
                    output = item.get("aggregated_output", "")
                    if ("unexpected EOF while looking for matching" in output
                            or "here-document at line 1 delimited by end-of-file" in output):
                        syntax_errors += 1
            if syntax_errors >= 4:
                blocked_reason = "Stopped after four repeated shell quoting failures"
            if not blocked_reason and time.monotonic() >= deadline:
                timed_out = True
            if blocked_reason or timed_out:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait()
                break

    with events_path.open("rb") as log:
        log.seek(offset)
        stdout = log.read().decode("utf-8", errors="replace")
    with stderr_path.open("rb") as errors:
        errors.seek(stderr_offset)
        stderr = errors.read().decode("utf-8", errors="replace")

    events = []
    for line in stdout.splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    new_thread = next(
        (event.get("thread_id") for event in events if event.get("type") == "thread.started"),
        None,
    )
    tools = [
        event["item"]
        for event in events
        if event.get("type") == "item.completed"
        and event.get("item", {}).get("type") in {"command_execution", "file_change"}
    ]
    final = [
        event["item"].get("text", "")
        for event in events
        if event.get("type") == "item.completed"
        and event.get("item", {}).get("type") == "agent_message"
    ]
    result = {
        "thread_id": new_thread or thread_id,
        "completed": not timed_out and not blocked_reason and any(
            event.get("type") == "turn.completed" for event in events),
        "timed_out": timed_out,
        "blocked_reason": blocked_reason,
        "exit_code": process.returncode,
        "tool_calls": len(tools),
        "successful_tools": sum(
            item.get("exit_code", 0) == 0 and item.get("status") != "failed"
            for item in tools
        ),
        "final_message": final[-1] if final else "",
        "stderr": stderr.strip(),
    }
    return result


def verify(
    expected_paths: list[Path], tests: list[str], old_head: str,
    old_hashes: dict[str, str | None], require_commit: bool,
) -> dict:
    missing = [str(path.relative_to(WORKSPACE)) for path in expected_paths if not path.is_file()]
    new_hashes = {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        for path in expected_paths
    }
    expected_changed = any(new_hashes[key] != old_hashes[key] for key in new_hashes)
    head = git("rev-parse", "HEAD")
    status = git("status", "--porcelain")
    changed = head != old_head or bool(status)
    committed = head != old_head and not status
    test_results = []
    for test_command in tests:
        result = run(
            [
                str(CODEX), "sandbox", "-P", "dushich-workspace", "-C", str(WORKSPACE),
                "/bin/bash", "-c", test_command,
            ],
            timeout=120,
        )
        output = result.stdout + result.stderr
        test_results.append({
            "command": test_command,
            "exit_code": result.returncode,
            "stdout": result.stdout[-6000:],
            "stderr": result.stderr[-6000:],
            "zero_tests": bool(re.search(r"\bRan 0 tests\b", output)),
        })
    return {
        "missing": missing,
        "changed": changed,
        "committed": committed,
        "expected_changed": expected_changed,
        "head": head,
        "git_status": status,
        "tests": test_results,
        "passed": not missing and changed and expected_changed and (
            not require_commit or committed
        ) and all(
            test["exit_code"] == 0 and not test["zero_tests"] for test in test_results
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Delegate a bounded local coding task to Dushich, with verification."
    )
    parser.add_argument("--expect", action="append", default=[], metavar="PATH")
    parser.add_argument("--test", action="append", default=[], metavar="COMMAND",
                        help="Test command in Codex sandbox; may be repeated")
    parser.add_argument("--timeout", type=int, default=120, metavar="SECONDS")
    parser.add_argument("--attempts", type=int, default=2, choices=(1, 2))
    parser.add_argument("--require-commit", action="store_true",
                        help="Require a new commit and a clean Git tree")
    parser.add_argument("--thread-id", help="Resume an existing Dushich Codex thread")
    parser.add_argument("--run-id", help="Bridge handoff ID for live event monitoring")
    parser.add_argument("prompt", help="Coding task for Dushich")
    args = parser.parse_args()

    if not args.expect and not args.test:
        parser.error("provide --expect PATH or --test COMMAND for independent verification")
    if args.timeout < 10 or args.timeout > 600:
        parser.error("--timeout must be between 10 and 600 seconds")
    if not WORKSPACE.is_dir() or not CODEX.is_file():
        parser.error("Dushich workspace or Codex CLI is missing")

    expected_paths = []
    for raw in args.expect:
        path = (WORKSPACE / raw).resolve()
        if not path.is_relative_to(WORKSPACE) or path == WORKSPACE:
            parser.error(f"expected path must be inside workspace: {raw}")
        expected_paths.append(path)
    old_hashes = {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        for path in expected_paths
    }

    try:
        if git("status", "--porcelain"):
            parser.error("workspace Git tree must be clean before a delegated task")
        old_head = git("rev-parse", "HEAD")
    except RuntimeError as exc:
        parser.error(str(exc))

    if args.run_id and not re.fullmatch(r"\d{8}T\d{6}Z-[0-9a-f]{8}", args.run_id):
        parser.error("invalid --run-id")
    run_id = args.run_id or (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                             + "-" + uuid4().hex[:8])
    log_dir = CODEX_HOME / "task-runs"
    log_dir.mkdir(mode=0o700, exist_ok=True)
    os.chmod(log_dir, 0o700)
    events_path = log_dir / f"{run_id}.jsonl"
    report_path = log_dir / f"{run_id}.json"
    if events_path.exists() or report_path.exists():
        parser.error("task run ID already exists")
    thread_id = args.thread_id
    attempts = []
    prompt = (
        "Use tools to make the requested changes in your workspace. Run tests and "
        "verify files before claiming success. Do not commit until tests pass. "
        + ("Make a Git commit after tests pass. " if args.require_commit else "")
        + "Expected files: " + ", ".join(args.expect) + ". "
        + "Independent test commands: " + "; ".join(args.test) + ". "
        + "Task: " + args.prompt
    )
    for attempt_number in range(1, args.attempts + 1):
        turn = codex_turn(prompt, thread_id, args.timeout, events_path)
        thread_id = turn.get("thread_id")
        try:
            check = verify(expected_paths, args.test, old_head, old_hashes,
                           args.require_commit)
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            check = {"passed": False, "error": str(exc)}
        attempts.append({"turn": turn, "verification": check})
        if turn.get("blocked_reason"):
            break
        if (
            turn.get("completed")
            and turn.get("exit_code") == 0
            and turn.get("successful_tools", 0) > 0
            and check.get("passed")
        ):
            break
        failure = []
        if not turn.get("completed") or turn.get("exit_code"):
            failure.append("Your Codex turn did not complete successfully.")
        if not turn.get("successful_tools"):
            failure.append("No successful file or terminal tool call was observed.")
        if check.get("missing"):
            failure.append("Missing files: " + ", ".join(check["missing"]))
        for test in check.get("tests", []):
            if test["exit_code"] or test["zero_tests"]:
                failure.append(
                    "Verification command failed or found zero tests: " + test["command"]
                    + "\n" + (test["stdout"] + test["stderr"])[-1500:]
                )
        if not check.get("changed"):
            failure.append("Git shows no actual change or new commit.")
        if not check.get("expected_changed"):
            failure.append("No expected file changed. Edit the specified files, not another test tree.")
        if args.require_commit and not check.get("committed"):
            failure.append("A new commit and clean Git tree are required after tests pass.")
        if check.get("error"):
            failure.append("Verification error: " + check["error"])
        prompt = (
            "Continue the same task. Independent verification found unfinished work: "
            + " ".join(failure)
            + " Use terminal or edit tools to correct it, run tests, and verify actual files. "
            "Do not describe work you have not performed."
        )

    passed = bool(attempts and attempts[-1]["verification"].get("passed") and
                  attempts[-1]["turn"].get("completed") and
                  not attempts[-1]["turn"].get("blocked_reason") and
                  attempts[-1]["turn"].get("exit_code") == 0 and
                  attempts[-1]["turn"].get("successful_tools", 0))
    report = {
        "run_id": run_id,
        "passed": passed,
        "model": MODEL,
        "require_commit": args.require_commit,
        "workspace": str(WORKSPACE),
        "events_path": str(events_path),
        "attempts": attempts,
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    os.chmod(report_path, 0o600)
    final = attempts[-1]["verification"]
    print(f"Dushich task: {'PASS' if passed else 'FAIL'}")
    print(f"Attempts: {len(attempts)} | tools: {sum(x['turn'].get('tool_calls', 0) for x in attempts)}")
    if attempts[-1]["turn"].get("blocked_reason"):
        print("Blocker: " + attempts[-1]["turn"]["blocked_reason"])
    print(f"Git HEAD: {final.get('head', 'unknown')[:12]}")
    if final.get("git_status"):
        print("Git status:\n" + final["git_status"])
    else:
        print("Git status: clean")
    if final.get("missing"):
        print("Missing: " + ", ".join(final["missing"]))
    for test in final.get("tests", []):
        print("Verification test: " + test["command"])
        print((test["stdout"] + test["stderr"]).strip()[-3000:])
        print(f"Test exit: {test['exit_code']}")
    print(f"Report: {report_path}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
