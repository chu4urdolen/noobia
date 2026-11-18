#!/usr/bin/env python3
"""Compact Dushich helper outputs to save tokens.

Strips repetitive `--------` header blocks, intermediate tool steps, and
verbose unittest progress lines so only the short final output survives.
Stdlib only.
"""

from __future__ import annotations

import re

_TOKENS_TAIL_RE = re.compile(r"\ntokens used\n.*$", re.DOTALL)
_DASH_LINE_RE = re.fullmatch
_OK_TEST_LINE_RE = re.compile(r"^test_\S+.*\.\.\. ok$")
_REPORT_HEADERS = (
    "Dushich task:",
    "Attempts:",
    "Git HEAD:",
    "Test exit:",
    "Report:",
    "Thread:",
)


def extract_final_codex_reply(raw_text: str, max_chars: int = 400) -> str:
    """Extract the final codex reply from raw `dushich exec` / Codex CLI output.

    Strips the trailing `tokens used` block, then takes the text after the
    LAST `\\ncodex\\n` marker (or after the last `--------` header line when no
    marker exists), strips whitespace, and truncates to ``max_chars``.
    """
    text = _TOKENS_TAIL_RE.sub("", raw_text)
    marker = text.rfind("\ncodex\n")
    if marker != -1:
        candidate = text[marker + len("\ncodex\n"):]
    else:
        idx = text.rfind("--------\n")
        candidate = text[idx + len("--------\n"):] if idx != -1 else text
    candidate = candidate.strip()
    if len(candidate) > max_chars:
        candidate = candidate[:max_chars]
    return candidate


def compact_test_output(raw_output: str, exit_code: int = 0, max_fail_chars: int = 600) -> str:
    """Compact a unittest run to a one-line summary (or a failure tail)."""
    if exit_code != 0:
        text = raw_output.strip()
        return text[-max_fail_chars:] if len(text) > max_fail_chars else text
    separator = "-" * 70
    if separator in raw_output:
        tail = raw_output.split(separator, 1)[1]
        ran_match = re.search(r"^Ran .* tests? .*$", tail, re.MULTILINE)
        status = "OK" if re.search(r"^\s*OK\s*$", tail, re.MULTILINE) else "FAILED"
        if ran_match:
            return f"{ran_match.group(0).strip()} ({status})"
        return f"Tests finished ({status})"
    for line in reversed(raw_output.splitlines()):
        if line.strip():
            return line.strip()[:160]
    return ""


def _is_dropped_line(line: str) -> bool:
    if re.fullmatch(r"-{3,}", line):
        return True
    if _OK_TEST_LINE_RE.match(line):
        return True
    return False


def compact_task_report(raw_report: str, max_reply_chars: int = 400) -> str:
    """Compact a `delegate-dushich` task report to the status header plus a
    capped `Dushich's report` section.

    Drops individual `test_... ... ok` lines and `--------` blocks, keeps the
    status header lines (`Dushich task:`, `Attempts:`, `Git HEAD:`,
    `Test exit:`, `Report:`, `Thread:`), and caps the report text at
    ``max_reply_chars``.
    """
    kept: list[str] = []
    report_parts: list[str] = []
    collecting_report = False
    for raw in raw_report.splitlines():
        line = raw.strip()
        if not line:
            collecting_report = False
            continue
        if _is_dropped_line(line):
            continue
        if line.startswith("Dushich's report"):
            collecting_report = True
            rest = line[len("Dushich's report"):].strip().lstrip(":").strip()
            if rest:
                report_parts.append(rest)
            continue
        if any(line.startswith(prefix) for prefix in _REPORT_HEADERS):
            collecting_report = False
            kept.append(line)
            continue
        if collecting_report:
            report_parts.append(line)
            continue
        kept.append(line)
    if report_parts:
        kept.append("Dushich's report: " + " ".join(report_parts)[:max_reply_chars])
    return "\n".join(kept)
