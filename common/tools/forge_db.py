#!/usr/bin/env python3
"""Noobia's shared memory in forge.db: where things are, and what projects did.

Tables:

* `projects`      the project registry: executor, receiver, and when (and for
                  whom) someone last worked on it, so agents notice when two
                  of them are about to work on one project at once.
* `nexus_paths`   one row per important path on Nexus with a description and
                  free-text search keywords, so an agent can look something up
                  instead of searching again.
* `project_notes` dated notes per project (decisions, state, handoffs) that may
                  cite rows in `nexus_paths`.
* `tags`          a small curated vocabulary of UPPERCASE tags (ROSE, SECURITY,
  `tag_links`     NETWORK, ART, ...); any path or project can carry several.
* `embeddings`    sentence vectors for meaning-based search: Qwen3-Embedding on
                  the RTX 5090 through Ollama when Ollama may keep it loaded
                  next to Qwen, otherwise a small CPU model (forge venv).

Every command is non-interactive and prints concise text, or JSON with --json.
forge-db is the only program that reads or writes forge.db. The database lives
at $NOOBIA/dushich/workspace/forge.db (NOOBIA defaults to /noobia; FORGE_DB
overrides the whole path) and is created, with every table, on first use.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys

NOOBIA = Path(os.environ.get("NOOBIA", "/noobia"))
DB = Path(os.environ.get("FORGE_DB") or NOOBIA / "dushich/workspace/forge.db")
# Work on a project for one agent counts as ongoing for this long.
ACTIVE_HOURS = 2
GPU_MODEL = "qwen3-embedding:0.6b"
CPU_MODEL = "BAAI/bge-small-en-v1.5"
MODEL_CACHE = str(NOOBIA / "common/runtime/models")  # fastembed's downloaded CPU model
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
    last_modified TEXT,
    modified_for TEXT);
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
    checked_at TEXT,
    hit_count INTEGER NOT NULL DEFAULT 0,
    last_hit_at TEXT,
    last_hit_by TEXT);
CREATE TABLE IF NOT EXISTS project_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_name TEXT NOT NULL,
    author TEXT NOT NULL,
    note TEXT NOT NULL,
    paths TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS project_notes_project ON project_notes(project_name, id);
CREATE TABLE IF NOT EXISTS tags (
    name TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tag_links (
    source TEXT NOT NULL CHECK (source IN ('path', 'project')),
    key TEXT NOT NULL,
    tag TEXT NOT NULL REFERENCES tags(name),
    added_by TEXT NOT NULL,
    added_at TEXT NOT NULL,
    PRIMARY KEY (source, key, tag));
CREATE INDEX IF NOT EXISTS tag_links_tag ON tag_links(tag);
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


ADDED_COLUMNS = {  # columns newer than the first atlases; added in place
    "nexus_paths": (("hit_count", "INTEGER NOT NULL DEFAULT 0"), ("last_hit_at", "TEXT"),
                    ("last_hit_by", "TEXT")),
    "projects": (("last_modified", "TEXT"), ("modified_for", "TEXT")),
}
REMOVED_COLUMNS = {  # columns older atlases still carry; dropped in place
    "projects": ("conversation_id",),
}


def connect() -> sqlite3.Connection:
    DB.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB, timeout=15)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    for table, added in ADDED_COLUMNS.items():
        columns = {r["name"] for r in db.execute(f"PRAGMA table_info({table})")}
        for column, spec in added:
            if column not in columns:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {spec}")
    for table, columns in REMOVED_COLUMNS.items():
        present = {r["name"] for r in db.execute(f"PRAGMA table_info({table})")}
        for column in columns:
            if column in present:
                db.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
    db.commit()
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


# -- tags ---------------------------------------------------------------------
TAG = re.compile(r"^[A-Z][A-Z0-9_]{1,31}$")


def tag_name(raw: str) -> str:
    name = raw.strip().upper().replace("-", "_").replace(" ", "_").lstrip("#")
    if not TAG.fullmatch(name):
        raise ValueError(f"Tag names are 2-32 letters, digits, or _: {raw!r}")
    return name


def tag_map(db: sqlite3.Connection) -> dict[tuple[str, str], list[str]]:
    found: dict[tuple[str, str], list[str]] = {}
    for row in db.execute("SELECT source, key, tag FROM tag_links ORDER BY tag"):
        found.setdefault((row["source"], row["key"]), []).append(row["tag"])
    return found


def tag_attach(db, tag: str, source: str, keys: list[str], by: str, commit: bool = True) -> int:
    tag = tag_name(tag)
    if not db.execute("SELECT 1 FROM tags WHERE name=?", (tag,)).fetchone():
        raise ValueError(f"Unknown tag {tag}; define it first with `forge-db tag add {tag} -d ...`")
    table, column = ("nexus_paths", "path") if source == "path" else ("projects", "project_name")
    added = 0
    for key in keys:
        key = clean_path(key) if source == "path" else key
        if not db.execute(f"SELECT 1 FROM {table} WHERE {column}=?", (key,)).fetchone():
            raise ValueError(f"Unknown {source}: {key}")
        added += db.execute("INSERT OR IGNORE INTO tag_links VALUES (?, ?, ?, ?, ?)",
                            (source, key, tag, require(by, "--by", 80), now())).rowcount
    if commit:
        db.commit()
        refresh_embeddings(db, [(source, k if source != "path" else clean_path(k)) for k in keys])
    return added


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


def entry_text(source: str, row: sqlite3.Row, tags: list[str] = ()) -> str:
    marks = "".join(f" #{t}" for t in tags)
    if source == "path":
        return f"{row['path']} ({row['kind']}, {row['owner'] or 'shared'}): {row['description']} {row['tags']}{marks}"
    if source == "note":
        return f"Note on {row['project_name']} by {row['author']}: {row['note']}"
    return f"Project {row['project_name']} ({row['executor']} for {row['receiver']}): {row['description'] or ''}{marks}"


def all_entries(db: sqlite3.Connection) -> list[tuple[str, str, str]]:
    tagged = tag_map(db)
    found = [("path", r["path"], entry_text("path", r, tagged.get(("path", r["path"]), [])))
             for r in db.execute("SELECT * FROM nexus_paths")]
    found += [("note", str(r["id"]), entry_text("note", r)) for r in db.execute("SELECT * FROM project_notes")]
    found += [("project", r["project_name"], entry_text("project", r, tagged.get(("project", r["project_name"]), [])))
              for r in db.execute("SELECT * FROM projects")]
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
def tagged_keys(db: sqlite3.Connection, tags: list[str]) -> set[tuple[str, str]]:
    """Entries carrying every given tag; a note counts when its project does."""
    wanted = [tag_name(t) for t in tags]
    keys = None
    for tag in wanted:
        found = {(r["source"], r["key"]) for r in
                 db.execute("SELECT source, key FROM tag_links WHERE tag=?", (tag,))}
        keys = found if keys is None else keys & found
    projects = {k for s, k in keys if s == "project"}
    keys |= {("note", str(r["id"])) for r in db.execute("SELECT id, project_name FROM project_notes")
             if r["project_name"] in projects}
    return keys


def search(db: sqlite3.Connection, query: str, limit: int = 10, sources=("path", "note", "project"),
           tags: list[str] = ()) -> list[dict]:
    words = [w for w in re.findall(r"[\w./-]+", query.lower()) if len(w) > 1] or [""]
    scores: dict[tuple[str, str], float] = {}
    texts = {}
    allowed = tagged_keys(db, list(tags)) if tags else None
    for source, key, text in all_entries(db):
        if source not in sources or (allowed is not None and (source, key) not in allowed):
            continue
        texts[(source, key)] = text
        lowered = text.lower()
        hits = sum(1 for w in words if w in lowered)
        if hits:
            scores[(source, key)] = hits / len(words)
    model = active_model()
    query_vector = vectors([query], query=True) if model and query.strip() else None
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


def path_hit(db, path: str, by: str) -> dict:
    """Count one hit for a recorded path that still exists; refresh its presence either way.

    A hit means an agent looked the path up and it was really there. Rows that
    stay at zero hits for a long time are candidates for retirement.
    """
    path = clean_path(path)
    if not db.execute("SELECT 1 FROM nexus_paths WHERE path=?", (path,)).fetchone():
        return {"path": path, "hit": False, "reason": "not recorded"}
    present, stamp = os.path.lexists(path), now()
    db.execute("UPDATE nexus_paths SET present=?, checked_at=?, hit_count=hit_count+?, "
               "last_hit_at=CASE WHEN ? THEN ? ELSE last_hit_at END, "
               "last_hit_by=CASE WHEN ? THEN ? ELSE last_hit_by END WHERE path=?",
               (int(present), stamp, int(present), int(present), stamp, int(present), by, path))
    row = db.execute("SELECT hit_count FROM nexus_paths WHERE path=?", (path,)).fetchone()
    return {"path": path, "hit": present, "hits": row["hit_count"],
            **({} if present else {"reason": "missing on disk; fix or remove the row"})}


def ago(stamp: str) -> str:
    minutes = int((datetime.now(timezone.utc) - datetime.fromisoformat(stamp)).total_seconds() // 60)
    return f"{minutes} min ago" if minutes < 120 else (
        f"{minutes // 60} h ago" if minutes < 48 * 60 else f"{minutes // 1440} days ago")


def project_touch(db, name: str, agent: str, together: bool = False) -> dict:
    """Record that someone is working on a project for `agent`.

    If a different agent worked on it within ACTIVE_HOURS, nothing is recorded
    and the result carries `conflict`, unless `together` says Noob authorized
    the two agents to share it.
    """
    row = db.execute("SELECT last_modified, modified_for FROM projects WHERE project_name=?",
                     (name,)).fetchone()
    if not row:
        raise ValueError(f"Unknown project: {name}")
    agent = require(agent, "--for", 80)
    previous, when = row["modified_for"], row["last_modified"]
    recent = when and datetime.fromisoformat(when) > datetime.now(timezone.utc) - timedelta(hours=ACTIVE_HOURS)
    if previous and previous.lower() != agent.lower() and recent and not together:
        return {"project": name, "conflict": True, "modified_for": previous, "last_modified": when,
                "message": (f"{name} is busy: work for {previous} was recorded {ago(when)}. Two agents "
                            f"should not work on one project at once. Tell {agent}, and ask Noob before "
                            f"continuing; once authorized, repeat with --together.")}
    db.execute("UPDATE projects SET last_modified=?, modified_for=? WHERE project_name=?",
               (now(), agent, name))
    return {"project": name, "conflict": False, "modified_for": agent, "last_modified": now(),
            "message": f"{name}: working for {agent}"
                       + (f" (before: {previous}, {ago(when)})" if previous and when else "")}


def note_add(db, project, text, paths, by, agent=None) -> dict:
    if not db.execute("SELECT 1 FROM projects WHERE project_name=?", (project,)).fetchone():
        raise ValueError(f"Unknown project: {project} (add it with `project add`)")
    cited = [clean_path(p) for p in paths]
    cursor = db.execute("INSERT INTO project_notes (project_name, author, note, paths, created_at) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (project, require(by, "--by", 80), require(text, "note", 6000),
                         json.dumps(cited), now()))
    # A note is work on the project: record it, and warn if another agent is active.
    activity = project_touch(db, project, agent or by)
    if activity["conflict"]:
        project_touch(db, project, agent or by, together=True)
    db.commit()
    refresh_embeddings(db, [("note", str(cursor.lastrowid))])
    note = dict(db.execute("SELECT * FROM project_notes WHERE id=?", (cursor.lastrowid,)).fetchone())
    return {**note, "warning": activity["message"]} if activity["conflict"] else note


def project_view(db, name: str, notes: int) -> dict:
    row = db.execute("SELECT * FROM projects WHERE project_name=?", (name,)).fetchone()
    if not row:
        raise ValueError(f"Unknown project: {name}")
    result = dict(row)
    result["tag_list"] = tag_map(db).get(("project", name), [])
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
    marks = "".join(f" #{t}" for t in value.get("tag_list", []))
    if "source" in value and "score" in value:
        return f"[{value['source']} {value['score']}] {value['text']}"
    if "name" in value and "uses" in value:
        return f"#{value['name']} ({value['uses']}): {value['description']}"
    if "conflict" in value and "message" in value:
        return ("BUSY: " if value["conflict"] else "") + value["message"]
    if "path" in value and "hit" in value:
        if value["hit"]:
            return f"hit {value['path']} (hits={value['hits']})"
        return f"no hit {value['path']}: {value['reason']}"
    if "path" in value and "kind" in value:
        mark = "" if value.get("present", 1) else " (MISSING)"
        meta = ", ".join(x for x in (value["kind"], value.get("owner") or "", value.get("project") or "",
                                     f"hits={value['hit_count']}" if "hit_count" in value else "") if x)
        return f"{value['path']}{mark} [{meta}] {value['description']}{marks}"
    if "note" in value:
        cited = json.loads(value["paths"]) if isinstance(value["paths"], str) else value["paths"]
        return (f"#{value['id']} {value['created_at'][:16]} {value['author']}: {value['note']}"
                + (f"\n    paths: {', '.join(cited)}" if cited else "")
                + (f"\nWARNING: {value['warning']}" if value.get("warning") else ""))
    if "project_name" in value:
        lines = [f"{value['project_name']} — {value['executor']} for {value['receiver']}"
                 f"{'' if value['hardware_ready'] else ' (hardware not ready)'}: {value['description'] or ''}{marks}"
                 + (f" [last worked on {ago(value['last_modified'])} for {value['modified_for']}]"
                    if value.get("last_modified") and value.get("modified_for") else "")]
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
    s.add_argument("query", nargs="*")
    s.add_argument("--limit", type=int, default=10)
    s.add_argument("--only", choices=("path", "note", "project"))
    s.add_argument("--tag", action="append", default=[], help="only entries with this tag (repeatable: all must match)")

    p = sub.add_parser("path", help="read or record a Nexus path")
    pa = p.add_subparsers(dest="action", required=True)
    pg = pa.add_parser("get", help="read one recorded path (counts a hit when it exists)")
    pg.add_argument("path")
    ph = pa.add_parser("hit", help="count a hit: you looked a path up and it was really there")
    ph.add_argument("path", nargs="+")
    ph.add_argument("--by", required=True, help="your name, e.g. Dushich")
    ps = pa.add_parser("set")
    ps.add_argument("path")
    ps.add_argument("--description", "-d", required=True)
    ps.add_argument("--kind", "-k", default="file", choices=KINDS)
    ps.add_argument("--owner", "-o")
    ps.add_argument("--keywords", "--tags", "-t", dest="keywords", default="",
                    help="free-text search words (not curated tags)")
    ps.add_argument("--project")
    ps.add_argument("--tag", action="append", default=[], help="attach a curated tag (repeatable)")
    ps.add_argument("--by", required=True, help="your name, e.g. Dushich")
    pr = pa.add_parser("remove")
    pr.add_argument("path")
    pr.add_argument("--by", required=True)
    pl = pa.add_parser("list")
    pl.add_argument("--prefix", default="/")
    pl.add_argument("--limit", type=int, default=200)
    pl.add_argument("--sort", choices=("path", "hits"), default="path",
                    help="hits: least-hit first, oldest last hit first (retirement candidates)")
    pc = pa.add_parser("check", help="re-check that recorded paths exist")
    pc.add_argument("--prefix", default="/")

    j = sub.add_parser("project", help="read, add, or track work on projects")
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
    jn.add_argument("--tag", action="append", default=[], help="attach a curated tag (repeatable)")
    jn.add_argument("--by", default="forge-db", help="your name")
    js = ja.add_parser("set", help="update a project's description or hardware readiness")
    js.add_argument("name")
    hw = js.add_mutually_exclusive_group()
    hw.add_argument("--hardware-ready", dest="hardware_ready", action="store_true", default=None,
                    help="the project's hardware exists and works")
    hw.add_argument("--no-hardware-ready", dest="hardware_ready", action="store_false", default=None,
                    help="the project's hardware is not ready yet")
    js.add_argument("--description", "-d", help="replace the project description")
    js.add_argument("--by", required=True)
    jt = ja.add_parser("touch", help="record that you are working on a project for an agent; "
                                     f"exit 3 if another agent worked on it in the last {ACTIVE_HOURS} h")
    jt.add_argument("name")
    jt.add_argument("--for", dest="agent", required=True, help="the agent the work is for, e.g. Gwyn")
    jt.add_argument("--together", action="store_true", help="Noob authorized sharing the project")
    jt.add_argument("--by", required=True)
    jr = ja.add_parser("remove", help="delete a project, its tag links, and (with --with-notes) its notes")
    jr.add_argument("name")
    jr.add_argument("--with-notes", action="store_true")
    jr.add_argument("--by", required=True)

    t = sub.add_parser("tag", help="curated tags for paths and projects")
    ta = t.add_subparsers(dest="action", required=True)
    ta.add_parser("list")
    td = ta.add_parser("add", help="define a tag or update its description")
    td.add_argument("name")
    td.add_argument("--description", "-d", required=True)
    td.add_argument("--by", required=True)
    for verb in ("attach", "detach"):
        tv = ta.add_parser(verb)
        tv.add_argument("name")
        tv.add_argument("--path", action="append", default=[])
        tv.add_argument("--project", action="append", default=[])
        tv.add_argument("--by", required=True)
    ta.add_parser("show", help="everything carrying a tag").add_argument("name")
    tr = ta.add_parser("remove", help="delete a tag and all its links")
    tr.add_argument("name")
    tr.add_argument("--by", required=True)

    n = sub.add_parser("note", help="read or add project notes")
    na = n.add_subparsers(dest="action", required=True)
    nn = na.add_parser("add")
    nn.add_argument("project")
    nn.add_argument("text")
    nn.add_argument("--path", action="append", default=[])
    nn.add_argument("--for", dest="agent", help="the agent the work was for (default: --by)")
    nn.add_argument("--by", required=True)
    nl = na.add_parser("list")
    nl.add_argument("project")
    nl.add_argument("--limit", type=int, default=20)

    c = sub.add_parser("changes", help="rows written since a UTC ISO time")
    c.add_argument("--since", required=True)
    sub.add_parser("embed", help="refresh meaning-search vectors")
    sub.add_parser("stats")

    args = parser.parse_args(argv)
    db = None
    failed = False
    code = 0
    try:
        db = connect()
        if args.cmd == "search":
            sources = (args.only,) if args.only else ("path", "note", "project")
            if not args.query and not args.tag:
                raise ValueError("Give search words, --tag, or both")
            result = search(db, " ".join(args.query), args.limit if args.query else 500, sources, args.tag)
        elif args.cmd == "path" and args.action == "get":
            path = clean_path(args.path)
            row = db.execute("SELECT * FROM nexus_paths WHERE path=?", (path,)).fetchone()
            if not row:
                raise ValueError("Path is not recorded; try `forge-db search`")
            path_hit(db, path, "(path get)")
            db.commit()
            row = db.execute("SELECT * FROM nexus_paths WHERE path=?", (path,)).fetchone()
            result = {**dict(row), "tag_list": tag_map(db).get(("path", path), [])}
        elif args.cmd == "path" and args.action == "hit":
            by = require(args.by, "--by", 80)
            result = [path_hit(db, p, by) for p in args.path]
            db.commit()
            failed = not all(r["hit"] for r in result)
        elif args.cmd == "path" and args.action == "set":
            for tag in args.tag:  # validate before writing anything
                if not db.execute("SELECT 1 FROM tags WHERE name=?", (tag_name(tag),)).fetchone():
                    raise ValueError(f"Unknown tag {tag_name(tag)}; define it with `forge-db tag add`")
            result = path_set(db, args.path, args.description, args.kind, args.owner,
                              args.keywords, args.project, args.by)
            for tag in args.tag:
                tag_attach(db, tag, "path", [result["path"]], args.by)
            result["tag_list"] = tag_map(db).get(("path", result["path"]), [])
        elif args.cmd == "path" and args.action == "remove":
            require(args.by, "--by")
            path = clean_path(args.path)
            deleted = db.execute("DELETE FROM nexus_paths WHERE path=?", (path,)).rowcount
            db.execute("DELETE FROM tag_links WHERE source='path' AND key=?", (path,))
            db.commit()
            refresh_embeddings(db, [])
            result = f"removed {deleted} row(s)"
        elif args.cmd == "path" and args.action == "list":
            prefix = clean_path(args.prefix)
            order = "hit_count, last_hit_at IS NOT NULL, last_hit_at, path" if args.sort == "hits" else "path"
            result = [dict(r) for r in db.execute(
                f"SELECT * FROM nexus_paths WHERE path=? OR path LIKE ? ORDER BY {order} LIMIT ?",
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
                       "hardware_ready, agentic_tools, last_modified, modified_for) "
                       "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       (require(args.name, "name", 80), args.executor, args.receiver,
                        require(args.description, "description"), int(args.hardware_ready),
                        json.dumps(["forge-db"]), now(), args.executor))
            for tag in args.tag:
                tag_attach(db, tag, "project", [args.name], args.by, commit=False)
            db.commit()
            refresh_embeddings(db, [("project", args.name)])
            result = project_view(db, args.name, 0)
        elif args.cmd == "project" and args.action == "set":
            require(args.by, "--by", 80)
            if args.hardware_ready is None and not args.description:
                raise ValueError("Nothing to set: pass --hardware-ready, --no-hardware-ready, or --description")
            if not db.execute("SELECT 1 FROM projects WHERE project_name=?", (args.name,)).fetchone():
                raise ValueError(f"Unknown project: {args.name}")
            if args.hardware_ready is not None:
                db.execute("UPDATE projects SET hardware_ready=? WHERE project_name=?",
                           (int(args.hardware_ready), args.name))
            if args.description:
                db.execute("UPDATE projects SET description=? WHERE project_name=?",
                           (require(args.description, "--description"), args.name))
            db.commit()
            refresh_embeddings(db, [("project", args.name)])
            result = project_view(db, args.name, 0)
        elif args.cmd == "project" and args.action == "touch":
            require(args.by, "--by", 80)
            result = project_touch(db, args.name, args.agent, args.together)
            db.commit()
            code = 3 if result["conflict"] else 0
        elif args.cmd == "project" and args.action == "remove":
            require(args.by, "--by", 80)
            if not db.execute("SELECT 1 FROM projects WHERE project_name=?", (args.name,)).fetchone():
                raise ValueError(f"Unknown project: {args.name}")
            notes = db.execute("SELECT COUNT(*) FROM project_notes WHERE project_name=?",
                               (args.name,)).fetchone()[0]
            if notes and not args.with_notes:
                raise ValueError(f"{args.name} has {notes} note(s); add --with-notes to delete them too")
            db.execute("DELETE FROM project_notes WHERE project_name=?", (args.name,))
            db.execute("DELETE FROM tag_links WHERE source='project' AND key=?", (args.name,))
            db.execute("UPDATE nexus_paths SET project=NULL WHERE project=?", (args.name,))
            db.execute("DELETE FROM projects WHERE project_name=?", (args.name,))
            db.commit()
            refresh_embeddings(db)
            result = f"removed project {args.name} and {notes} note(s)"
        elif args.cmd == "tag" and args.action == "list":
            result = [dict(r) for r in db.execute(
                "SELECT t.name, t.description, COUNT(l.tag) AS uses FROM tags t "
                "LEFT JOIN tag_links l ON l.tag = t.name GROUP BY t.name ORDER BY uses DESC, t.name")]
        elif args.cmd == "tag" and args.action == "add":
            name = tag_name(args.name)
            db.execute("INSERT INTO tags VALUES (?, ?, ?, ?) ON CONFLICT(name) DO UPDATE SET "
                       "description=excluded.description",
                       (name, require(args.description, "description", 300), require(args.by, "--by", 80), now()))
            db.commit()
            result = f"tag #{name} defined"
        elif args.cmd == "tag" and args.action in ("attach", "detach"):
            if not args.path and not args.project:
                raise ValueError("Give at least one --path or --project")
            if args.action == "attach":
                added = (tag_attach(db, args.name, "path", args.path, args.by, commit=False)
                         + tag_attach(db, args.name, "project", args.project, args.by, commit=False))
                db.commit()
                result = f"#{tag_name(args.name)} attached to {added} new item(s)"
            else:
                require(args.by, "--by")
                name = tag_name(args.name)
                removed = sum(db.execute("DELETE FROM tag_links WHERE source=? AND key=? AND tag=?",
                                         (source, clean_path(k) if source == "path" else k, name)).rowcount
                              for source, keys in (("path", args.path), ("project", args.project)) for k in keys)
                db.commit()
                result = f"#{name} detached from {removed} item(s)"
            refresh_embeddings(db, [("path", clean_path(p)) for p in args.path]
                               + [("project", p) for p in args.project])
        elif args.cmd == "tag" and args.action == "show":
            name = tag_name(args.name)
            row = db.execute("SELECT * FROM tags WHERE name=?", (name,)).fetchone()
            if not row:
                raise ValueError(f"Unknown tag {name}")
            tagged = tag_map(db)
            result = [f"#{name}: {row['description']}"]
            result += [render({**dict(r), "tag_list": tagged.get(("project", r["project_name"]), [])})
                       for r in db.execute("SELECT p.* FROM projects p JOIN tag_links l ON l.source='project' "
                                           "AND l.key=p.project_name WHERE l.tag=? ORDER BY 1", (name,))]
            result += [render({**dict(r), "tag_list": tagged.get(("path", r["path"]), [])})
                       for r in db.execute("SELECT n.* FROM nexus_paths n JOIN tag_links l ON l.source='path' "
                                           "AND l.key=n.path WHERE l.tag=? ORDER BY 1", (name,))]
            if args.json:
                result = {"tag": dict(row), "items": result[1:]}
        elif args.cmd == "tag" and args.action == "remove":
            require(args.by, "--by")
            name = tag_name(args.name)
            links = db.execute("DELETE FROM tag_links WHERE tag=?", (name,)).rowcount
            removed = db.execute("DELETE FROM tags WHERE name=?", (name,)).rowcount
            db.commit()
            refresh_embeddings(db)
            result = f"removed tag #{name} ({removed} definition, {links} link(s))"
        elif args.cmd == "note" and args.action == "add":
            result = note_add(db, args.project, args.text, args.path, args.by, args.agent)
        elif args.cmd == "note" and args.action == "list":
            result = [dict(r) for r in db.execute(
                "SELECT * FROM (SELECT * FROM project_notes WHERE project_name=? ORDER BY id DESC LIMIT ?) "
                "ORDER BY id", (args.project, args.limit))]
        elif args.cmd == "changes":
            result = {"paths": [dict(r) for r in db.execute(
                          "SELECT * FROM nexus_paths WHERE updated_at>=? ORDER BY updated_at", (args.since,))],
                      "projects": [dict(r) for r in db.execute(
                          "SELECT * FROM projects WHERE last_modified>=? ORDER BY last_modified", (args.since,))],
                      "notes": [dict(r) for r in db.execute(
                          "SELECT * FROM project_notes WHERE created_at>=? ORDER BY id", (args.since,))]}
            if not args.json:
                result = result["projects"] + result["paths"] + result["notes"]
        elif args.cmd == "embed":
            changed = refresh_embeddings(db)
            result = (f"refreshed {changed} vector(s) with {active_model()}" if active_model()
                      else "meaning search unavailable: build it with common/runtime/install.sh forge")
        else:
            counts = {t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                      for t in ("projects", "nexus_paths", "project_notes", "tags", "tag_links", "embeddings")}
            result = {**counts, "db": str(DB), "meaning_model": active_model()}
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(f"forge-db: {exc}", file=sys.stderr)
        return 2
    finally:
        if db is not None:
            db.close()
    print(json.dumps(result, indent=1, default=str) if args.json else render(result))
    return 1 if failed else code


if __name__ == "__main__":
    sys.exit(main())
