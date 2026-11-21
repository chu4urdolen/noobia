#!/usr/bin/env python3
"""Source-to-installed diff of Lynx's agent tool catalog, from a saved snapshot.

Compares the tracked source pairs in ``lynx/tools/local_calls`` with the
SHA-256 list of the phone's installed catalog
(``/usr/local/share/lynx/agent-tools``) saved by ``lynx_status_snapshot.py``.
Reports, per tool, exactly which files are missing on the phone, added on the
phone, or have different hashes. Output contains only tool names, file kinds,
and 12-character hash prefixes, never file contents.

Bounded and deterministic:
- entries are sorted;
- at most ``--limit`` (default 50) are listed, while counts stay exact;
- hostile or malformed names are counted and shown only as an escaped
  40-character preview;
- duplicate catalog keys in the snapshot JSON are reported, not silently
  merged.

Never contacts Lynx, writes nothing, and never syncs anything.

  lynx_catalog_diff.py --text            # uses state/latest.json
  lynx_catalog_diff.py --status FILE     # JSON
  lynx_catalog_diff.py --fail-on-drift   # exit 2 when not in sync

Exit status: 0 compared (in sync, or drift without --fail-on-drift), 2 drift
with --fail-on-drift, 1 error or no catalog in the snapshot.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import lynx_tool_manifest as mm  # noqa: E402

DEFAULT_STATUS = HERE / "state" / "latest.json"
NAME = re.compile(r"^([a-z][a-z0-9_]{0,63})\.(json|sh)$")
HASH = re.compile(r"^[0-9a-f]{64}$")
SHORT = 12
DEFAULT_LIMIT = 50
MAX_SNAPSHOT_BYTES = mm.MAX_SNAPSHOT_BYTES


class DiffError(Exception):
    pass


def preview(text):
    text = str(text)
    shown = json.dumps(text[:40], ensure_ascii=True)
    return shown + ("…" if len(text) > 40 else "")


def source_files(source_dir=mm.SOURCE_DIR):
    files = {}
    for path in sorted(Path(source_dir).iterdir()):
        match = NAME.match(path.name)
        if match and path.is_file() and not path.is_symlink():
            files[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def load_catalog(path):
    """Installed catalog files from a snapshot, keeping duplicate keys visible."""
    path = Path(path)
    if path.stat().st_size > MAX_SNAPSHOT_BYTES:
        raise DiffError(f"snapshot exceeds {MAX_SNAPSHOT_BYTES} bytes")
    duplicates = []

    def pairs(items):
        seen = {}
        for key, value in items:
            if key in seen:
                duplicates.append(key)
            seen[key] = value
        return seen

    try:
        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs)
    except (ValueError, UnicodeError) as exc:
        raise DiffError(f"snapshot is not JSON: {exc}") from None
    catalog = data.get("catalog") if isinstance(data, dict) else None
    files = catalog.get("files") if isinstance(catalog, dict) else None
    if not isinstance(files, dict):
        raise DiffError("snapshot has no installed catalog (catalog.files)")
    return data, files, sorted(set(duplicates) & set(files))


def diff(source, installed, duplicates=(), limit=DEFAULT_LIMIT):
    rejected = []
    clean = {}
    for name, digest in installed.items():
        if not isinstance(name, str) or not NAME.match(name) or \
                not isinstance(digest, str) or not HASH.match(digest):
            rejected.append(preview(name))
        else:
            clean[name] = digest

    tools = sorted({NAME.match(n).group(1) for n in list(source) + list(clean)})
    entries = []
    counts = {"in_sync": 0, "hash_differs": 0, "missing_on_phone": 0,
              "added_on_phone": 0, "partial": 0}
    for tool in tools:
        files = {}
        for kind in ("json", "sh"):
            name = f"{tool}.{kind}"
            src, inst = source.get(name), clean.get(name)
            if src and inst:
                files[kind] = "same" if src == inst else "differs"
            elif src:
                files[kind] = "missing_on_phone"
            elif inst:
                files[kind] = "added_on_phone"
        states = set(files.values())
        in_source = any(f"{tool}.{k}" in source for k in ("json", "sh"))
        on_phone = any(f"{tool}.{k}" in clean for k in ("json", "sh"))
        if states == {"same"} and len(files) == 2:
            status = "in_sync"
        elif not on_phone:
            status = "missing_on_phone"
        elif not in_source:
            status = "added_on_phone"
        elif "differs" in states and states <= {"same", "differs"} and len(files) == 2:
            status = "hash_differs"
        else:
            status = "partial"  # one file missing, added, or a pair split
        counts[status] += 1
        if status != "in_sync":
            entries.append({
                "tool": tool, "status": status, "files": files,
                "source_sha256": {k: source[f"{tool}.{k}"][:SHORT] for k in ("json", "sh")
                                  if f"{tool}.{k}" in source},
                "installed_sha256": {k: clean[f"{tool}.{k}"][:SHORT] for k in ("json", "sh")
                                     if f"{tool}.{k}" in clean}})
    in_sync = not entries and not rejected and not duplicates
    return {
        "in_sync": in_sync,
        "source_tools": len({NAME.match(n).group(1) for n in source}),
        "installed_tools": len({NAME.match(n).group(1) for n in clean}),
        "counts": counts,
        "rejected_entries": {"count": len(rejected), "preview": sorted(rejected)[:10]},
        "duplicate_entries": list(duplicates)[:10],
        "entries": entries[:limit],
        "entries_truncated": max(0, len(entries) - limit),
    }


def text_report(result, captured_at):
    lines = [f"Lynx catalog diff (snapshot {captured_at or 'time unknown'}): "
             f"{'IN SYNC' if result['in_sync'] else 'DRIFT'}; source "
             f"{result['source_tools']} tools, installed {result['installed_tools']}"]
    counts = {k: v for k, v in result["counts"].items() if v}
    lines.append("counts: " + ", ".join(f"{k}={v}" for k, v in counts.items()))
    for entry in result["entries"]:
        files = " ".join(f"{k}:{v}" for k, v in entry["files"].items())
        lines.append(f"  {entry['status']:<16} {entry['tool']}  {files}")
    if result["entries_truncated"]:
        lines.append(f"  ... {result['entries_truncated']} more not shown (raise --limit)")
    if result["rejected_entries"]["count"]:
        lines.append(f"rejected installed entries: {result['rejected_entries']['count']} "
                     f"(previews: {', '.join(result['rejected_entries']['preview'])})")
    if result["duplicate_entries"]:
        lines.append("duplicate installed entries: " + ", ".join(result["duplicate_entries"]))
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--status", default=str(DEFAULT_STATUS), metavar="FILE")
    parser.add_argument("--source", default=str(mm.SOURCE_DIR))
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--text", action="store_true")
    parser.add_argument("--fail-on-drift", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 500:
        parser.error("--limit must be 1..500")
    try:
        data, installed, duplicates = load_catalog(args.status)
        result = diff(source_files(args.source), installed, duplicates, args.limit)
    except (DiffError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    captured = data.get("captured_at") if isinstance(data.get("captured_at"), str) else None
    if args.text:
        sys.stdout.write(text_report(result, captured))
    else:
        print(json.dumps(dict(result, ok=True, snapshot=captured), indent=2, sort_keys=True))
    return 2 if args.fail_on_drift and not result["in_sync"] else 0


if __name__ == "__main__":
    sys.exit(main())
