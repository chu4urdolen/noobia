"""Asynchronous Job Engine for Long-Running Tools (NA-20 & ARCHITECTURE.md §8.3).

Provides:
- Non-blocking execution of long tools (network scans, camera detections, forensics).
- Non-overlapping execution via flock-based locks per tool + action.
- Structured lifecycle sense emissions:
    NOOBIA P20 asyncjob job.started job=<id> tool=<name> action=<act>
    NOOBIA P20 asyncjob job.progress job=<id> percent=<n>
    NOOBIA P20 asyncjob job.done job=<id> tool=<name> action=<act> | <summary>
    NOOBIA P20 asyncjob job.failed job=<id> tool=<name> action=<act> | <error>
"""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import sys
import threading
import time
import uuid
from typing import Any, Callable, Dict, Optional

LOCK_DIR = Path("/run/noobia/locks")


class ActionLock:
    def __init__(self, name: str, lock_dir: Optional[Path] = None):
        self.lock_dir = lock_dir or LOCK_DIR
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        # Sanitize filename
        safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in name)
        self.lock_file = self.lock_dir / f"{safe_name}.lock"
        self._fd: Optional[int] = None

    def acquire(self) -> bool:
        try:
            self._fd = os.open(str(self.lock_file), os.O_CREAT | os.O_RDWR, 0o644)
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except (BlockingIOError, OSError):
            if self._fd is not None:
                try:
                    os.close(self._fd)
                except OSError:
                    pass
                self._fd = None
            return False

    def release(self) -> None:
        if self._fd is not None:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None

    def __enter__(self):
        if not self.acquire():
            raise BlockingIOError(f"Lock {self.lock_file.name} is already held")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()


def emit_job_sense(event_type: str, job_id: str, tool: str, action: str,
                   text: str = "", fields: Optional[Dict[str, Any]] = None,
                   emitter: Optional[Callable[[str], None]] = None) -> None:
    """Emit an asyncjob lifecycle event to noobia-sense."""
    f = {"job": job_id, "tool": tool, "action": action}
    if fields:
        f.update(fields)

    # Format fields as key=value tokens
    field_str = " ".join(f"{k}={v}" for k, v in f.items())
    payload = f"NOOBIA P20 asyncjob job.{event_type} {field_str}"
    if text:
        payload += f" | {text}"

    if emitter:
        emitter(payload)
        return

    # Try standard sense.emit or viewlog
    try:
        from common.autonomy import sense
        sense.emit(20, "asyncjob", f"job.{event_type}", fields=f, text=text or None)
        return
    except Exception:
        pass

    try:
        from common.autonomy import viewlog
        viewlog.write("noobia-sense", payload)
    except Exception:
        pass


class AsyncJobManager:
    def __init__(self, lock_dir: Optional[Path] = None, emitter: Optional[Callable[[str], None]] = None):
        self.lock_dir = lock_dir or LOCK_DIR
        self.emitter = emitter

    def run_async(self, tool: str, action: str, target_fn: Callable[..., Any],
                  args: tuple = (), kwargs: Optional[Dict[str, Any]] = None,
                  cause: Optional[str] = None, use_fork: bool = False) -> Dict[str, Any]:
        """Start a task asynchronously if not already running."""
        lock_name = f"{tool}_{action}"
        lock = ActionLock(lock_name, self.lock_dir)

        if not lock.acquire():
            return {
                "ok": False,
                "busy": True,
                "error": f"Tool '{tool}' action '{action}' is already in progress.",
            }

        job_id = f"job-{uuid.uuid4().hex[:12]}"
        kwargs = kwargs or {}

        def _worker():
            extra_fields = {"cause": cause} if cause else {}
            try:
                emit_job_sense("started", job_id, tool, action,
                               text=f"Started {tool} {action}",
                               fields=extra_fields, emitter=self.emitter)
                
                result = target_fn(*args, **kwargs)
                
                summary = ""
                if isinstance(result, dict):
                    summary = result.get("sentence") or result.get("message") or json.dumps(result)
                elif isinstance(result, str):
                    summary = result
                else:
                    summary = f"Completed {tool} {action} successfully"

                emit_job_sense("done", job_id, tool, action,
                               text=str(summary), fields=extra_fields,
                               emitter=self.emitter)
            except Exception as exc:
                emit_job_sense("failed", job_id, tool, action,
                               text=f"{type(exc).__name__}: {exc}",
                               fields=extra_fields, emitter=self.emitter)
            finally:
                lock.release()

        if use_fork and hasattr(os, "fork"):
            pid = os.fork()
            if pid > 0:
                # Parent process
                return {
                    "ok": True,
                    "job_id": job_id,
                    "tool": tool,
                    "action": action,
                    "pid": pid,
                    "message": f"{tool} {action} started in background (job {job_id})"
                }
            else:
                # Child process
                try:
                    _worker()
                finally:
                    os._exit(0)
        else:
            # Thread-based background execution
            th = threading.Thread(target=_worker, name=f"asyncjob-{job_id}", daemon=True)
            th.start()
            return {
                "ok": True,
                "job_id": job_id,
                "tool": tool,
                "action": action,
                "message": f"{tool} {action} started in background (job {job_id})"
            }
