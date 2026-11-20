#!/usr/bin/env python3
"""Launch and tile four corner GNOME Terminal windows on Nexus startup.

The four corners of the primary screen are populated with:
  - Top-Left:     noobia-codex   (Aria)
  - Top-Right:    noobia-banshee (Banshee)
  - Bottom-Left:  dushich        (Dushich)
  - Bottom-Right: empty shell    (Interactive GNOME Terminal)
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import json
import os
import subprocess
import sys
import time
import urllib.request
from typing import Dict, Iterable, List, Sequence

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CORNERS: tuple[str, ...] = ("topleft", "topright", "bottomleft", "bottomright")

DEFAULT_WORK_AREA: Dict[str, int] = {
    "x": 67,
    "y": 32,
    "width": 1853,
    "height": 1048,
}

# GTK CSD shadow extents on GNOME Terminal (left=26, right=26, top=23, bottom=29)
CSD_EXTENTS: Dict[str, int] = {
    "left": 26,
    "right": 26,
    "top": 23,
    "bottom": 29,
}

CORNER_APP_ID = "org.gnome.Terminal.NoobiaCorners"

CORNER_SPECS: Dict[str, Dict[str, str | None]] = {
    "topleft": {
        "role": "noobia-corner-topleft",
        "title": "Noobia • Aria (noobia-codex)",
        "command": "/home/aria/.local/bin/noobia-codex",
        "geometry": "100x23+67+32",
    },
    "topright": {
        "role": "noobia-corner-topright",
        "title": "Noobia • Banshee (noobia-banshee)",
        "command": "/home/aria/.local/bin/noobia-banshee",
        "geometry": "100x23+993+32",
    },
    "bottomleft": {
        "role": "noobia-corner-bottomleft",
        "title": "Noobia • Dushich (dushich)",
        "command": "/usr/local/bin/dushich",
        "geometry": "100x23+67+556",
    },
    "bottomright": {
        "role": "noobia-corner-bottomright",
        "title": "Noobia • Terminal",
        "command": None,
        "geometry": "100x23+993+556",
    },
}

DEFAULT_SCRIPT_PATH = "/noobia/tools/nexus-corner-terminals.py"
DEFAULT_STARTUP_DELAY_SECONDS = 5

# ---------------------------------------------------------------------------
# Geometry & Command Builders
# ---------------------------------------------------------------------------

def compute_corner_rects(work_area: Dict[str, int]) -> Dict[str, Dict[str, int]]:
    """Return quarter rectangles for each screen corner."""
    left_w = work_area["width"] // 2
    right_w = work_area["width"] - left_w
    top_h = work_area["height"] // 2
    bottom_h = work_area["height"] - top_h

    return {
        "topleft": {
            "x": work_area["x"],
            "y": work_area["y"],
            "width": left_w,
            "height": top_h,
        },
        "topright": {
            "x": work_area["x"] + left_w,
            "y": work_area["y"],
            "width": right_w,
            "height": top_h,
        },
        "bottomleft": {
            "x": work_area["x"],
            "y": work_area["y"] + top_h,
            "width": left_w,
            "height": bottom_h,
        },
        "bottomright": {
            "x": work_area["x"] + left_w,
            "y": work_area["y"] + top_h,
            "width": right_w,
            "height": bottom_h,
        },
    }


def build_gnome_terminal_command(
    corner: str,
    geometry: str | None = None,
    app_id: str | None = CORNER_APP_ID,
) -> List[str]:
    """Return the command list to launch a GNOME Terminal window for a corner."""
    spec = CORNER_SPECS[corner]
    geom = geometry if geometry is not None else str(spec["geometry"])
    cmd: List[str] = ["/usr/bin/gnome-terminal"]
    if app_id:
        cmd += ["--app-id", app_id]
    cmd += [
        "--window",
        f"--role={spec['role']}",
        f"--title={spec['title']}",
        f"--geometry={geom}",
    ]
    if spec["command"] is not None:
        if spec["command"] == "/usr/local/bin/dushich":
            # Wait up to 20s for local Ollama before starting Dushich so early boot doesn't exit
            wait_ollama = (
                "for _ in $(seq 1 40); do "
                "/usr/bin/curl -fsS --max-time 1 http://127.0.0.1:11434/api/version >/dev/null 2>&1 && break; "
                "sleep 0.5; done; "
            )
            shell_str = f"{wait_ollama}{spec['command']}; exec /bin/bash -i"
        else:
            shell_str = f"{spec['command']}; exec /bin/bash -i"
        cmd += ["--", "/bin/bash", "-lc", shell_str]
    return cmd


def build_autostart_desktop(
    script_path: str = DEFAULT_SCRIPT_PATH,
    delay_seconds: int = DEFAULT_STARTUP_DELAY_SECONDS,
) -> str:
    """Return the contents of an XDG autostart .desktop file."""
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Noobia Corner Terminals\n"
        "Comment=Start four GNOME Terminal windows in the four screen corners\n"
        f"Exec=/usr/bin/python3 {script_path} --delay {delay_seconds}\n"
        "Icon=org.gnome.Terminal\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n"
        f"X-GNOME-Autostart-Delay={delay_seconds}\n"
    )


def ensure_x11_terminal_server(app_id: str = CORNER_APP_ID) -> None:
    """Ensure a dedicated X11-backed gnome-terminal-server is running for exact corner placement."""
    res = subprocess.run(
        [
            "/usr/bin/gdbus",
            "call",
            "--session",
            "--dest",
            app_id,
            "--object-path",
            "/org/gnome/Terminal",
            "--method",
            "org.freedesktop.DBus.Peer.Ping",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode == 0:
        return

    env = os.environ.copy()
    env["GDK_BACKEND"] = "x11"
    subprocess.Popen(
        ["/usr/libexec/gnome-terminal-server", "--app-id", app_id],
        env=env,
        start_new_session=True,
    )
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        ping = subprocess.run(
            [
                "/usr/bin/gdbus",
                "call",
                "--session",
                "--dest",
                app_id,
                "--object-path",
                "/org/gnome/Terminal",
                "--method",
                "org.freedesktop.DBus.Peer.Ping",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if ping.returncode == 0:
            break
        time.sleep(0.2)


def align_x11_corner_windows(work_area: Dict[str, int] | None = None) -> int:
    """Fine-tune X11 corner terminal positions and sizes via libX11."""
    if work_area is None:
        work_area = DEFAULT_WORK_AREA
    rects = compute_corner_rects(work_area)
    role_to_rect = {
        str(CORNER_SPECS[c]["role"]): rects[c] for c in CORNERS
    }

    try:
        tree_out = subprocess.check_output(
            ["/usr/bin/xwininfo", "-root", "-tree"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return 0

    lib_name = ctypes.util.find_library("X11")
    if not lib_name:
        return 0
    x11 = ctypes.CDLL(lib_name)
    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XMoveResizeWindow.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint,
        ctypes.c_uint,
    ]
    x11.XFlush.argtypes = [ctypes.c_void_p]
    x11.XCloseDisplay.argtypes = [ctypes.c_void_p]

    dpy = x11.XOpenDisplay(None)
    if not dpy:
        return 0

    aligned = 0
    try:
        for line in tree_out.splitlines():
            if "Gnome-terminal" not in line and "org.gnome.Terminal" not in line:
                continue
            parts = line.strip().split()
            if not parts or not parts[0].startswith("0x"):
                continue
            wid_str = parts[0]
            try:
                prop_out = subprocess.check_output(
                    ["/usr/bin/xprop", "-id", wid_str, "WM_WINDOW_ROLE"],
                    text=True,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                continue
            for role, r in role_to_rect.items():
                if f'"{role}"' in prop_out:
                    wid = int(wid_str, 16)
                    target_x = r["x"] - CSD_EXTENTS["left"]
                    target_y = r["y"] - CSD_EXTENTS["top"]
                    target_w = r["width"] + CSD_EXTENTS["left"] + CSD_EXTENTS["right"]
                    target_h = r["height"] + CSD_EXTENTS["top"] + CSD_EXTENTS["bottom"]
                    x11.XMoveResizeWindow(dpy, wid, target_x, target_y, target_w, target_h)
                    aligned += 1
        x11.XFlush(dpy)
    finally:
        x11.XCloseDisplay(dpy)
    return aligned


def count_gnome_terminal_windows() -> int:
    """Count currently open GNOME Terminal windows across default and corner servers."""
    total = 0
    for dest in ("org.gnome.Terminal", CORNER_APP_ID):
        try:
            res = subprocess.run(
                [
                    "/usr/bin/gdbus",
                    "call",
                    "--session",
                    "--dest",
                    dest,
                    "--object-path",
                    "/org/gnome/Terminal",
                    "--method",
                    "org.freedesktop.DBus.ObjectManager.GetManagedObjects",
                ],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            if res.returncode == 0:
                total += res.stdout.count("'/org/gnome/Terminal/window/")
        except Exception:
            pass
    return total


def launch_missing_corners(
    existing_roles: Iterable[str] | None = None,
    dry_run: bool = False,
    delay_between: float = 0.0,
) -> List[List[str]]:
    """Launch GNOME Terminal windows for any corner not already in existing_roles."""
    existing_set = set(existing_roles) if existing_roles is not None else set()
    launched: List[List[str]] = []

    if not dry_run:
        ensure_x11_terminal_server(CORNER_APP_ID)

    for corner in CORNERS:
        role = CORNER_SPECS[corner]["role"]
        if role in existing_set:
            continue
        cmd = build_gnome_terminal_command(corner)
        if not dry_run:
            subprocess.Popen(cmd, start_new_session=True)
            if delay_between > 0:
                time.sleep(delay_between)
        launched.append(cmd)

    if not dry_run and launched:
        time.sleep(0.8)
        align_x11_corner_windows()
    return launched


def wait_for_gnome_shell(timeout: float = 20.0) -> bool:
    """Wait until GNOME Shell is active on the session bus."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        res = subprocess.run(
            [
                "/usr/bin/gdbus",
                "call",
                "--session",
                "--dest",
                "org.gnome.Shell.Extensions",
                "--object-path",
                "/org/gnome/Shell/Extensions",
                "--method",
                "org.freedesktop.DBus.Peer.Ping",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0:
            return True
        time.sleep(0.5)
    return False


def wait_for_ollama(timeout: float = 15.0) -> bool:
    """Wait until local Ollama responds on 127.0.0.1:11434."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen("http://127.0.0.1:11434/api/version", timeout=1.0) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Launch Noobia corner terminals")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print JSON of commands instead of launching them.",
    )
    parser.add_argument(
        "--print-desktop",
        action="store_true",
        help="Print the XDG autostart desktop file contents.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="Seconds to sleep before launching the corner terminals.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Launch the four corner terminals even if GNOME Terminal windows already exist.",
    )
    args = parser.parse_args(argv)

    if args.print_desktop:
        print(build_autostart_desktop(), end="")
        return 0

    if args.dry_run:
        cmds = launch_missing_corners(dry_run=True)
        print(json.dumps(cmds, indent=2))
        return 0

    wait_for_gnome_shell(timeout=20.0)
    if args.delay > 0:
        time.sleep(args.delay)
    wait_for_ollama(timeout=15.0)

    if not args.force and count_gnome_terminal_windows() >= 4:
        return 0

    launch_missing_corners(dry_run=False, delay_between=0.4)
    return 0


if __name__ == "__main__":
    sys.exit(main())
