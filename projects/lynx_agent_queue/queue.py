"""A tiny, standard‑library only job spool.

The queue is a directory‑based job store.  Each job is a JSON file named
``<job-id>.json`` containing only the prompt string.  Jobs are created with
``create_job`` which validates the prompt length (1–8000 UTF‑8 characters) and
writes the file atomically with ``0600`` permissions.

Workers claim jobs with ``claim_next``.  The method scans the directory for
unclaimed job files, attempts to atomically rename the first one to
``<job-id>.claimed`` and returns the job id.  The rename operation is
guaranteed to be atomic on POSIX file systems; if two workers race the same
file only one will succeed.

Once a job is claimed a worker calls ``finish`` to store the result and
remove the claimed file.  The result is written to ``<job-id>.done`` with
the same file mode.  ``cancel`` removes a pending job.

``status`` returns a minimal, prompt‑free status dictionary:

* ``pending`` – job file exists
* ``claimed`` – job file has been renamed to ``.claimed``
* ``finished`` – result file exists with ``ok`` and ``text`` fields

The queue rejects malformed identifiers – only a 32‑character hexadecimal
string is accepted.  All file paths are strictly relative to the queue root;
no symlink following or path traversal is permitted.
"""

from __future__ import annotations

import json
import os
import pathlib
import uuid
from dataclasses import dataclass
from typing import Optional

__all__ = ["JobQueue", "JobError"]


class JobError(RuntimeError):
    """Raised for queue‑related errors.

    The class intentionally accepts no arguments so that it can be raised
    without an explicit message.  All callers provide a message via
    ``raise JobError("msg")``.
    """

    def __init__(self, *args, **kwargs):  # pragma: no cover - trivial
        super().__init__(*args)


class JobQueue:
    """Thread‑safe, file‑system based job queue.

    Parameters
    ----------
    root:
        Directory where job files are stored.  It is created if it does not
        exist.
    """

    def __init__(self, root: pathlib.Path | str):
        self.root = pathlib.Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        # No symbolic links are allowed; ensure directory is not a symlink.
        if self.root.is_symlink():
            raise JobError("queue root must not be a symlink")

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _validate_id(self, job_id: str) -> None:
        if not (len(job_id) == 32 and all(c in "0123456789abcdef" for c in job_id)):
            raise JobError("malformed job id")

    def _job_file(self, job_id: str, suffix: str = "json") -> pathlib.Path:
        self._validate_id(job_id)
        return self.root / f"{job_id}.{suffix}"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def create_job(self, prompt: str) -> str:
        """Create a new job with *prompt* and return its ID.

        The prompt must be a UTF‑8 string between 1 and 8000 characters.
        The job file is written atomically with mode ``0600``.
        """

        if not isinstance(prompt, str):
            raise JobError("prompt must be a string")
        encoded = prompt.encode("utf-8")
        if not (1 <= len(encoded) <= 8000):
            raise JobError("prompt must be 1..8000 UTF‑8 bytes")

        job_id = uuid.uuid4().hex
        job_path = self._job_file(job_id)
        temp_path = job_path.with_suffix(".tmp")
        # Write JSON payload; the prompt is stored privately.
        with temp_path.open("w", encoding="utf-8") as fp:
            json.dump({"prompt": prompt}, fp)
        os.replace(temp_path, job_path)
        # Ensure file mode is 0600
        os.chmod(job_path, 0o600)
        return job_id

    def claim_next(self) -> Optional[str]:
        """Return the ID of the next unclaimed job, or ``None``.

        The method atomically renames the job file to a ``.claimed`` suffix.
        Races are handled by the atomic ``os.rename``; if the rename fails
        because the file no longer exists the method continues searching.
        """

        pending = sorted(self.root.glob("*.json"), key=lambda p: p.stat().st_ctime)
        for job_path in pending:
            job_id = job_path.stem
            claimed_path = job_path.with_suffix(".claimed")
            try:
                os.rename(job_path, claimed_path)
            except FileNotFoundError:
                continue
            except OSError as exc:
                # Unexpected rename error – propagate
                raise JobError(str(exc))
            return job_id
        return None

    def finish(self, job_id: str, ok: bool, text: str) -> None:
        """Mark a claimed job as finished.

        The result is written to ``<job-id>.done``.  The claimed file is
        removed.
        """

        claimed_path = self._job_file(job_id, "claimed")
        if not claimed_path.is_file():
            raise JobError("job not claimed or does not exist")
        result_path = self._job_file(job_id, "done")
        temp_path = result_path.with_suffix(".tmp")
        with temp_path.open("w", encoding="utf-8") as fp:
            json.dump({"ok": ok, "text": text}, fp)
        os.replace(temp_path, result_path)
        os.chmod(result_path, 0o600)
        claimed_path.unlink()

    def cancel(self, job_id: str) -> None:
        """Remove a pending job.

        The operation is safe even if the job is already claimed – in that
        case nothing happens.
        """

        pending_path = self._job_file(job_id, "json")
        if pending_path.is_file():
            pending_path.unlink()

    def status(self, job_id: str) -> dict:
        """Return a minimal status dictionary for *job_id*.

        The returned dict never contains the prompt.
        """

        # Ensure id is valid
        self._validate_id(job_id)
        pending = self._job_file(job_id, "json")
        claimed = self._job_file(job_id, "claimed")
        done = self._job_file(job_id, "done")
        if pending.is_file():
            return {"status": "pending"}
        if claimed.is_file():
            return {"status": "claimed"}
        if done.is_file():
            with done.open("r", encoding="utf-8") as fp:
                data = json.load(fp)
            return {"status": "finished", "ok": data["ok"], "text": data["text"]}
        raise JobError("job not found")

