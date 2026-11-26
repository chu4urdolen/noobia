# Argus historian evidence index

`tools/argus_history.py` is a local, on-demand evidence index for Argus's existing `/noobia/archive/events/YYYY/*.jsonl` files. It is deployed on his Pi at `/noobia/argus/tools/argus_history.py`. The SQLite database lives on his NVMe root at `/noobia/argus/data/history.sqlite3` (private directory 0700, database 0600). It neither edits nor deletes the original archive.

```sh
python3 /noobia/argus/tools/argus_history.py init
python3 /noobia/argus/tools/argus_history.py import-archive
python3 /noobia/argus/tools/argus_history.py status
python3 /noobia/argus/tools/argus_history.py events-on 2026-08-19 --limit 20
python3 /noobia/argus/tools/argus_history.py find Argus --limit 20
```

Output is bounded JSON, except failures, which print an error and exit nonzero. `events-on` selects only events with an explicit day. A missing or imprecise event date is retained but is never silently converted from `recorded_at`. `find` searches event ID, title, summary, and participants. Results include the first source path and line, record ID, and SHA-256 of the original line.

The database retains every distinct file version as raw bytes with its SHA-256 and UTC capture time. It retains each distinct source line and parsed event without overwriting earlier versions. Reimporting unchanged files adds nothing. A changed line creates another version under the same event ID; both remain queryable. A malformed file is rejected before any of that file is written, and symlinks outside the archive are rejected. The schema has `PRAGMA user_version=2`.

On 2026-11-26 the Pi imported three existing event files: 3 snapshots and 11 records. An immediate repeat import added zero snapshots and zero records; the original archive Git worktree remained clean. Local tests exercise repeat import, version retention, exact source bytes, uncertain dates, malformed input, and path escape rejection.

The coding Noobs' journals remain in their own directories. A brief journal collection trial on 2026-11-26 was reversed at Noob's request: all three captured hashes matched the owners' current files, the duplicate snapshots were removed from Argus's database, and the transfer commands were removed. Journal collection is deferred until the coding Noobs have their continuity features.

## Forge evidence and daily ledger

`argus_forge_sync.py` runs on Nexus. It requests a full, JSON export through `forge-db --json changes --include-archived`, validates and hashes the bytes, and transfers them over pinned SSH. The inclusive flag returns moved archived notes with their original fields and IDs. Argus retains each exact export and each distinct source row version. The full export avoids gaps from a timestamp cursor while the feed is small; the 5 MiB validation bound will require a paginated feed as Forge grows.

`build-ledger DATE` stores a versioned evidence ledger for a Europe/Sofia day. It separates date-only Argus archive events from timed Forge notes and cites source IDs and hashes. It makes no unsupported event-time inference from Forge path or project update times. Repeating unchanged evidence reuses the version; changed evidence produces another. A ledger is an evidence chronology, not an independent fact check or prose synthesis.

```sh
python3 /noobia/argus/tools/argus_forge_sync.py        # Nexus
python3 /noobia/argus/tools/argus_client.py collect-day --date 2026-11-26
python3 /noobia/argus/tools/argus_client.py job-result JOB_ID
python3 /noobia/argus/tools/argus_client.py ledger 2026-11-26
```

The Nexus `noobia` MCP server exposes `argus_status`, `argus_collect_day`, `argus_daily_ledger`, `argus_job_status`, `argus_job_result`, `argus_events_on`, `argus_find_events`, `argus_forge_notes_on`, and `argus_source_record`. The three search tools return source-backed historical records in pages of at most 100, with `next_offset` when more are available; Forge notes can be filtered by exact project or actor. `argus_source_record` retrieves an exact cited archive line (base64) or Forge row by its key and SHA-256. `argus_collect_day` transfers the Forge feed and queues archive import followed by ledger construction; its returned ledger job ID is polled separately. The route uses local MCP stdio plus pinned SSH to the Pi; no Argus LAN listener is opened. Journals remain paused, and Council is out of scope.

On 2026-11-26, the inclusive Forge export contained 1,016 source rows, including 572 notes. A real collection request completed both jobs, with no duplicate archive records, and reused the 2026-11-26 ledger version 2 (24 Forge notes). The local Argus and Forge tests passed. There is no automatic schedule or narrative synthesis yet.

## Off-device recovery

`argus_backup.py create` streams consistent SQLite snapshots, the original Argus archive, and a station packet to `/noobia/argus/private/backups/` on Nexus. The station packet includes Argus's current role and root instructions, the shared instructions, launcher, installed worker unit, HDMI desktop settings, and the exact Pi wallpaper image. Each immutable dated directory has a SHA-256 manifest. `verify FOLDER` checks hashes and both SQLite databases, then restores the archived event files into a temporary database and reimports them; it also checks the station packet's required files. Older backups without the station packet remain verifiable. On 2026-11-27, the newest backup verified three archive event files, 11 restored records, both SQLite databases, and seven station files. This protects the original archive separately from the old `rsync --delete` mirror. It is manual; no retention deletion or automatic backup timer has been added.
