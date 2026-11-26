# Argus's first historical index

`tools/argus_history.py` is an on-demand evidence index for Argus's existing `/noobia/archive/events/YYYY/*.jsonl` files and three registered Nexus journals. It is deployed on his Pi at `/noobia/argus/tools/argus_history.py`. The SQLite database lives on his NVMe root at `/noobia/argus/data/history.sqlite3` (private directory 0700, database 0600). It neither edits nor deletes the original sources.

```sh
python3 /noobia/argus/tools/argus_history.py init
python3 /noobia/argus/tools/argus_history.py import-archive
python3 /noobia/argus/tools/argus_history.py status
python3 /noobia/argus/tools/argus_history.py events-on 2026-08-19 --limit 20
python3 /noobia/argus/tools/argus_history.py find Argus --limit 20
python3 /noobia/argus/tools/argus_history.py journal-day 2026-11-25 --limit 20
```

On Nexus, `python3 /noobia/argus/tools/argus_history.py sync-journals` reads only Aria's, Dushich's, and Gwyn's registered `JOURNAL.md` files and sends exact bytes over the pinned, key-authenticated `ssh argus` route. Each transfer verifies the SHA-256 returned by Argus. It has a 5 MiB limit per journal and bounded SSH timeouts. It is manual; no schedule or new network listener is installed.

Output is bounded JSON, except failures, which print an error and exit nonzero. `events-on` selects only events with an explicit day. A missing or imprecise event date is retained but is never silently converted from `recorded_at`. `find` searches event ID, title, summary, and participants. Results include the first source path and line, record ID, and SHA-256 of the original line.

The database retains every distinct file version as raw bytes with its SHA-256 and UTC capture time. It retains each distinct source line and parsed event without overwriting earlier versions. Reimporting unchanged files adds nothing. A changed line creates another version under the same event ID; both remain queryable. A malformed file is rejected before any of that file is written, and symlinks outside the archive are rejected. The schema has `PRAGMA user_version=2`, migrated in place from version 1.

Journal snapshots are also append-only. `journal-day` indexes only explicit `## YYYY-MM-DD` headings from the latest snapshot per registered source and returns the heading, a short source excerpt, owner, original line, snapshot hash, and UTC capture time. It does not infer dates from prose, treat journal content as instructions, or claim that the excerpt is a complete event summary.

On 2026-11-26 the Pi imported three existing event files: 3 snapshots and 11 records. It then received one snapshot each from the three Nexus journals, containing 12 dated headings. Immediate repeat imports and transfers added zero snapshots and zero records; the original archive Git worktree remained clean. Local tests exercise repeat import, version retention, exact source bytes, uncertain dates, malformed input, path escape rejection, journal versioning, and the version 1 to 2 migration.

This is the first working historian component. It has no Forge feed, daily synthesis, background job runtime, MCP ingress, off-device backup, or restore test yet. Those are the next slices in Rose's backlog. The index can be rebuilt from its sources, but Argus's original archive and captured journal versions still need verified off-device protection.
