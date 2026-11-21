#!/usr/bin/env python3
"""Consolidated Lynx offline test-suite runner (Round 6, item D20).

Discovers every ``test_*.py`` in ``lynx/tools`` (top level and in each
tool subdirectory), executes each suite in an isolated subprocess, then
runs a ``git diff --check``-equivalent whitespace sanity scan over all
tracked files under ``lynx/`` (trailing whitespace, missing EOF newline,
conflict markers; binary files skipped).

Result classification (documented in
LYNX-CONSOLIDATED-SUITE-20261121.md):

* ``ok``           -- unittest suite ran and passed.
* ``script-ok``    -- file collects zero unittest tests (a standalone
                      offline test script); it is re-run directly as
                      ``python3 <file>`` and its exit code decides.
* ``failed``       -- tests ran and at least one failed or errored.
* ``script-failed``-- standalone script exited nonzero.
* ``env-blocked``  -- the suite could not even be imported because a
                      system dependency is missing (e.g. a Python module
                      or a binary). The suite did not run; it is reported
                      with the missing dependency name.

Exit contract: exit 0 when every suite is ``ok``/``script-ok``, the
whitespace scan is clean, and no test failed. ``env-blocked`` suites are
always reported but do not affect the exit code by default; pass
``--strict`` (intended for fully provisioned hosts, e.g. clean-clone
verification) to make them fail the run.

Strictly offline: no network, no SSH, no device contact, no writes.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_TIMEOUT = 300
MAX_SCAN_BYTES = 10 * 1024 * 1024  # 10 MiB per scanned file
SKIP_DIRS = {"__pycache__", ".git"}
PATCH_EXEMPT_SUFFIXES = (".patch", ".diff")
FAILED_STATUSES = ("failed", "script-failed")

# Binaries that some suites invoke (V53 RAM gates, usb mtu3 preflight)
# but which Ubuntu ships outside a minimal PATH (/usr/sbin).
REQUIRED_BINARIES = ("modinfo",)
STANDARD_BIN_DIRS = ("/usr/sbin", "/usr/local/sbin", "/sbin")

_RAN_RE = re.compile(r"Ran (\d+) test")
_IMPORT_FAIL_RE = re.compile(r"Failed to import test module")
_NO_TESTS_RE = re.compile(r"NO TESTS RAN")
_MISSING_MODULE_RE = re.compile(r"No module named ['\"]([A-Za-z0-9_]+)")
_MISSING_FILE_RE = re.compile(r"No such file or directory: '([^']+)'")


@dataclass
class SuiteResult:
    suite: str
    path: str
    tests: int = 0
    ok: bool = False
    status: str = ""  # ok | script-ok | failed | script-failed | env-blocked
    missing: str = ""  # env-blocked only: e.g. "python:dbus_next"
    duration: float = 0.0
    detail: str = ""


@dataclass
class WhitespaceViolation:
    path: str
    line: int
    kind: str


def tools_root(script: Optional[Path] = None) -> Path:
    """Return the lynx/tools directory this runner lives in."""
    base = script if script is not None else Path(__file__).resolve()
    return base.parent


def discover_test_files(root: Path) -> List[Path]:
    """Find all test_*.py in root (top level) and its immediate subdirectories."""
    found: List[Path] = []
    for p in sorted(root.glob("test_*.py")):
        if p.is_file():
            found.append(p)
    for d in sorted(root.iterdir()):
        if not d.is_dir() or d.name in SKIP_DIRS or d.name.startswith("."):
            continue
        for p in sorted(d.glob("test_*.py")):
            if p.is_file():
                found.append(p)
    return found


def build_child_env() -> Dict[str, str]:
    """Environment for child test processes.

    Some suites invoke ``modinfo`` (kmod), which Ubuntu places in
    ``/usr/sbin``. Login shells have that on PATH; constrained exec
    contexts may not. Prepend the standard system directory that actually
    holds a missing required binary -- only when it is not already
    resolvable -- and otherwise pass the environment through untouched.
    """
    env = dict(os.environ)
    path_dirs = [d for d in env.get("PATH", "").split(":") if d]
    for binary in REQUIRED_BINARIES:
        if shutil.which(binary, path=":".join(path_dirs)):
            continue
        for d in STANDARD_BIN_DIRS:
            if (Path(d) / binary).is_file():
                if d not in path_dirs:
                    path_dirs.insert(0, d)
                break
    env["PATH"] = ":".join(path_dirs)
    return env


def _tail(stderr: str, lines: int = 3) -> str:
    out = (stderr.strip().splitlines() or [""])[-lines:]
    return " ".join(t.strip() for t in out if t.strip())[:300]


def run_script_fallback(test_file: Path, timeout: int,
                        started: float, env: Dict[str, str]) -> SuiteResult:
    """Run a no-unittest test file directly as a standalone script."""
    module = test_file.stem
    try:
        res = subprocess.run(
            [sys.executable, test_file.name],
            cwd=str(test_file.parent), capture_output=True, text=True,
            timeout=timeout, env=env,
        )
    except subprocess.TimeoutExpired:
        return SuiteResult(
            suite=module, path=str(test_file), ok=False, status="script-failed",
            duration=time.monotonic() - started,
            detail=f"standalone script TIMEOUT after {timeout}s",
        )
    duration = time.monotonic() - started
    if res.returncode == 0:
        out_tail = (res.stdout or "").strip().splitlines()
        note = out_tail[-1][:200] if out_tail else "exit 0"
        return SuiteResult(
            suite=module, path=str(test_file), ok=True, status="script-ok",
            duration=duration, detail=f"standalone script, {note}",
        )
    err_tail = _tail(res.stderr, 3)
    return SuiteResult(
        suite=module, path=str(test_file), ok=False, status="script-failed",
        duration=duration,
        detail=f"standalone script, exit {res.returncode}"
               + (f" | {err_tail}" if err_tail else ""),
    )


def _env_blocked_detail(stderr: str) -> str:
    """Name the missing dependency from a unittest collection failure."""
    m = _MISSING_MODULE_RE.search(stderr)
    if m:
        return f"missing python module: {m.group(1)}"
    m = _MISSING_FILE_RE.search(stderr)
    if m:
        return f"missing binary: {m.group(1)}"
    return "import failed (see detail)"


def run_suite(test_file: Path, timeout: int = DEFAULT_TIMEOUT) -> SuiteResult:
    """Run one test file in an isolated subprocess and classify the result."""
    env = build_child_env()
    module = test_file.stem
    started = time.monotonic()
    try:
        res = subprocess.run(
            [sys.executable, "-m", "unittest", module],
            cwd=str(test_file.parent), capture_output=True, text=True,
            timeout=timeout, env=env,
        )
    except subprocess.TimeoutExpired:
        return SuiteResult(
            suite=module, path=str(test_file), ok=False, status="failed",
            duration=time.monotonic() - started,
            detail=f"TIMEOUT after {timeout}s",
        )
    duration = time.monotonic() - started
    stderr = res.stderr or ""
    if res.returncode == 0:
        m = _RAN_RE.search(stderr)
        tests = int(m.group(1)) if m else 0
        return SuiteResult(
            suite=module, path=str(test_file), tests=tests, ok=True,
            status="ok", duration=duration, detail=_tail(stderr),
        )
    # Import/collection crashed before any test could run. Two observed
    # signatures: the loader's "Failed to import test module" report
    # (ModuleNotFoundError) and a bare FileNotFoundError traceback
    # (missing binary at import time, no "Ran" line at all).
    ran = _RAN_RE.search(stderr)
    if _IMPORT_FAIL_RE.search(stderr):
        return SuiteResult(
            suite=module, path=str(test_file), ok=False, status="env-blocked",
            missing=_env_blocked_detail(stderr), duration=duration,
            detail=_tail(stderr),
        )
    if not ran:
        m = _MISSING_FILE_RE.search(stderr)
        if m:
            return SuiteResult(
                suite=module, path=str(test_file), ok=False,
                status="env-blocked", missing=f"missing binary: {m.group(1)}",
                duration=duration, detail=_tail(stderr),
            )
        return SuiteResult(
            suite=module, path=str(test_file), ok=False, status="failed",
            duration=duration, detail=_tail(stderr),
        )
    if _NO_TESTS_RE.search(stderr):
        return run_script_fallback(test_file, timeout, started, env)
    return SuiteResult(
        suite=module, path=str(test_file), tests=int(ran.group(1)), ok=False,
        status="failed", duration=duration, detail=_tail(stderr),
    )


def _is_binary(data: bytes) -> bool:
    return b"\0" in data[:8192]


def _markdown_hard_break_exempt(line: bytes) -> bool:
    """Standard Markdown hard-break idiom: a line ending in 2+ spaces."""
    return len(line) - len(line.rstrip(b" ")) >= 2


def scan_whitespace_file(file_path: Path, repo_root: Path) -> List[WhitespaceViolation]:
    """git-diff-check-equivalent scan of one text file.

    Conventions respected (documented in LYNX-CONSOLIDATED-SUITE-20261121.md):
    * ``*.patch`` / ``*.diff`` files are source-of-truth kernel artifacts and
      are exempt in full (trailing context whitespace is significant).
    * ``.md`` lines ending in 2+ spaces are Markdown hard breaks, not stray
      whitespace.
    Everything else: trailing space/tab, missing EOF newline, and conflict
    markers are violations.
    """
    violations: List[WhitespaceViolation] = []
    rel = str(file_path.relative_to(repo_root))
    name = file_path.name.lower()
    if name.endswith(PATCH_EXEMPT_SUFFIXES):
        return violations
    try:
        size = file_path.stat().st_size
        if size == 0:
            return violations
        if size > MAX_SCAN_BYTES:
            return violations
        data = file_path.read_bytes()
    except OSError:
        return violations
    if _is_binary(data):
        return violations
    if not data.endswith(b"\n"):
        violations.append(WhitespaceViolation(rel, 0, "missing-eof-newline"))
    is_md = name.endswith((".md", ".markdown"))
    marker_prefix = b"<" * 7
    line_no = 0
    for raw in data.split(b"\n"):
        line_no += 1
        if raw.startswith(marker_prefix + b" ") or raw == marker_prefix:
            violations.append(WhitespaceViolation(rel, line_no, "conflict-marker"))
        if raw.endswith(b"\t"):
            violations.append(WhitespaceViolation(rel, line_no, "trailing-whitespace"))
        elif raw.endswith(b" ") and not (is_md and _markdown_hard_break_exempt(raw)):
            violations.append(WhitespaceViolation(rel, line_no, "trailing-whitespace"))
    return violations


def tracked_files(repo_root: Path, prefix: str) -> List[Path]:
    """List git-tracked files under prefix (falls back to a bounded walk)."""
    try:
        res = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files", prefix],
            capture_output=True, text=True, timeout=60,
        )
        if res.returncode == 0:
            return [repo_root / p for p in res.stdout.splitlines() if p]
    except (OSError, subprocess.TimeoutExpired):
        pass
    # Fallback: walk, skipping known build/vendor artifact directories.
    skip = {
        "alpine-aarch64", "alpine-x86", "alpine-bootstrap", "aarch64-binutils",
        "aarch64-gcc", "avb-host", "build-deps", "adb-tmp",
        "android-user-home", "audio-codec-build-deps", "linux-port",
    }
    out: List[Path] = []
    tools = repo_root / prefix / "tools"
    if tools.is_dir():
        for p in tools.rglob("*.py"):
            if "__pycache__" not in p.parts:
                out.append(p)
    return out


def overall_ok(results: List[SuiteResult], ws_violations: List[WhitespaceViolation],
               strict: bool = False) -> bool:
    """Run verdict: no failed suites, whitespace clean, and (strict) no env-blocked."""
    if not results:
        return False
    if any(r.status in FAILED_STATUSES for r in results):
        return False
    if ws_violations:
        return False
    if strict and any(r.status == "env-blocked" for r in results):
        return False
    return True


_STATUS_LABELS = {
    "ok": "OK",
    "script-ok": "OK (script)",
    "failed": "FAIL",
    "script-failed": "FAIL (script)",
    "env-blocked": "ENV-BLOCKED",
}


def render_markdown(
    results: List[SuiteResult],
    ws_violations: List[WhitespaceViolation],
    wall: float,
    strict: bool = False,
) -> str:
    lines: List[str] = []
    lines.append("# Lynx Consolidated Test Suite Report")
    lines.append("")
    ok_count = sum(1 for r in results if r.ok)
    failed = [r for r in results if r.status in FAILED_STATUSES]
    env_blocked = [r for r in results if r.status == "env-blocked"]
    ws_ok = not ws_violations
    verdict = overall_ok(results, ws_violations, strict)
    lines.append(f"**Overall: {'PASS' if verdict else 'FAIL'}**")
    lines.append("")
    lines.append(f"- Suites: {len(results)} total, {ok_count} ok, "
                 f"{len(failed)} failed, {len(env_blocked)} env-blocked")
    lines.append(f"- Tests: {sum(r.tests for r in results)}")
    lines.append(f"- Wall clock: {wall:.2f}s")
    lines.append(f"- Whitespace sanity (git diff --check equivalent): "
                 f"{'CLEAN' if ws_ok else f'{len(ws_violations)} violation(s)'}")
    if env_blocked:
        lines.append("- Env-blocked (missing system dependency, suite not run): "
                     + "; ".join(f"`{r.suite}` [{r.missing}]" for r in env_blocked))
    if strict:
        lines.append("- Mode: strict (env-blocked counts as failure)")
    lines.append("")
    lines.append("| Suite | Tests | Result | Time (s) | Detail |")
    lines.append("|---|---|---|---|---|")
    for r in results:
        detail = (r.detail or "-").replace("|", "\\|")
        label = _STATUS_LABELS.get(r.status, "OK" if r.ok else "FAIL")
        lines.append(
            f"| {r.suite} | {r.tests if r.tests else '-'} | "
            f"{label} | {r.duration:.2f} | {detail} |"
        )
    if ws_violations:
        lines.append("")
        lines.append("### Whitespace violations")
        lines.append("")
        for v in ws_violations[:50]:
            lines.append(f"- `{v.path}`:{v.line} {v.kind}")
        if len(ws_violations) > 50:
            lines.append(f"- ... and {len(ws_violations) - 50} more")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Consolidated Lynx offline test-suite runner")
    parser.add_argument("--root", type=Path, default=None,
                        help="lynx/tools directory to scan (default: this file's dir)")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                        help=f"per-suite subprocess timeout seconds (default {DEFAULT_TIMEOUT})")
    parser.add_argument("--skip-whitespace", action="store_true",
                        help="skip the whitespace sanity scan")
    parser.add_argument("--strict", action="store_true",
                        help="count env-blocked suites (missing system deps) "
                             "as failures; for fully provisioned hosts")
    parser.add_argument("--json", action="store_true",
                        help="emit JSON instead of markdown")
    args = parser.parse_args()

    root = (args.root or tools_root()).resolve()
    if not root.is_dir():
        print(f"error: tools directory not found: {root}", file=sys.stderr)
        return 1

    started = time.monotonic()
    files = discover_test_files(root)
    if not files:
        print(f"error: no test_*.py found under {root}", file=sys.stderr)
        return 1

    results: List[SuiteResult] = []
    for f in files:
        results.append(run_suite(f, timeout=args.timeout))

    ws_violations: List[WhitespaceViolation] = []
    if not args.skip_whitespace:
        repo_root = root.parent.parent  # lynx/tools -> noobia
        prefix = "lynx"
        for tf in tracked_files(repo_root, prefix):
            ws_violations.extend(scan_whitespace_file(tf, repo_root))

    wall = time.monotonic() - started
    verdict = overall_ok(results, ws_violations, args.strict)
    if args.json:
        payload: Dict[str, Any] = {
            "suites": [
                {"suite": r.suite, "path": r.path, "tests": r.tests,
                 "ok": r.ok, "status": r.status or ("ok" if r.ok else "failed"),
                 "missing": r.missing,
                 "duration": round(r.duration, 3),
                 "detail": r.detail}
                for r in results
            ],
            "whitespace_violations": [
                {"path": v.path, "line": v.line, "kind": v.kind}
                for v in ws_violations
            ],
            "env_blocked": [r.suite for r in results if r.status == "env-blocked"],
            "wall_clock": round(wall, 3),
            "strict": args.strict,
            "overall_ok": verdict,
        }
        print(json.dumps(payload, indent=2))
    else:
        print(render_markdown(results, ws_violations, wall, args.strict))
    return 0 if verdict else 1


if __name__ == "__main__":
    sys.exit(main())
