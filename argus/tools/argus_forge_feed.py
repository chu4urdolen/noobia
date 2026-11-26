"""Validate and normalize the public forge-db JSON changes feed."""

from datetime import datetime, timezone
import hashlib
import json


MAX_FEED_BYTES = 5 * 1024 * 1024
KINDS = ("paths", "projects", "notes")


def aware_utc(value, field):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field} must be an ISO timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must have a timezone")
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")


def required_text(row, field, kind):
    value = row.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{kind}.{field} must be nonempty text")
    return value


def normalize_row(kind, row):
    if not isinstance(row, dict):
        raise ValueError(f"{kind} row must be an object")
    if kind == "notes":
        source_id = row.get("id")
        if not isinstance(source_id, int) or isinstance(source_id, bool) or source_id < 1:
            raise ValueError("notes.id must be a positive integer")
        project = required_text(row, "project_name", kind)
        actor = required_text(row, "author", kind)
        occurred_at = aware_utc(row.get("created_at"), "notes.created_at")
        if occurred_at is None:
            raise ValueError("notes.created_at is required")
        observed_at = None
        stable_key = f"note:{source_id}"
    elif kind == "paths":
        source_id = required_text(row, "path", kind)
        if not source_id.startswith("/"):
            raise ValueError("paths.path must be absolute")
        project = row.get("project")
        actor = row.get("updated_by")
        occurred_at = None
        observed_at = aware_utc(row.get("updated_at"), "paths.updated_at")
        stable_key = "path:" + source_id
    else:
        source_id = required_text(row, "project_name", kind)
        project = source_id
        actor = row.get("modified_for")
        occurred_at = None
        observed_at = aware_utc(row.get("last_modified"), "projects.last_modified")
        stable_key = "project:" + source_id
    if project is not None and not isinstance(project, str):
        raise ValueError(f"{kind} project must be text or null")
    if actor is not None and not isinstance(actor, str):
        raise ValueError(f"{kind} actor must be text or null")
    canonical = json.dumps(row, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":")).encode("utf-8")
    return {
        "kind": kind[:-1] if kind != "paths" else "path",
        "source_id": str(source_id),
        "stable_key": stable_key,
        "content_sha256": hashlib.sha256(canonical).hexdigest(),
        "occurred_at": occurred_at,
        "observed_at": observed_at,
        "project": project,
        "actor": actor,
        "raw_record": row,
    }


def parse_feed(data):
    if not isinstance(data, bytes) or not data or len(data) > MAX_FEED_BYTES:
        raise ValueError("Forge feed must be 1 byte to 5 MiB")
    try:
        document = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Forge feed is not valid UTF-8 JSON") from error
    if not isinstance(document, dict) or set(document) != set(KINDS):
        raise ValueError("Forge feed must contain paths, projects, and notes")
    records = []
    seen = set()
    for kind in KINDS:
        rows = document[kind]
        if not isinstance(rows, list):
            raise ValueError(f"Forge {kind} must be a list")
        for row in rows:
            record = normalize_row(kind, row)
            if record["stable_key"] in seen:
                raise ValueError(f"duplicate Forge source ID: {record['stable_key']}")
            seen.add(record["stable_key"])
            records.append(record)
    return hashlib.sha256(data).hexdigest(), records
