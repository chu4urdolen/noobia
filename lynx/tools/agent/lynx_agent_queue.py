"""Private, durable job spool for Lynx's future supervised agent worker."""

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import time
import uuid

ID = re.compile(r"[0-9a-f]{32}\Z")


class QueueError(RuntimeError):
    pass


class JobQueue:
    def __init__(self, root):
        self.root = Path(root)
        if self.root.is_symlink():
            raise QueueError("queue directory is a symlink")
        self.root.mkdir(parents=True, mode=0o700, exist_ok=True)
        mode = self.root.lstat().st_mode
        if not stat.S_ISDIR(mode) or stat.S_IMODE(mode) != 0o700:
            raise QueueError("queue directory must be a private directory")

    @staticmethod
    def _id(job_id):
        if not isinstance(job_id, str) or not ID.fullmatch(job_id):
            raise QueueError("invalid job ID")
        return job_id

    def _path(self, job_id, suffix):
        return self.root / (self._id(job_id) + "." + suffix)

    @contextmanager
    def _locked(self):
        flags = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW
        fd = os.open(self.root / ".lock", flags, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise QueueError("invalid queue lock")
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _sync_dir(self):
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def _write(self, path, data):
        temporary = self.root / (".tmp-" + uuid.uuid4().hex)
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream, separators=(",", ":"))
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            self._sync_dir()
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _regular(path):
        try:
            return stat.S_ISREG(path.lstat().st_mode)
        except FileNotFoundError:
            return False

    def create_job(self, prompt):
        if not isinstance(prompt, str) or not 1 <= len(prompt.encode("utf-8")) <= 8000:
            raise QueueError("prompt must be 1..8000 UTF-8 bytes")
        with self._locked():
            job_id = uuid.uuid4().hex
            path = self._path(job_id, "pending")
            if any(self._path(job_id, suffix).exists() or
                   self._path(job_id, suffix).is_symlink()
                   for suffix in ("pending", "running", "done")):
                raise QueueError("job ID collision")
            self._write(path, {"prompt": prompt, "created_ns": time.time_ns()})
            return job_id

    def claim_next(self, max_pending_age_s=None, max_sense_age_s=20.0):
        with self._locked():
            pending = sorted(self.root.glob("*.pending"),
                             key=lambda p: (p.lstat().st_mtime_ns, p.name))
            now_ns = time.time_ns()
            for path in pending:
                self._id(path.stem)
                if not self._regular(path):
                    raise QueueError("invalid pending job file")
                target = self._path(path.stem, "running")
                if target.exists() or target.is_symlink():
                    raise QueueError("job already claimed")
                with path.open("r", encoding="utf-8") as stream:
                    payload = json.load(stream)
                prompt = payload.get("prompt")
                if not isinstance(prompt, str):
                    raise QueueError("malformed job prompt")

                created_ns = payload.get("created_ns", path.lstat().st_mtime_ns)
                age_s = (now_ns - created_ns) / 1e9
                is_sense = prompt.lstrip().startswith("[sense]")
                if (max_pending_age_s is not None and age_s > max_pending_age_s) or \
                   (max_sense_age_s is not None and is_sense and age_s > max_sense_age_s):
                    path.unlink(missing_ok=True)
                    self._sync_dir()
                    continue

                os.replace(path, target)
                self._sync_dir()
                return path.stem, prompt
            return None

    def finish(self, job_id, ok, text):
        if not isinstance(ok, bool) or not isinstance(text, str) or len(text) > 8000:
            raise QueueError("invalid job result")
        with self._locked():
            running = self._path(job_id, "running")
            if not self._regular(running):
                raise QueueError("job is not running")
            done = self._path(job_id, "done")
            if done.exists() or done.is_symlink():
                raise QueueError("job already finished")
            self._write(done, {"ok": ok, "text": text, "finished_ns": time.time_ns()})
            running.unlink()
            self._sync_dir()

    def cancel(self, job_id):
        with self._locked():
            pending = self._path(job_id, "pending")
            if pending.is_symlink():
                raise QueueError("invalid pending job file")
            if not self._regular(pending):
                return False
            pending.unlink()
            self._sync_dir()
            return True

    def status(self, job_id):
        with self._locked():
            for suffix in ("done", "running", "pending"):
                path = self._path(job_id, suffix)
                if path.is_symlink():
                    raise QueueError("invalid job file")
                if self._regular(path):
                    if suffix == "done":
                        with path.open("r", encoding="utf-8") as stream:
                            return {"status": "finished", "ok": json.load(stream)["ok"]}
                    return {"status": suffix}
            raise QueueError("job not found")
