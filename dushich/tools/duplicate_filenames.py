#!/usr/bin/env python3
"""duplicate_filenames -- report duplicate file basenames under a directory tree.

This tool scans a directory tree and groups *regular* files by their basename
(the file name without any directory components), ignoring file contents.  A
basename collision means the same file name appears in two or more locations.

Behaviour:
  * Only regular files are counted (``S_ISREG`` on ``lstat``), so symlinks,
    devices and other special files are excluded.
  * ``.git`` and ``.dushich-git`` directories and symlinked directories are not traversed.
  * Permission and other OS errors encountered while walking are recorded in
    the report instead of aborting the scan.
  * The report is deterministic and fully sorted.

The CLI runs the scan as a detached background job so the caller never blocks
on a (possibly large) walk:

  duplicate_filenames.py start [root] [--dir STATE_DIR]
  duplicate_filenames.py status <job-id> [--dir STATE_DIR]
  duplicate_filenames.py result <job-id> [--dir STATE_DIR] [--max N]

  start   create a job, launch a detached worker, print the job id and exit
          immediately (non-blocking).
  status  print a single bounded plain-text status line (non-blocking).
  result  print a bounded plain-text summary of the completed report
          (non-blocking; reads the current state).

Job state and reports are stored under a private (mode 0700) state directory
with 0600 files.  Only the Python standard library is used.

Exit codes:
  0  success (job present; for ``result`` the job completed)
  1  job not found
  2  ``result`` requested but job not yet completed (pending/running)
  3  ``result`` requested but job failed

Testing hook:
  The environment variable ``DUPLICATE_NAMES_TEST_WORKER_DELAY`` (seconds)
  makes the worker sleep before scanning.  It exists only so tests can
  deterministically prove the CLI does not block on the scan; it has no
  effect unless explicitly set.
"""

import argparse
import json
import os
import stat as statmod
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone

DEFAULT_MAX_GROUPS = 20
DEFAULT_MAX_PATHS = 8

#: Name of the testing hook that makes the worker delay before scanning.
TEST_WORKER_DELAY_ENV = "DUPLICATE_NAMES_TEST_WORKER_DELAY"
#: Environment variable that can override the default state directory.
STATE_DIR_ENV = "DUPLICATE_NAMES_STATE_DIR"


