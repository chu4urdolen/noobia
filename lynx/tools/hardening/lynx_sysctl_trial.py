#!/usr/bin/env python3
"""Reversible, runtime-only Lynx kernel hardening trial."""

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(os.environ.get("LYNX_SYSCTL_ROOT", "/proc/sys"))
STATE = Path(os.environ.get("LYNX_SYSCTL_STATE", "/run/lynx-sysctl-trial"))
DELAY = int(os.environ.get("LYNX_SYSCTL_DELAY", "120"))
TARGETS = {
    "kernel/kptr_restrict": "1",
    "kernel/dmesg_restrict": "1",
    "kernel/unprivileged_bpf_disabled": "2",  # 1 cannot be undone at runtime
    "net/ipv4/conf/all/accept_redirects": "0",
    "net/ipv4/conf/default/accept_redirects": "0",
    "net/ipv4/conf/wlan0/accept_redirects": "0",
    "net/ipv4/conf/all/rp_filter": "2",  # loose mode preserves multi-homed routes
}


@contextmanager
def locked():
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    STATE.chmod(0o700)
    with (STATE / "lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def read_values():
    return {key: (ROOT / key).read_text().strip() for key in TARGETS}


def write_values(values):
    for key, value in values.items():
        (ROOT / key).write_text(str(value) + "\n")


def restore_values(values):
    """Try every original value even when one procfs write fails."""
    errors = []
    for key, value in values.items():
        try:
            (ROOT / key).write_text(str(value) + "\n")
        except OSError as exc:
            errors.append(f"{key}: {exc}")
    if errors:
        raise RuntimeError("restore incomplete: " + "; ".join(errors))


def snapshot_path():
    return STATE / "snapshot.json"


def load_snapshot():
    data = json.loads(snapshot_path().read_text())
    if set(data) != set(TARGETS) or not all(str(v).isdigit() for v in data.values()):
        raise RuntimeError("snapshot invalid; stop for manual recovery")
    return data


def save_snapshot(values):
    target = snapshot_path()
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as out:
        json.dump(values, out, sort_keys=True)
        out.write("\n")


def clear_state():
    (STATE / "pending").unlink(missing_ok=True)
    snapshot_path().unlink(missing_ok=True)


def enable():
    with locked():
        if snapshot_path().exists() or (STATE / "pending").exists():
            raise RuntimeError("trial already active; refuse to replace its rollback")
        before = read_values()
        token = f"{time.time_ns()}-{os.getpid()}"
        # Start the independent timer before changing any kernel value.
        subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "_rollback", token],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, close_fds=True, start_new_session=True)
        save_snapshot(before)
        (STATE / "pending").write_text(token + "\n")
        try:
            write_values(TARGETS)
            if read_values() != TARGETS:
                raise RuntimeError("kernel did not retain the requested values")
        except Exception as exc:
            try:
                restore_values(before)
            except RuntimeError as restore_error:
                raise RuntimeError(f"apply failed ({exc}); {restore_error}; snapshot retained") from exc
            clear_state()
            raise
    print(f"pending; auto-rollback in {DELAY}s")


def confirm():
    with locked():
        if not (STATE / "pending").exists() or not snapshot_path().exists():
            raise RuntimeError("no pending trial")
        if read_values() != TARGETS:
            raise RuntimeError("kernel values drifted; refuse confirmation")
        (STATE / "pending").unlink()
    print("active until disable or reboot")


def disable():
    with locked():
        if snapshot_path().exists():
            restore_values(load_snapshot())
            clear_state()
        else:
            (STATE / "pending").unlink(missing_ok=True)
    print("original values restored")


def rollback(token):
    time.sleep(DELAY)
    if not STATE.is_dir():
        return
    with locked():
        pending = STATE / "pending"
        if pending.exists() and pending.read_text().strip() == token:
            restore_values(load_snapshot())
            clear_state()


def status():
    if (STATE / "pending").exists():
        print("pending")
    elif snapshot_path().exists():
        print("active")
    else:
        print("off")


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        if action == "enable":
            enable()
        elif action == "confirm":
            confirm()
        elif action == "disable":
            disable()
        elif action == "status":
            status()
        elif action == "_rollback" and len(sys.argv) == 3:
            rollback(sys.argv[2])
        else:
            raise ValueError("usage: lynx_sysctl_trial.py enable|confirm|disable|status")
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"sysctl trial: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
