#!/usr/bin/env python3
"""Solo Dushich avatar pane: render PNG assets as TrueColor half-block art.

Renders the square PNG states (idle, working_1..4, final) into terminal
half-block (`▀`) art using 24-bit ANSI foreground/background colors, detects
the agent state from pane text, and animates the working frames.
"""

from __future__ import annotations

import argparse
import os
import sys
import subprocess
import time
from pathlib import Path

from PIL import Image

REQUIRED_FRAMES = ("idle", "working_1", "working_2", "working_3", "working_4", "final")
BRAILLE_SPINNERS = set("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏")
DEFAULT_PICS_DIR = "/noobia/pics"
AGENT_LABELS = {"idle": "IDLE", "working": "WORKING", "final": "FINAL"}


def render_png_halfblocks(png_path: str | Path, size: int = 28) -> str:
    """Render a PNG as `size // 2` lines of TrueColor half-block characters."""
    size = max(2, size - (size % 2))
    img = Image.open(png_path).convert("RGB").resize((size, size), Image.Resampling.LANCZOS)
    lines: list[str] = []
    for y in range(0, size, 2):
        row = []
        for x in range(size):
            r1, g1, b1 = img.getpixel((x, y))
            r2, g2, b2 = img.getpixel((x, y + 1))
            row.append(
                f"\033[38;2;{r1};{g1};{b1}m\033[48;2;{r2};{g2};{b2}m▀"
            )
        lines.append("".join(row) + "\033[0m")
    return "\n".join(lines)


def detect_solo_state(screen_text: str, pane_title: str = "") -> str:
    """Classify pane content as 'working', 'final', or 'idle'."""
    lower = screen_text.lower()
    if "esc to interrupt" in lower or (
        any(ch in BRAILLE_SPINNERS for ch in pane_title)
        or any(ch in BRAILLE_SPINNERS for ch in screen_text)
    ):
        return "working"
    if "worked for " in lower:
        return "final"
    return "idle"


def select_frame_name(state: str, tick: int) -> str:
    """Map a state + animation tick to the frame file name to render."""
    if state == "working":
        return f"working_{(tick % 4) + 1}"
    if state == "final":
        return "final"
    return "idle"


class FrameCache:
    """Cache rendered half-block strings per agent/frame."""

    def __init__(self, pics_dir: str, agent: str, size: int) -> None:
        self.pics_dir = Path(pics_dir)
        self.agent = agent
        self.size = size
        self._cache: dict[str, str] = {}

    def get(self, frame_name: str) -> str:
        if frame_name not in self._cache:
            png = self.pics_dir / self.agent / f"{frame_name}.png"
            self._cache[frame_name] = render_png_halfblocks(png, self.size)
        return self._cache[frame_name]


def read_pane_text(tmux_socket: str, target_pane: str) -> tuple[str, str]:
    """Read the target pane's captured text and title via tmux."""
    try:
        out = subprocess.run(
            ["tmux", f"-L{tmux_socket}", "capture-pane", "-t", target_pane, "-p", "-J", "-S", "-60"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        text = out.stdout or ""
    except Exception:
        text = ""
    try:
        title = subprocess.run(
            ["tmux", f"-L{tmux_socket}", "display-message", "-t", target_pane, "-p", "#{pane_title}"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    except Exception:
        title = ""
    return text, title


def draw_frame(art: str, agent: str, state: str) -> None:
    """Erase the screen area and stamp the frame plus status line."""
    status = f"{agent} • {AGENT_LABELS.get(state, 'IDLE')}"
    art_lines = art.splitlines()
    clear = "\033[H" + "\033[2K" * (len(art_lines) + 1)
    out = clear + art + "\n" + f"\033[1m{status}\033[0m\n"
    sys.stdout.write(out)
    sys.stdout.flush()


def main() -> int:
    parser = argparse.ArgumentParser(description="Solo Dushich avatar pane renderer.")
    parser.add_argument("--agent", default="Dushich")
    parser.add_argument("--pics-dir", default=DEFAULT_PICS_DIR)
    parser.add_argument("--tmux-socket", default=os.environ.get("TMUX_TMP_SOCKET", "dushich"))
    parser.add_argument("--target-pane", default="")
    parser.add_argument("--size", type=int, default=28)
    parser.add_argument("--interval", type=float, default=0.4)
    parser.add_argument("--once", action="store_true", help="render one frame and exit")
    args = parser.parse_args()

    cache = FrameCache(args.pics_dir, args.agent, args.size)
    if args.once:
        text, title = (read_pane_text(args.tmux_socket, args.target_pane)
                       if args.target_pane else ("", ""))
        state = detect_solo_state(text, title)
        frame = select_frame_name(state, 0)
        draw_frame(cache.get(frame), args.agent, state)
        return 0

    tick = 0
    while True:
        if args.target_pane:
            text, title = read_pane_text(args.tmux_socket, args.target_pane)
        else:
            text, title = "", ""
        state = detect_solo_state(text, title)
        frame = select_frame_name(state, tick)
        draw_frame(cache.get(frame), args.agent, state)
        tick += 1
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
