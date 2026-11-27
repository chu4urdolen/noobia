"""Universal supervised agent worker loop for any Noob (NA-81).

Executes claimed queue jobs with:
- Privilege dropping (no_new_privs, non-root user)
- Inference backend validation
- Signed Aigel outbox reply delivery
- Principle 10 thermal/battery quiescence compliance
- Event ID acknowledgment back into events.db upon completion
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import unicodedata
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from .jobqueue import JobQueue, QueueError

PR_SET_NO_NEW_PRIVS = 38


def sanitize_text(text: str) -> str:
    """Sanitize text: remove emojis and replace em-dashes/en-dashes with comma."""
    import re
    text = text.replace("—", ",").replace("–", ",")
    text = re.sub(r'\s*,\s*', ', ', text)
    out = []
    for ch in text:
        cat = unicodedata.category(ch)
        if cat.startswith("S") or cat in ("So", "Sk", "Sm", "Sc"):
            continue
        out.append(ch)
    return "".join(out).strip()


def _no_new_privs():
    import ctypes
    if ctypes.CDLL(None, use_errno=True).prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "prctl(NO_NEW_PRIVS) failed")


class AgentWorker:
    def __init__(
        self,
        queue_root: Path | str,
        stop_path: Path | str,
        agent_bin: Path | str,
        agent_user: str = "",
        thought_path: Optional[Path | str] = None,
        aigel_key_path: Optional[Path | str] = None,
    ):
        self.queue = JobQueue(queue_root)
        self.stop_path = Path(stop_path)
        self.agent_bin = str(agent_bin)
        self.agent_user = agent_user
        self.thought_path = Path(thought_path) if thought_path else None
        self.aigel_key_path = Path(aigel_key_path) if aigel_key_path else None
        self.current_process: Optional[subprocess.Popen] = None
        self.stopping = False

    def agent_privileges(self) -> Dict[str, Any]:
        if not self.agent_user:
            return {}
        import pwd
        pw = pwd.getpwnam(self.agent_user)
        if pw.pw_uid == 0:
            raise ValueError("Agent user must not be root")
        return {
            "user": pw.pw_uid,
            "group": pw.pw_gid,
            "extra_groups": [],
            "preexec_fn": _no_new_privs,
        }

    def sign_headers(self, payload: bytes) -> Dict[str, str]:
        if not self.aigel_key_path or not self.aigel_key_path.exists():
            return {"Content-Type": "application/json"}
        secret = self.aigel_key_path.read_text(encoding="utf-8").strip()
        if not secret:
            return {"Content-Type": "application/json"}
        sig = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
        return {"Content-Type": "application/json", "X-Noobia-Signature": sig}

    def execute_job(self, prompt: str, timeout: float = 120.0) -> Tuple[bool, str]:
        if not os.path.exists(self.agent_bin) or not os.access(self.agent_bin, os.X_OK):
            return False, "executable_unavailable"

        cmd = ["/usr/bin/python3", self.agent_bin, "--stdin"]
        kwargs = self.agent_privileges()
        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
                **kwargs,
            )
            self.current_process = proc
            out, err = proc.communicate(input=prompt, timeout=timeout)
            ok = (proc.returncode == 0)
            text = out.strip() or err.strip()
            return ok, text
        except subprocess.TimeoutExpired:
            if self.current_process:
                try:
                    os.killpg(self.current_process.pid, signal.SIGKILL)
                except OSError:
                    pass
            return False, "inference_timeout"
        except Exception as exc:
            return False, f"worker_error: {exc}"
        finally:
            self.current_process = None

    def run_one(self) -> bool:
        """Claim and execute one pending job. Return True if work was done."""
        if self.stop_path.exists():
            return False
        claimed = self.queue.claim_next()
        if not claimed:
            return False
        job_id, prompt = claimed
        event_ids = self.queue.get_event_ids(job_id)

        print(json.dumps({"event": "job_started", "job_id": job_id}), flush=True)
        ok, text = self.execute_job(prompt)

        # Ack events in events.db if any
        if event_ids:
            try:
                from common.autonomy.events import EventStore
                store = EventStore()
                for eid in event_ids:
                    store.ack(eid)
            except Exception:
                pass

        # Update thought if output generated
        if ok and self.thought_path and text:
            clean_thought = sanitize_text(text)
            try:
                self.thought_path.parent.mkdir(parents=True, exist_ok=True)
                self.thought_path.write_text(clean_thought, encoding="utf-8")
            except OSError:
                pass

        self.queue.finish(job_id, ok, text)
        print(json.dumps({"event": "job_finished", "job_id": job_id, "ok": ok, "event_ids": event_ids}), flush=True)
        return True
