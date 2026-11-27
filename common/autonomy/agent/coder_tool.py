"""Run one bounded coding task as an unprivileged coding user for any Noob (NA-81)."""

from __future__ import annotations

import json
import os
from pathlib import Path
import pwd
import signal
import subprocess
import sys
from typing import Any, Dict, Optional


def ask_coder(
    prompt: str,
    codex_binary: Path | str,
    work_dir: Path | str,
    home_dir: Path | str,
    coder_user: str,
    model: str = "qwen3.8-27b",
    timeout: float = 180.0,
    nexus_key_path: Optional[Path | str] = None,
) -> Dict[str, Any]:
    if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 2000:
        raise ValueError("Prompt length must be 1..2000 characters")

    codex = Path(codex_binary)
    work = Path(work_dir)
    home = Path(home_dir)

    if not codex.is_file() or not os.access(codex, os.X_OK):
        raise RuntimeError(f"Codex binary unavailable at {codex}")

    try:
        user = pwd.getpwnam(coder_user)
    except KeyError:
        raise RuntimeError(f"Coding user '{coder_user}' does not exist")

    if user.pw_uid == 0:
        raise RuntimeError("Coding user cannot be root")
    if not work.is_dir() or work.stat().st_uid != user.pw_uid:
        raise RuntimeError(f"Unprivileged workspace unavailable at {work}")

    key = ""
    if nexus_key_path and Path(nexus_key_path).exists():
        key = Path(nexus_key_path).read_text(encoding="utf-8").strip()

    command = [
        str(codex), "exec", "--skip-git-repo-check", "-s", "danger-full-access",
        "-m", model, "-C", str(work), prompt
    ]
    env = {
        "HOME": str(home),
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "CODEX_HOME": str(home / ".codex"),
        "NEXUS_KEY": key,
    }
    process = subprocess.Popen(
        command,
        cwd=work,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
        user=user.pw_uid,
        group=user.pw_gid,
    )
    try:
        out, err = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        raise RuntimeError("Codex task timed out") from None

    if process.returncode != 0:
        raise RuntimeError("Codex task failed: " + err[-600:])

    return {
        "ok": True,
        "model": model,
        "output": out[-4000:],
        "workspace": str(work),
        "user": coder_user,
    }
