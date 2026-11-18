#!/usr/bin/env python3
"""Noobia's shared memory in forge.db: where things are, and what projects did.

Three tables sit next to the Foreman's `projects` table:

* `nexus_paths`   one row per important path on Nexus with a description, so an
                  agent can look something up instead of searching again.
* `project_notes` dated notes per project (decisions, state, handoffs) that may
                  cite rows in `nexus_paths`.
* `embeddings`    sentence vectors for meaning-based search: Qwen3-Embedding on
                  the RTX 5090 through Ollama when Ollama may keep it loaded
                  next to Qwen, otherwise a small CPU model (forge venv).

Every command is non-interactive and prints concise text, or JSON with --json.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys

DB = Path(os.environ.get("FORGE_DB", "/noobia/dushich/workspace/forge.db"))
GPU_MODEL = "qwen3-embedding:0.6b"
CPU_MODEL = "BAAI/bge-small-en-v1.5"
MODEL_CACHE = "/opt/noobia/forge-venv/models"
OLLAMA = "http://127.0.0.1:11434"
QUERY_INSTRUCTION = ("Instruct: Given a question about the Noobia computer Nexus, retrieve the "
                     "paths, projects, and notes that answer it\nQuery: ")
# Similarities cluster differently per model; (floor, span) rescales them to ~0..1.
SIMILARITY_SCALE = {GPU_MODEL: (0.35, 0.4), CPU_MODEL: (0.55, 0.35)}
KINDS = ("dir", "file", "tool", "service", "db", "config", "doc", "device", "log", "link", "other")

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    project_name TEXT PRIMARY KEY,
    executor TEXT NOT NULL,
    receiver TEXT NOT NULL,
    description TEXT,
    hardware_ready INTEGER NOT NULL,
    agentic_tools TEXT,
    conversation_id TEXT);
CREATE TABLE IF NOT EXISTS nexus_paths (
    path TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    owner TEXT,
    description TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '',
    project TEXT,
    updated_by TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    present INTEGER,
    checked_at TEXT);
CREATE TABLE IF NOT EXISTS project_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_name TEXT NOT NULL,
    author TEXT NOT NULL,
    note TEXT NOT NULL,
    paths TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS project_notes_project ON project_notes(project_name, id);
CREATE TABLE IF NOT EXISTS embeddings (
    source TEXT NOT NULL,
    key TEXT NOT NULL,
    model TEXT NOT NULL,
    text_hash TEXT NOT NULL,
    vector BLOB NOT NULL,
    PRIMARY KEY (source, key));
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    db = sqlite3.connect(DB, timeout=15)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    return db


def clean_path(raw: str) -> str:
    path = os.path.normpath(raw)
    if not path.startswith("/"):
        raise ValueError("Paths must be absolute")
    return path


def require(value: str | None, name: str, limit: int = 4000) -> str:
    if not value or not value.strip():
        raise ValueError(f"{name} is required")
    if len(value) > limit:
        raise ValueError(f"{name} exceeds {limit} characters")
    return value.strip()


# -- optional meaning-based search ---------------------------------------------
_model = None
_gpu = None


def _ollama(path: str, body: dict | None = None, timeout: float = 3) -> dict:
    import urllib.request
    request = urllib.request.Request(OLLAMA + path, data=json.dumps(body).encode() if body else None,
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def gpu_ready() -> bool:
    """Use the GPU model only when loading it cannot evict Dushich's Qwen.

    That is when it is already loaded, or when Ollama allows two loaded models.
    """
    global _gpu
    if _gpu is None:
        _gpu = False
        try:
            if any(m.get("name") == GPU_MODEL for m in _ollama("/api/ps").get("models", [])):
                _gpu = True
            else:
                import subprocess
                env = subprocess.run(["systemctl", "show", "ollama", "-p", "Environment"],
                                     capture_output=True, text=True, timeout=5).stdout
                found = re.search(r"OLLAMA_MAX_LOADED_MODELS=(\d+)", env)
                _gpu = bool(found and int(found.group(1)) >= 2
                            and any(m.get("name") == GPU_MODEL for m in _ollama("/api/tags").get("models", [])))
        except (OSError, ValueError):
            _gpu = False
    return _gpu


def embedder():
    """Return the CPU fastembed model, or None when the forge venv is unavailable."""
    global _model
    if _model is None:
        try:
            from fastembed import TextEmbedding
        except ImportError:
            _model = False
        else:
            _model = TextEmbedding(CPU_MODEL, cache_dir=MODEL_CACHE)
    return _model or None


def active_model() -> str | None:
    if gpu_ready():
        return GPU_MODEL
    return CPU_MODEL if embedder() else None


def vectors(texts: list[str], query: bool = False):
    model = active_model()
    if not model or not texts:
        return None
    import numpy
    if model == GPU_MODEL:
        inputs = [QUERY_INSTRUCTION + t if query else t for t in texts]
        reply = _ollama("/api/embed", {"model": GPU_MODEL, "input": inputs, "keep_alive": -1,
                                       "options": {"num_ctx": 2048}}, timeout=120)
        result = numpy.array(reply["embeddings"], dtype=numpy.float32)
    else:
        result = numpy.array(list(embedder().embed(texts)), dtype=numpy.float32)
    return result / numpy.linalg.norm(result, axis=1, keepdims=True)


def entry_text(source: str, row: sqlite3.Row) -> str:
    if source == "path":
        return f"{row['path']} ({row['kind']}, {row['owner'] or 'shared'}): {row['description']} {row['tags']}"
    if source == "note":
        return f"Note on {row['project_name']} by {row['author']}: {row['note']}"
    return f"Project {row['project_name']} ({row['executor']} for {row['receiver']}): {row['description'] or ''}"


def all_entries(db: sqlite3.Connection) -> list[tuple[str, str, str]]:
    found = [("path", r["path"], entry_text("path", r)) for r in db.execute("SELECT * FROM nexus_paths")]
    found += [("note", str(r["id"]), entry_text("note", r)) for r in db.execute("SELECT * FROM project_notes")]
    found += [("project", r["project_name"], entry_text("project", r)) for r in db.execute("SELECT * FROM projects")]
    return found


def refresh_embeddings(db: sqlite3.Connection, only: list[tuple[str, str]] | None = None) -> int:
    """Embed new or changed entries; return how many were (re)computed."""
    model = active_model()
    if not model:
        return 0
    # One model's vectors at a time; switching models re-embeds everything.
    db.execute("DELETE FROM embeddings WHERE model<>?", (model,))
    stored = {(r["source"], r["key"]): r["text_hash"] for r in
              db.execute("SELECT source, key, text_hash FROM embeddings WHERE model=?", (model,))}
    entries = [e for e in all_entries(db) if only is None or (e[0], e[1]) in only]
    stale = [(s, k, t, hashlib.sha256(t.encode()).hexdigest()) for s, k, t in entries]
    stale = [e for e in stale if stored.get((e[0], e[1])) != e[3]]
    for start in range(0, len(stale), 64):
        batch = stale[start:start + 64]
        for (source, key, _, digest), vector in zip(batch, vectors([e[2] for e in batch])):
            db.execute("INSERT OR REPLACE INTO embeddings VALUES (?, ?, ?, ?, ?)",
                       (source, key, model, digest, vector.tobytes()))
    live = {(s, k) for s, k, _ in all_entries(db)}
    for source, key in list(stored):
        if (source, key) not in live:
            db.execute("DELETE FROM embeddings WHERE source=? AND key=?", (source, key))
    db.commit()
    return len(stale)


# -- search -------------------------------------------------------------------
def search(db: sqlite3.Connection, query: str, limit: int = 10, sources=("path", "note", "project")) -> list[dict]:
    words = [w for w in re.findall(r"[\w./-]+", query.lower()) if len(w) > 1]
    scores: dict[tuple[str, str], float] = {}
    texts = {}
    for source, key, text in all_entries(db):
        if source not in sources:
            continue
        texts[(source, key)] = text
        lowered = text.lower()
        hits = sum(1 for w in words if w in lowered)
        if hits:
            scores[(source, key)] = hits / len(words)
    model = active_model()
    query_vector = vectors([query], query=True) if model else None
    if query_vector is not None:
        import numpy
        floor, span = SIMILARITY_SCALE[model]
        for row in db.execute("SELECT source, key, vector FROM embeddings WHERE model=?", (model,)):
            if (row["source"], row["key"]) not in texts:
                continue
            similarity = float(numpy.frombuffer(row["vector"], dtype=numpy.float32) @ query_vector[0])
            meaning = max(0.0, (similarity - floor) / span)
            key = (row["source"], row["key"])
            scores[key] = scores.get(key, 0.0) + meaning
    ranked = sorted(((k, v) for k, v in scores.items() if v > 0.05), key=lambda item: -item[1])[:limit]
    return [{"source": s, "key": k, "score": round(v, 3), "text": texts[(s, k)]} for (s, k), v in ranked]


# -- commands -----------------------------------------------------------------
def path_set(db, path, description, kind, owner, tags, project, by) -> dict:
    path = clean_path(path)
    if kind not in KINDS:
        raise ValueError(f"kind must be one of: {', '.join(KINDS)}")
    if project and not db.execute("SELECT 1 FROM projects WHERE project_name=?", (project,)).fetchone():
        raise ValueError(f"Unknown project: {project}")
    db.execute("""INSERT INTO nexus_paths (path, kind, owner, description, tags, project,
                  updated_by, updated_at, present, checked_at)
                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                  ON CONFLICT(path) DO UPDATE SET kind=excluded.kind,
                  owner=COALESCE(excluded.owner, owner), description=excluded.description,
                  tags=CASE WHEN excluded.tags='' THEN tags ELSE excluded.tags END,
                  project=COALESCE(excluded.project, project), updated_by=excluded.updated_by,
                  updated_at=excluded.updated_at, present=excluded.present,
                  checked_at=excluded.checked_at""",
               (path, kind, owner, require(description, "description", 2000), tags or "",
                project, require(by, "--by", 80), now(), int(os.path.lexists(path)), now()))
    db.commit()
    refresh_embeddings(db, [("path", path)])
    return dict(db.execute("SELECT * FROM nexus_paths WHERE path=?", (path,)).fetchone())


def note_add(db, project, text, paths, by) -> dict:
    if not db.execute("SELECT 1 FROM projects WHERE project_name=?", (project,)).fetchone():
        raise ValueError(f"Unknown project: {project} (add it with `projects add`)")
    cited = [clean_path(p) for p in paths]
    cursor = db.execute("INSERT INTO project_notes (project_name, author, note, paths, created_at) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (project, require(by, "--by", 80), require(text, "note", 6000),
                         json.dumps(cited), now()))
    db.commit()
    refresh_embeddings(db, [("note", str(cursor.lastrowid))])
    return dict(db.execute("SELECT * FROM project_notes WHERE id=?", (cursor.lastrowid,)).fetchone())


def project_view(db, name: str, notes: int) -> dict:
    row = db.execute("SELECT * FROM projects WHERE project_name=?", (name,)).fetchone()
    if not row:
        raise ValueError(f"Unknown project: {name}")
    result = dict(row)
    result["paths"] = [dict(r) for r in db.execute(
        "SELECT path, kind, description FROM nexus_paths WHERE project=? ORDER BY path", (name,))]
    result["notes"] = [dict(r) for r in db.execute(
        "SELECT * FROM (SELECT * FROM project_notes WHERE project_name=? ORDER BY id DESC LIMIT ?) "
        "ORDER BY id", (name, notes))]
    return result


def render(value) -> str:
    if isinstance(value, list):
        return "\n".join(render(item) for item in value) or "(none)"
    if not isinstance(value, dict):
        return str(value)
    if "source" in value and "score" in value:
        return f"[{value['source']} {value['score']}] {value['text']}"
    if "path" in value and "kind" in value:
        mark = "" if value.get("present", 1) else " (MISSING)"
        meta = ", ".join(x for x in (value["kind"], value.get("owner") or "", value.get("project") or "") if x)
        return f"{value['path']}{mark} [{meta}] {value['description']}"
    if "note" in value:
        cited = json.loads(value["paths"]) if isinstance(value["paths"], str) else value["paths"]
        return (f"#{value['id']} {value['created_at'][:16]} {value['author']}: {value['note']}"
                + (f"\n    paths: {', '.join(cited)}" if cited else ""))
    if "project_name" in value:
        lines = [f"{value['project_name']} — {value['executor']} for {value['receiver']}"
                 f"{'' if value['hardware_ready'] else ' (hardware not ready)'}: {value['description'] or ''}"]
        if "paths" in value:
            lines += ["  paths:"] + [f"    {p['path']} [{p['kind']}] {p['description']}" for p in value["paths"]]
            lines += ["  notes:"] + [f"    {render(n)}" for n in value["notes"]]
        return "\n".join(lines)
    return json.dumps(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="forge-db", description=__doc__.split("\n")[0])
    parser.add_argument("--json", action="store_true", help="print JSON")
    sub = parser.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("search", help="find paths, notes, and projects by words and meaning")
    s.add_argument("query", nargs="+")
    s.add_argument("--limit", type=int, default=10)
    s.add_argument("--only", choices=("path", "note", "project"))

    p = sub.add_parser("path", help="read or record a Nexus path")
    pa = p.add_subparsers(dest="action", required=True)
    pa.add_parser("get").add_argument("path")
    ps = pa.add_parser("set")
    ps.add_argument("path")
    ps.add_argument("--description", "-d", required=True)
    ps.add_argument("--kind", "-k", default="file", choices=KINDS)
    ps.add_argument("--owner", "-o")
    ps.add_argument("--tags", "-t", default="")
    ps.add_argument("--project")
    ps.add_argument("--by", required=True, help="your name, e.g. Dushich")
    pr = pa.add_parser("remove")
    pr.add_argument("path")
    pr.add_argument("--by", required=True)
    pl = pa.add_parser("list")
    pl.add_argument("--prefix", default="/")
    pl.add_argument("--limit", type=int, default=200)
    pc = pa.add_parser("check", help="re-check that recorded paths exist")
    pc.add_argument("--prefix", default="/")

    j = sub.add_parser("project", help="read or add Foreman projects")
    ja = j.add_subparsers(dest="action", required=True)
    ja.add_parser("list")
    jg = ja.add_parser("get")
    jg.add_argument("name")
    jg.add_argument("--notes", type=int, default=10)
    jn = ja.add_parser("add")
    jn.add_argument("name")
    jn.add_argument("--executor", required=True)
    jn.add_argument("--receiver", required=True)
    jn.add_argument("--description", "-d", required=True)
    jn.add_argument("--hardware-ready", action="store_true")

    n = sub.add_parser("note", help="read or add project notes")
    na = n.add_subparsers(dest="action", required=True)
    nn = na.add_parser("add")
    nn.add_argument("project")
    nn.add_argument("text")
    nn.add_argument("--path", action="append", default=[])
    nn.add_argument("--by", required=True)
    nl = na.add_parser("list")
    nl.add_argument("project")
    nl.add_argument("--limit", type=int, default=20)

    c = sub.add_parser("changes", help="rows written since a UTC ISO time")
    c.add_argument("--since", required=True)
    sub.add_parser("embed", help="refresh meaning-search vectors")
    sub.add_parser("stats")

    args = parser.parse_args(argv)
    try:
        db = connect()
        if args.cmd == "search":
            sources = (args.only,) if args.only else ("path", "note", "project")
            result = search(db, " ".join(args.query), args.limit, sources)
        elif args.cmd == "path" and args.action == "get":
            row = db.execute("SELECT * FROM nexus_paths WHERE path=?", (clean_path(args.path),)).fetchone()
            if not row:
                raise ValueError("Path is not recorded; try `forge-db search`")
            result = dict(row)
        elif args.cmd == "path" and args.action == "set":
            result = path_set(db, args.path, args.description, args.kind, args.owner,
                              args.tags, args.project, args.by)
        elif args.cmd == "path" and args.action == "remove":
            require(args.by, "--by")
            deleted = db.execute("DELETE FROM nexus_paths WHERE path=?", (clean_path(args.path),)).rowcount
            db.commit()
            refresh_embeddings(db, [])
            result = f"removed {deleted} row(s)"
        elif args.cmd == "path" and args.action == "list":
            prefix = clean_path(args.prefix)
            result = [dict(r) for r in db.execute(
                "SELECT * FROM nexus_paths WHERE path=? OR path LIKE ? ORDER BY path LIMIT ?",
                (prefix, prefix.rstrip("/") + "/%", args.limit))]
        elif args.cmd == "path" and args.action == "check":
            prefix = clean_path(args.prefix)
            missing = []
            for row in db.execute("SELECT path FROM nexus_paths WHERE path=? OR path LIKE ?",
                                  (prefix, prefix.rstrip("/") + "/%")).fetchall():
                present = os.path.lexists(row["path"])
                db.execute("UPDATE nexus_paths SET present=?, checked_at=? WHERE path=?",
                           (int(present), now(), row["path"]))
                if not present:
                    missing.append(row["path"])
            db.commit()
            result = {"missing": missing} if args.json else ("missing: " + ", ".join(missing) if missing else "all recorded paths exist")
        elif args.cmd == "project" and args.action == "list":
            result = [dict(r) for r in db.execute("SELECT * FROM projects ORDER BY project_name")]
        elif args.cmd == "project" and args.action == "get":
            result = project_view(db, args.name, args.notes)
        elif args.cmd == "project" and args.action == "add":
            db.execute("INSERT INTO projects (project_name, executor, receiver, description, "
                       "hardware_ready, agentic_tools) VALUES (?, ?, ?, ?, ?, ?)",
                       (require(args.name, "name", 80), args.executor, args.receiver,
                        require(args.description, "description"), int(args.hardware_ready),
                        json.dumps(["forge-db"])))
            db.commit()
            refresh_embeddings(db, [("project", args.name)])
            result = project_view(db, args.name, 0)
        elif args.cmd == "note" and args.action == "add":
            result = note_add(db, args.project, args.text, args.path, args.by)
        elif args.cmd == "note" and args.action == "list":
            result = [dict(r) for r in db.execute(
                "SELECT * FROM (SELECT * FROM project_notes WHERE project_name=? ORDER BY id DESC LIMIT ?) "
                "ORDER BY id", (args.project, args.limit))]
        elif args.cmd == "changes":
            result = {"paths": [dict(r) for r in db.execute(
                          "SELECT * FROM nexus_paths WHERE updated_at>=? ORDER BY updated_at", (args.since,))],
                      "notes": [dict(r) for r in db.execute(
                          "SELECT * FROM project_notes WHERE created_at>=? ORDER BY id", (args.since,))]}
            if not args.json:
                result = result["paths"] + result["notes"]
        elif args.cmd == "embed":
            changed = refresh_embeddings(db)
            result = (f"refreshed {changed} vector(s) with {active_model()}" if active_model()
                      else "meaning search unavailable: run with /opt/noobia/forge-venv/bin/python")
        else:
            counts = {t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                      for t in ("projects", "nexus_paths", "project_notes", "embeddings")}
            result = {**counts, "db": str(DB), "meaning_model": active_model()}
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(f"forge-db: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=1, default=str) if args.json else render(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
