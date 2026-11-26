# Argus's first historical index

`tools/argus_history.py` is a local, on-demand evidence index for Argus's existing `/noobia/archive/events/YYYY/*.jsonl` files. It is deployed on his Pi at `/noobia/argus/tools/argus_history.py`. The SQLite database lives on his NVMe root at `/noobia/argus/data/history.sqlite3` (private directory 0700, database 0600). It neither edits nor deletes the original archive.

```sh
python3 /noobia/argus/tools/argus_history.py init
python3 /noobia/argus/tools/argus_history.py import-archive
python3 /noobia/argus/tools/argus_history.py status
python3 /noobia/argus/tools/argus_history.py events-on 2026-08-19 --limit 20
python3 /noobia/argus/tools/argus_history.py find Argus --limit 20
```

Output is bounded JSON, except failures, which print an error and exit nonzero. `events-on` selects only events with an explicit day. A missing or imprecise event date is retained but is never silently converted from `recorded_at`. `find` searches event ID, title, summary, and participants. Results include the first source path and line, record ID, and SHA-256 of the original line.

The database retains every distinct file version as raw bytes with its SHA-256 and UTC capture time. It retains each distinct source line and parsed event without overwriting earlier versions. Reimporting unchanged files adds nothing. A changed line creates another version under the same event ID; both remain queryable. A malformed file is rejected before any of that file is written, and symlinks outside the archive are rejected. The schema has `PRAGMA user_version=1`.

On 2026-11-26 the Pi imported three existing event files: 3 snapshots and 11 records. An immediate repeat import added zero snapshots and zero records; the original archive Git worktree remained clean. Local tests exercise repeat import, version retention, exact source bytes, uncertain dates, malformed input, and path escape rejection.

The coding Noobs' journals remain in their own directories. A brief journal collection trial on 2026-11-26 was reversed at Noob's request: all three captured hashes matched the owners' current files, the duplicate snapshots were removed from Argus's database, and the transfer commands were removed. Journal collection is deferred until the coding Noobs have their continuity features.

This component indexes only Argus's own existing event archive. It has no journal or Forge feed, daily synthesis, background schedule, MCP ingress, off-device backup, or restore test yet. The index can be rebuilt from Argus's original archive, but that archive itself still needs verified off-device protection.