def utc_now():
    """Return the current UTC time as a stable, sortable ISO-8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def default_state_dir():
    """Return the default private state directory path.

    Resolution order:
      1. ``DUPLICATE_NAMES_STATE_DIR`` environment variable, if set.
      2. ``$XDG_DATA_HOME/duplicate_names`` when ``XDG_DATA_HOME`` is set.
      3. ``/noobia/dushich/private/duplicate-reports``.
    """
    override = os.environ.get(STATE_DIR_ENV)
    if override:
        return os.path.abspath(override)
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return os.path.join(xdg, "duplicate_names")
    return "/noobia/dushich/private/duplicate-reports"


def ensure_private_dir(path):
    """Create *path* (and parents) and force it to mode 0700."""
    os.makedirs(path, exist_ok=True)
    os.chmod(path, 0o700)
    return path


def write_private_json(path, obj):
    """Atomically write *obj* as pretty JSON to *path* with mode 0600.

    The file is written to a temporary name in the same directory and then
    moved into place with ``os.replace`` so readers never observe a partial
    file.
    """
    directory = os.path.dirname(path) or "."
    ensure_private_dir(directory)
    data = json.dumps(obj, indent=2, sort_keys=True) + "\n"
    tmp = "%s.tmp.%d" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def read_json(path):
    """Read and parse a JSON file."""
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def jobs_dir(state_dir):
    return os.path.join(state_dir, "jobs")


def reports_dir(state_dir):
    return os.path.join(state_dir, "reports")


def job_path(state_dir, job_id):
    return os.path.join(jobs_dir(state_dir), job_id + ".json")


def report_path(state_dir, job_id):
    return os.path.join(reports_dir(state_dir), job_id + ".json")


def new_job_record(job_id, root):
    """Return a fresh job record with status ``pending``."""
    now = utc_now()
    return {
        "job_id": job_id,
        "root": os.path.abspath(root),
        "status": "pending",
        "created_at": now,
        "started_at": None,
        "finished_at": None,
        "scanned_files": None,
        "unique_basenames": None,
        "duplicate_basenames": None,
        "permission_error_count": None,
        "report": None,
        "error": None,
    }


def scan_tree(root):
    """Walk *root* and group regular files by basename.

    Returns a tuple ``(groups, errors, scanned_files)`` where

      * ``groups`` is a dict mapping basename -> sorted list of absolute paths,
      * ``errors`` is a list (sorted by path) of permission/OS error records,
      * ``scanned_files`` is the number of regular files examined.

    Git metadata directories and symlinked directories are not traversed, and only
    regular files (per ``lstat``) are counted.
    """
    root = os.path.abspath(root)
    errors = []
    groups = {}
    scanned = 0

    def record_error(exc, path):
        errors.append({
            "path": path if path is not None else root,
            "error": "%s: %s" % (exc.__class__.__name__, exc),
            "errno": getattr(exc, "errno", None),
        })

    def onerror(exc):
        record_error(exc, getattr(exc, "filename", None))

    for dirpath, dirnames, filenames in os.walk(root, onerror=onerror, followlinks=False):
        # Prune ``.git`` and symlinked directories so they are never traversed.
        kept = []
        for name in dirnames:
            if name in {".git", ".dushich-git"}:
                continue
            full = os.path.join(dirpath, name)
            try:
                if os.path.islink(full):
                    continue
            except OSError:
                continue
            kept.append(name)
        dirnames[:] = kept

        for name in filenames:
            full = os.path.join(dirpath, name)
            try:
                st = os.lstat(full)
            except OSError as exc:
                record_error(exc, full)
                continue
            if not statmod.S_ISREG(st.st_mode):
                # Symlinks, sockets, fifos, devices, etc. are not regular files.
                continue
            scanned += 1
            groups.setdefault(name, []).append(full)

    for name in groups:
        groups[name].sort()
    errors.sort(key=lambda e: (e["path"], e["error"]))
    return groups, errors, scanned


def build_report(root, groups, errors, scanned_files):
    """Assemble the sorted report dictionary from scan results."""
    duplicates = {name: paths for name, paths in groups.items() if len(paths) >= 2}
    return {
        "root": os.path.abspath(root),
        "generated_at": utc_now(),
        "scanned_files": scanned_files,
        "unique_basenames": len(groups),
        "duplicate_basenames": len(duplicates),
        "permission_errors": errors,
        "duplicates": duplicates,
    }


def run_worker(state_dir, job_id):
    """Perform the scan for *job_id* and finalise the job record.

    Runs inside the detached worker process.  Updates the job status through
    ``running`` and then ``completed`` (or ``failed`` on error).
    """
    jp = job_path(state_dir, job_id)
    record = read_json(jp)
    record["status"] = "running"
    record["started_at"] = utc_now()
    write_private_json(jp, record)

    # Testing hook: allow a deterministic delay so tests can prove the CLI does
    # not block on the scan.  Inactive unless the variable is explicitly set.
    delay = os.environ.get(TEST_WORKER_DELAY_ENV)
    if delay:
        try:
            time.sleep(float(delay))
        except ValueError:
            pass

    root = record["root"]
    if not os.path.isdir(root):
        raise FileNotFoundError("root directory does not exist: %s" % root)

    groups, errors, scanned = scan_tree(root)
    report = build_report(root, groups, errors, scanned)
    rp = report_path(state_dir, job_id)
    write_private_json(rp, report)

    record["status"] = "completed"
    record["finished_at"] = utc_now()
    record["scanned_files"] = scanned
    record["unique_basenames"] = report["unique_basenames"]
    record["duplicate_basenames"] = report["duplicate_basenames"]
    record["permission_error_count"] = len(errors)
    record["report"] = rp
    record["error"] = None
    write_private_json(jp, record)
    return 0


def cmd_worker(args):
    state_dir = resolve_state_dir(args.dir)
    try:
        return run_worker(state_dir, args.job_id)
    except Exception as exc:  # noqa: BLE001 - report any failure on the job
        jp = job_path(state_dir, args.job_id)
        try:
            record = read_json(jp)
        except (OSError, ValueError):
            record = new_job_record(args.job_id, "")
        record["status"] = "failed"
        record["error"] = "%s: %s" % (exc.__class__.__name__, exc)
        record["finished_at"] = utc_now()
        try:
            write_private_json(jp, record)
        except OSError:
            pass
        return 3


def cmd_start(args):
    state_dir = resolve_state_dir(args.dir)
    ensure_private_dir(state_dir)
    root = os.path.abspath(args.root)
    job_id = uuid.uuid4().hex[:12]
    record = new_job_record(job_id, root)
    jp = job_path(state_dir, job_id)
    write_private_json(jp, record)

    module = os.path.abspath(__file__)
    cmd = [sys.executable, module, "_worker", job_id, "--dir", state_dir]
    try:
        subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
            cwd=os.path.dirname(module),
        )
    except OSError as exc:
        record["status"] = "failed"
        record["error"] = "failed to launch worker: %s" % exc
        record["finished_at"] = utc_now()
        write_private_json(jp, record)
        sys.stderr.write("error: %s\n" % exc)
        return 1

    sys.stdout.write(job_id + "\n")
    return 0


def cmd_status(args):
    state_dir = resolve_state_dir(args.dir)
    jp = job_path(state_dir, args.job_id)
    if not os.path.isfile(jp):
        sys.stdout.write("job=%s not-found\n" % args.job_id)
        return 1
    record = read_json(jp)
    line = (
        "job=%s status=%s root=%s files=%s unique=%s duplicates=%s errors=%s"
        % (
            record["job_id"],
            record["status"],
            record.get("root"),
            record.get("scanned_files"),
            record.get("unique_basenames"),
            record.get("duplicate_basenames"),
            record.get("permission_error_count"),
        )
    )
    if record.get("error"):
        line += " error=" + record["error"]
    sys.stdout.write(line + "\n")
    # ``status`` is for polling: 0 whenever the job is known, 1 if not found.
    return 0


def cmd_result(args):
    state_dir = resolve_state_dir(args.dir)
    jp = job_path(state_dir, args.job_id)
    if not os.path.isfile(jp):
        sys.stdout.write("job=%s not-found\n" % args.job_id)
        return 1
    record = read_json(jp)

    out = [
        "job=%s status=%s root=%s"
        % (record["job_id"], record["status"], record.get("root"))
    ]

    if record["status"] != "completed":
        if record.get("error"):
            out.append("error=" + record["error"])
        out.append("result not available yet (status=%s)" % record["status"])
        sys.stdout.write("\n".join(out) + "\n")
        return 3 if record["status"] == "failed" else 2

    out.append(
        "files=%s unique=%s duplicates=%s errors=%s"
        % (
            record.get("scanned_files"),
            record.get("unique_basenames"),
            record.get("duplicate_basenames"),
            record.get("permission_error_count"),
        )
    )

    rp = record.get("report")
    if rp and os.path.isfile(rp):
        report = read_json(rp)
        dups = report.get("duplicates", {})
        items = sorted(dups.items())
        max_groups = max(0, args.max)
        out.append("duplicates (%d total):" % len(items))
        if not items:
            out.append("  (none)")
        shown = 0
        for name, paths in items:
            if shown >= max_groups:
                out.append("  ... %d more (see report: %s)" % (len(items) - shown, rp))
                break
            out.append("  %s (%d):" % (name, len(paths)))
            for p in paths[:args.max_paths]:
                out.append("    - " + p)
            if len(paths) > args.max_paths:
                out.append("    ... %d more paths (see report)" %
                           (len(paths) - args.max_paths))
            shown += 1
        out.append("report=" + rp)
    else:
        out.append("report missing: %s" % rp)

    sys.stdout.write("\n".join(out) + "\n")
    return 0


def resolve_state_dir(cli_dir):
    return os.path.abspath(cli_dir) if cli_dir else default_state_dir()


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--dir",
        default=None,
        metavar="STATE_DIR",
        help="private state directory for job state and reports "
             "(default: %s)" % default_state_dir(),
    )

    parser = argparse.ArgumentParser(
        prog="duplicate_filenames",
        description="Report duplicate file basenames under a directory tree.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_start = sub.add_parser("start", parents=[common],
                             help="start a detached scan of ROOT and print a job id")
    p_start.add_argument("root", nargs="?", default="/noobia",
                         help="directory tree to scan (default: /noobia)")
    p_start.set_defaults(func=cmd_start)

    p_status = sub.add_parser("status", parents=[common],
                              help="print a bounded status line for JOB_ID")
    p_status.add_argument("job_id", help="job id returned by ``start``")
    p_status.set_defaults(func=cmd_status)

    p_result = sub.add_parser("result", parents=[common],
                              help="print a bounded result summary for JOB_ID")
    p_result.add_argument("job_id", help="job id returned by ``start``")
    p_result.add_argument(
        "--max", type=int, default=DEFAULT_MAX_GROUPS, metavar="N",
        help="maximum number of duplicate groups to print (default: %d)"
             % DEFAULT_MAX_GROUPS,
    )
    p_result.add_argument(
        "--max-paths", type=int, default=DEFAULT_MAX_PATHS, metavar="N",
        help="maximum paths shown in each group (default: %d)"
             % DEFAULT_MAX_PATHS,
    )
    p_result.set_defaults(func=cmd_result)

    p_worker = sub.add_parser("_worker", parents=[common],
                              help=argparse.SUPPRESS)
    p_worker.add_argument("job_id")
    p_worker.set_defaults(func=cmd_worker)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
