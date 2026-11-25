#!/usr/bin/env python3
"""repo-secret-scan: secrets and private details in Noobia's PUBLIC repository (LNX-76).

Rose's backlog, "Sensitive information exposure audit" (Gwyn, 2026-11-25).
Runs on Nexus over the files Git tracks (what GitHub publishes). Read-only.

Looks for private key blocks, provider tokens (OpenAI, Anthropic, GitHub,
AWS, Google, Slack), password/secret/key assignments with a literal value,
and optional PRIVATE TERMS given at run time (e.g. a real name). The terms are
never stored by this tool, and every hit is printed masked.

    repo-secret-scan [--repo /noobia] [--term WORD ...] [--terms-file PATH] [--json]
Exit 0 = nothing found, 1 = findings, 2 = the scan failed.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

PATTERNS = [
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY")),
    ("openai-key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}")),
    ("anthropic-key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}")),
    ("github-token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}|\bgithub_pat_[A-Za-z0-9_]{40,}")),
    ("aws-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("google-key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("assigned-secret", re.compile(r"(?i)\b(password|passwd|secret|api[_-]?key|token)\b\s*[:=]\s*[\"']([^\"'\s]{8,})[\"']")),
]
# Test fixtures and obvious placeholders are not secrets.
PLACEHOLDER = re.compile(r"(?i)(test|example|dummy|fake|placeholder|changeme|xxxx|<[a-z_]+>|\$\{|\{\{|redacted)")
MAX_BYTES = 2_000_000


def mask(s: str) -> str:
    return s[:4] + "…" + f"({len(s)} chars)" if len(s) > 6 else "…"


def tracked(repo: Path) -> list[str]:
    out = subprocess.run(["git", "-C", str(repo), "ls-files", "-z"], capture_output=True, check=True)
    return [p for p in out.stdout.decode("utf-8", "replace").split("\0") if p]


def scan(repo: Path, terms: list[str]) -> list[dict]:
    term_rx = [(t, re.compile(rf"\b{re.escape(t)}\b", re.I)) for t in terms if t.strip()]
    hits = []
    for rel in tracked(repo):
        p = repo / rel
        try:
            if p.is_symlink() or p.stat().st_size > MAX_BYTES:
                continue
            data = p.read_bytes()
        except OSError:
            continue
        if b"\0" in data[:4096]:
            continue   # binary
        for n, line in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
            for kind, rx in PATTERNS:
                for m in rx.finditer(line):
                    value = m.group(m.lastindex or 0)
                    if PLACEHOLDER.search(line) or PLACEHOLDER.search(value):
                        continue
                    if kind == "assigned-secret" and os.path.basename(rel).startswith("test_"):
                        continue   # fixtures in unit tests
                    hits.append({"file": rel, "line": n, "kind": kind, "match": mask(value)})
            for t, rx in term_rx:
                if rx.search(line):
                    hits.append({"file": rel, "line": n, "kind": "private-term", "match": mask(t)})
    return hits


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", type=Path, default=Path(os.environ.get("NOOBIA", "/noobia")))
    ap.add_argument("--term", action="append", default=[], help="a private word to look for (not stored)")
    ap.add_argument("--terms-file", type=Path, help="private words, one per line (keep it outside the repo)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    terms = list(args.term)
    if args.terms_file:
        terms += [l.strip() for l in args.terms_file.read_text().splitlines() if l.strip()]
    try:
        hits = scan(args.repo, terms)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 2
    if args.json:
        print(json.dumps({"ok": not hits, "hits": hits}, indent=1))
    else:
        by_file = {}
        for h in hits:
            by_file.setdefault(h["file"], []).append(h)
        print(f"repo secret scan: {'clean' if not hits else f'{len(hits)} hit(s) in {len(by_file)} file(s)'}")
        for f, hs in sorted(by_file.items()):
            kinds = sorted({h["kind"] for h in hs})
            print(f"  {f}: {', '.join(kinds)} (lines {', '.join(str(h['line']) for h in hs[:8])}"
                  f"{' ...' if len(hs) > 8 else ''})")
    return 0 if not hits else 1


if __name__ == "__main__":
    sys.exit(main())
