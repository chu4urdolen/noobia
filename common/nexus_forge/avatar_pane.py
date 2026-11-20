#!/usr/bin/env python3
"""Solo Dushich avatar pane: render PNG assets as TrueColor half-block art.

Renders the square PNG states (idle, working_1..4, final) into terminal
half-block (`▀`) art using 24-bit ANSI foreground/background colors. The
pane draws ONLY images (no text labels): the Dushich avatar on top and a
Rose.png fill below it. State is tracked from the agent pane's text; the
final image holds for `FINAL_DURATION` seconds before returning to idle.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import tempfile
from PIL import Image

NOOBIA = os.environ.get("NOOBIA", "/noobia")

REQUIRED_FRAMES = ("idle", "working_1", "working_2", "working_3", "working_4", "final")
BRAILLE_SPINNERS = set("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏⣾⣷⣯⣟⡿⢿⣻⣽")
CLAUDE_WORKING_RE = re.compile(
    r"[✽✻✶]\s+\S+…|…\s*\(\s*\d+[smh]|(?:·|\()\s*thinking\b|thinking\)|↓\s*[\d.]+[km]?\s*tokens",
    re.IGNORECASE,
)
CLAUDE_FINAL_RE = re.compile(
    r"\b(?:worked|thought|cooked|cogitated|baked|brewed|pondered|churned|twitched|simmered)\s+for\s+\d+|\bfor\s+\d+[smh]\b.*·\s*done",
    re.IGNORECASE,
)
DEFAULT_PICS_DIR = NOOBIA + "/pics"
DEFAULT_SIZE = 18
FINAL_DURATION = 2.0
ROSE_PATH = Path(NOOBIA + "/pics/Rose/Rose.png")


def render_png_halfblocks(png_path: str | Path, size: int = 18, height_px: int | None = None) -> str:
    """Render a PNG as `height_px // 2` lines of TrueColor half-block characters.

    ``size`` is the grid width in pixels; ``height_px`` (default ``size``)
    is the grid height. Both are clamped to even integers >= 2.
    """
    width_px = max(2, size - (size % 2))
    if height_px is None:
        height_px = size
    height_px = max(2, int(height_px) - (int(height_px) % 2))
    img = Image.open(png_path).convert("RGB").resize((width_px, height_px), Image.Resampling.LANCZOS)
    lines: list[str] = []
    for y in range(0, height_px, 2):
        row = []
        for x in range(width_px):
            r1, g1, b1 = img.getpixel((x, y))
            r2, g2, b2 = img.getpixel((x, y + 1))
            row.append(
                f"\033[38;2;{r1};{g1};{b1}m\033[48;2;{r2};{g2};{b2}m▀"
            )
        lines.append("".join(row) + "\033[0m")
    return "\n".join(lines)


def render_png_chafa(png_path: str | Path, width_cols: int = 18, height_rows: int | None = None) -> str:
    """Render a PNG with `chafa` high-density subpixel symbols."""
    if height_rows is None:
        with Image.open(png_path) as im:
            w, h = im.size
        height_rows = max(2, round(width_cols * (h / max(1, w)) * 0.5))
    if shutil.which("chafa"):
        out = subprocess.run(
            [
                "chafa",
                "--format", "symbols",
                "--symbols", "block+border+space+quad+sextant",
                "--colors", "full",
                "--size", f"{width_cols}x{height_rows}",
                "--stretch", str(png_path),
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if out.returncode == 0 and out.stdout.strip():
            text = out.stdout.rstrip("\n")
            text = re.sub(r"(?:\033\[[0-9;?]*[A-Za-z])+\s*\Z", "", text)
            return text.rstrip("\n")
    return render_png_halfblocks(png_path, width_cols, height_rows * 2)


def render_composite_sixel(
    top_png: str | Path,
    cols: int = 18,
    rows: int = 21,
    cell_w: int = 10,
    cell_h: int = 20,
) -> str:
    """Composite top Dushich portrait + bottom Rose fill into one Sixel image."""
    usable_rows = max(4, rows - 1)
    top_rows = min(usable_rows, max(2, round(cols * 1.5 * 0.5)))
    rem_rows = max(0, usable_rows - top_rows)

    px_w = cols * cell_w
    top_px_h = top_rows * cell_h
    rem_px_h = rem_rows * cell_h
    total_px_h = top_px_h + rem_px_h

    canvas = Image.new("RGB", (px_w, total_px_h), (0, 0, 0))
    with Image.open(top_png) as top_im:
        canvas.paste(top_im.convert("RGB").resize((px_w, top_px_h), Image.Resampling.LANCZOS), (0, 0))
    if rem_px_h > 0 and ROSE_PATH.exists():
        with Image.open(ROSE_PATH) as rose_im:
            canvas.paste(rose_im.convert("RGB").resize((px_w, rem_px_h), Image.Resampling.LANCZOS), (0, top_px_h))

    if shutil.which("chafa"):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            canvas.save(tmp_path, format="PNG")
            passthru = "tmux" if os.environ.get("TMUX") else "none"
            out = subprocess.run(
                [
                    "chafa",
                    "--format", "sixels",
                    "--passthrough", passthru,
                    "--size", f"{cols}x{usable_rows}",
                    "--stretch",
                    str(tmp_path),
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if out.returncode == 0 and out.stdout.strip():
                return out.stdout
        finally:
            tmp_path.unlink(missing_ok=True)
    return render_png_chafa(top_png, cols, top_rows)


def detect_solo_state(screen_text: str, pane_title: str = "") -> str:
    """Classify pane content as 'working', 'final', or 'idle'."""
    lower = screen_text.lower()
    if (
        "esc to interrupt" in lower
        or "running command" in lower
        or "thinking..." in lower
        or any(ch in BRAILLE_SPINNERS for ch in pane_title)
        or any(ch in BRAILLE_SPINNERS for ch in screen_text)
        or bool(CLAUDE_WORKING_RE.search(screen_text))
    ):
        return "working"
    if (
        "worked for " in lower
        or "thought for " in lower
        or bool(CLAUDE_FINAL_RE.search(lower))
    ):
        return "final"
    return "idle"


def is_pane_working(screen_text: str, pane_title: str = "") -> bool:
    """True when the agent pane is currently working."""
    return detect_solo_state(screen_text, pane_title) == "working"


class StateTracker:
    """State machine: working -> final (2.0s) -> idle, until the next work."""

    def __init__(self) -> None:
        self.was_working: bool = False
        self.final_until: float = 0.0

    def update(self, is_working: bool, now: float) -> str:
        if is_working:
            self.was_working = True
            return "working"
        if self.was_working:
            self.was_working = False
            self.final_until = now + FINAL_DURATION
            return "final"
        if now < self.final_until:
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
        png = self.pics_dir / self.agent / f"{frame_name}.png"
        mtime_ns = png.stat().st_mtime_ns
        if frame_name not in self._cache or self._cache[frame_name][1] != mtime_ns:
            art = render_png_chafa(png, self.size)
            self._cache[frame_name] = (art, mtime_ns)
        return self._cache[frame_name][0]


def read_pane_text(tmux_socket: str, target_pane: str) -> tuple[str, str]:
    """Read the target pane's captured text and title via tmux."""
    sock_args = [f"-L{tmux_socket}"] if tmux_socket and tmux_socket != "default" else []
    try:
        out = subprocess.run(
            ["tmux", *sock_args, "capture-pane", "-t", target_pane, "-p", "-J", "-S", "-60"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        text = out.stdout or ""
    except Exception:
        text = ""
    try:
        title = subprocess.run(
            ["tmux", *sock_args, "display-message", "-t", target_pane, "-p", "#{pane_title}"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    except Exception:
        title = ""
    return text, title


def draw_frame(top_art: str, bottom_art: str = "", clear_all: bool = False) -> None:
    """Stamp the image art with no text: images only.

    Disables line wrap and hides the cursor. With ``clear_all`` the whole
    screen and scrollback are cleared first; otherwise only the area below
    the cursor is cleared before and after.
    """
    prefix = "\033[?7l\033[?25l"
    if clear_all:
        prefix += "\033[2J\033[3J\033[H"
        suffix = ""
    else:
        prefix += "\033[H"
        suffix = "\033[J"
    parts = top_art
    if bottom_art:
        parts += "\n" + bottom_art
    sys.stdout.write(prefix + parts + suffix)
    sys.stdout.flush()


def render_bottom_fill(rows: int, size: int, top_rows: int = 14) -> str:
    """Render the Rose.png fill for the rows below the avatar grid."""
    rem_rows = max(0, rows - top_rows - 1)
    if rem_rows < 2 or not ROSE_PATH.exists():
        return ""
    return render_png_chafa(ROSE_PATH, size, rem_rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Solo Dushich avatar pane renderer.")
    parser.add_argument("--agent", default="Dushich")
    parser.add_argument("--pics-dir", default=DEFAULT_PICS_DIR)
    parser.add_argument("--tmux-socket", default=os.environ.get("TMUX_TMP_SOCKET", "dushich"))
    parser.add_argument("--target-pane", default="")
    parser.add_argument("--size", type=int, default=DEFAULT_SIZE)
    parser.add_argument("--interval", type=float, default=0.4)
    parser.add_argument("--sixel", action="store_true", help="render full-resolution Sixel via passthrough")
    parser.add_argument("--once", action="store_true", help="render one frame and exit")
    args = parser.parse_args()

    cache = FrameCache(args.pics_dir, args.agent, args.size)
    sixel_cache: dict[tuple[str, int, int, int], str] = {}
    tracker = StateTracker()
    last_dims: tuple[int, int] | None = None
    last_drawn: tuple[str, int, int] | None = None
    bottom_art = ""

    while True:
        now = time.monotonic()
        cols, rows = shutil.get_terminal_size((args.size, 24))
        clear_all = False
        if cols != args.size and args.target_pane:
            self_pane = os.environ.get("TMUX_PANE") or (args.target_pane.rsplit(".", 1)[0] + ".1")
            subprocess.run(
                [
                    "tmux", f"-L{args.tmux_socket}", "resize-pane",
                    "-t", self_pane, "-x", str(args.size),
                ],
                capture_output=True,
                timeout=5,
            )
            cols, rows = shutil.get_terminal_size((args.size, 24))
            clear_all = True
        if (cols, rows) != last_dims:
            clear_all = True
            last_dims = (cols, rows)
            last_drawn = None
            if not args.sixel:
                bottom_art = render_bottom_fill(rows, args.size)

        if args.target_pane:
            text, title = read_pane_text(args.tmux_socket, args.target_pane)
            if text is None:
                return 0
        else:
            text, title = "", ""
        state = tracker.update(is_pane_working(text, title), now)
        frame = select_frame_name(state, int(now / args.interval))
        draw_key = (frame, cols, rows)
        if draw_key != last_drawn or clear_all:
            if args.sixel:
                png = Path(args.pics_dir) / args.agent / f"{frame}.png"
                mtime = png.stat().st_mtime_ns if png.exists() else 0
                skey = (frame, cols, rows, mtime)
                if skey not in sixel_cache:
                    sixel_cache[skey] = render_composite_sixel(png, args.size, rows)
                draw_frame(sixel_cache[skey], "", clear_all)
            else:
                draw_frame(cache.get(frame), bottom_art, clear_all)
            last_drawn = draw_key
        if args.once:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
