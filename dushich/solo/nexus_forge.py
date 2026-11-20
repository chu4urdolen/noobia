#!/usr/bin/env python3
"""nexus-forge: a multi-terminal GTK3 + VTE 2.91 window for Noobia agents.

A 2x2 resizable grid of quadrants, each pairing a live terminal with an
animated avatar sidebar.  The quadrants:

    top-left     Aria + Dushich Helper   (Aria codex, Dushich helper)
    bottom-left  Dushich Solo            (dushich, no helper)
    top-right    Banshee + Dushich Helper (banshee, Dushich helper)
    bottom-right Gwyn + Dushich Helper   (Claude Code, Dushich helper)

Every quadrant reuses the pure helpers from `avatar_pane` / `dushich_window`
(`StateTracker`, `is_pane_working`, `select_frame_name`,
`compute_sidebar_layout`, `is_dushich_helper_working`, ...).  The sidebar
draws the primary agent frame on top, an optional helper-agent frame in the
middle, a one-line token quota badge (`H/W : %/%` or `Local: 100%`) right above
`Rose.png`, and `Rose.png` filling any remaining height at the bottom.

Features:
- **Quadrant Zoom**: Press `Ctrl+Shift+Z` or `F11`, or double-click any quadrant
  header to maximize that quadrant to fill the whole window.  Press again or
  `Escape` to restore the 2x2 grid.
- **Token Quota Badge**: Live hourly/weekly token quota or local indicator
  rendered on a compact pill badge right above Rose.
- **Session Resilience**: Reconnect/respawn overlay card on terminal child exit.
- **Portable Configuration**: Load custom titles, paths, commands, and badges
  via `--config <path>` or `~/.config/nexus-forge/config.json`.

Run `nexus_forge.py --self-test` for a headless smoke test of the quadrant
table, config loader, token quota resolver, layout math, and pixbuf Cairo paints.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from avatar_pane import (
    DEFAULT_PICS_DIR,
    REQUIRED_FRAMES,
    ROSE_PATH,
    StateTracker,
    is_pane_working,
    read_pane_text,
    select_frame_name,
)
from dushich_window import compute_sidebar_layout, is_dushich_helper_working

# ---------------------------------------------------------------------------
# GUI imports are optional at import time so the pure data table (and the
# headless --self-test helpers) can be imported without a display connection.
# ---------------------------------------------------------------------------
try:
    import gi

    gi.require_version("Gtk", "3.0")
    gi.require_version("Vte", "2.91")
    gi.require_version("Gdk", "3.0")
    gi.require_version("GdkPixbuf", "2.0")
    gi.require_version("PangoCairo", "1.0")
    from gi.repository import Gtk, Vte, Gdk, GdkPixbuf, GLib, Pango, PangoCairo

    _GI_AVAILABLE = True
except Exception as _gi_import_error:  # pragma: no cover - environment specific
    Gtk = None
    Vte = None
    Gdk = None
    GdkPixbuf = None
    GLib = None
    Pango = None
    PangoCairo = None
    _GI_AVAILABLE = False
    _GI_IMPORT_ERROR = _gi_import_error


ASPECT_RATIO = 1.5
DEFAULT_SIDEBAR_WIDTH = 140
POLL_INTERVAL = 0.4
BACKGROUND = "#121417"
FOREGROUND = "#e6edf3"
ARIA_TMUX_SOCKET = "default"
DEFAULT_CONFIG_PATH = Path.home() / ".config" / "nexus-forge" / "config.json"
DEFAULT_RATE_LIMITS_PATH = Path.home() / ".config" / "nexus-forge" / "rate_limits.json"

# ---------------------------------------------------------------------------
# The quadrant table: which agent, optional helper, and launch command each
# of the four quadrants runs.  Pure data -- no GTK required.
# ---------------------------------------------------------------------------
DEFAULT_QUADRANTS = {
    "top_left": {
        "title": "Aria + Dushich Helper",
        "agent": "Aria",
        "helper_agent": "",
        "badge": "",
        "command": [
            "/bin/bash",
            "-lc",
            "s=$(tmux list-sessions -F '#{session_name}:#{session_attached}' 2>/dev/null | awk -F: '/^noobia-aria-.*:0$/{print $1; exit}'); if [ -n \"$s\" ]; then if tmux list-panes -t \"$s\":0 -F '#{pane_current_command}' 2>/dev/null | grep -qx 'codex'; then exec tmux attach-session -t \"$s\"; else tmux kill-session -t \"$s\" 2>/dev/null || true; fi; fi; NOOBIA_ARIA_NO_GUI=1 exec ${NOOBIA:-/noobia}/aria/codex-with-dushich",
        ],
    },
    "bottom_left": {
        "title": "Dushich Solo",
        "agent": "Dushich",
        "helper_agent": "",
        "badge": "Local: 100%",
        "command": [
            "/bin/bash",
            "-lc",
            "for _ in $(seq 1 40); do /usr/bin/curl -fsS --max-time 1 http://127.0.0.1:11434/api/version >/dev/null 2>&1 && break; sleep 0.5; done; s=$(tmux -Ldushich-clean list-sessions -F '#{session_name}:#{session_attached}' 2>/dev/null | awk -F: '/^noobia-dushich-solo-.*:0$/{print $1; exit}'); if [ -n \"$s\" ]; then exec tmux -Ldushich-clean attach-session -t \"$s\"; fi; NOOBIA_DUSHICH_NO_GUI=1 exec ${NOOBIA:-/noobia}/dushich/solo/launch --no-gui",
        ],
    },
    "top_right": {
        "title": "Banshee + Dushich Helper",
        "agent": "Banshee",
        "helper_agent": "",
        "badge": "",
        "command": [
            "/bin/bash",
            "-lc",
            "s=$(tmux list-sessions -F '#{session_name}:#{session_attached}' 2>/dev/null | awk -F: '/^noobia-banshee-.*:0$/{print $1; exit}'); if [ -n \"$s\" ]; then exec tmux attach-session -t \"$s\"; fi; exec ${NOOBIA:-/noobia}/banshee/launch",
        ],
    },
    "bottom_right": {
        "title": "Gwyn + Dushich Helper",
        "agent": "Gwyn",
        "helper_agent": "",
        "badge": "",
        "command": [
            "/bin/bash",
            "-lc",
            "s=$(tmux list-sessions -F '#{session_name}:#{session_attached}' 2>/dev/null | awk -F: '/^noobia-gwyn-.*:0$/{print $1; exit}'); if [ -n \"$s\" ]; then exec tmux attach-session -t \"$s\"; fi; exec ${NOOBIA:-/noobia}/gwyn-app-nub/launch",
        ],
    },
}


def quadrant_names(left_only: bool = False) -> list:
    """Return the quadrant names to build, in grid order.

    With ``left_only`` only the two left quadrants are returned (Top-Left
    Aria+Dushich and Bottom-Left Dushich Solo).
    """
    if left_only:
        return ["top_left", "bottom_left"]
    return ["top_left", "top_right", "bottom_left", "bottom_right"]


# ---------------------------------------------------------------------------
# Configuration loading & merging
# ---------------------------------------------------------------------------
def load_config(
    config_path: str | Path | None = None,
    check_default: bool = True,
) -> dict:
    """Load configuration from a JSON file, or return empty dict if not found."""
    target: Path | None = None
    if config_path:
        target = Path(config_path)
    elif os.environ.get("NEXUS_FORGE_CONFIG"):
        target = Path(os.environ["NEXUS_FORGE_CONFIG"])
    elif check_default and DEFAULT_CONFIG_PATH.is_file():
        target = DEFAULT_CONFIG_PATH

    if target and target.is_file():
        try:
            with open(target, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception as err:
            print(f"Warning: failed to read config file {target}: {err}", file=sys.stderr)
    return {}


def build_quadrants_table(cfg: dict | None = None) -> dict:
    """Return quadrants table merged from default and optional config dict."""
    quads = {k: dict(v) for k, v in DEFAULT_QUADRANTS.items()}
    if cfg and "quadrants" in cfg and isinstance(cfg["quadrants"], dict):
        for q_name, q_val in cfg["quadrants"].items():
            if isinstance(q_val, dict):
                merged = dict(quads.get(q_name, {}))
                merged.update(q_val)
                quads[q_name] = merged
    return quads


# ---------------------------------------------------------------------------
# Token quota / rate limits resolution
# ---------------------------------------------------------------------------
_TOKEN_BADGE_CACHE: dict[str, tuple[float, str]] = {}
CACHE_TTL = 15.0


def _get_agy_token_quota() -> str:
    now = time.time()
    one_hour_ago = now - 3600
    one_week_ago = now - 7 * 86400
    total_1h = 0
    total_7d = 0
    pattern = str(
        Path.home()
        / ".gemini"
        / "antigravity-cli"
        / "brain"
        / "*"
        / ".system_generated"
        / "logs"
        / "transcript.jsonl"
    )
    for fpath in glob.glob(pattern):
        try:
            if os.path.getmtime(fpath) < one_week_ago:
                continue
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    try:
                        d = json.loads(line)
                        ts_str = d.get("created_at")
                        if not ts_str:
                            continue
                        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        ts_sec = dt.timestamp()
                        if ts_sec < one_week_ago:
                            continue
                        toks = (d.get("input_tokens") or 0) + (d.get("output_tokens") or 0)
                        if ts_sec >= one_hour_ago:
                            total_1h += toks
                        total_7d += toks
                    except Exception:
                        pass
        except Exception:
            pass
    if total_7d == 0 and total_1h == 0:
        return "H/W: --% / --%"
    h_rem = max(0, 100 - min(100, int(round((total_1h / 1_000_000) * 100))))
    w_rem = max(0, 100 - min(100, int(round((total_7d / 15_000_000) * 100))))
    return f"H/W: {h_rem}% / {w_rem}%"


def _get_claude_token_quota() -> str:
    now = time.time()
    one_hour_ago = now - 3600
    one_week_ago = now - 7 * 86400
    total_1h = 0
    total_7d = 0
    pattern = "/noobia/gwyn-app-nub/private/claude/projects/**/*.jsonl"
    for fpath in glob.glob(pattern, recursive=True):
        try:
            if os.path.getmtime(fpath) < one_week_ago:
                continue
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    try:
                        d = json.loads(line)
                        ts_str = d.get("timestamp")
                        if not ts_str or not isinstance(ts_str, str):
                            continue
                        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        ts_sec = dt.timestamp()
                        if ts_sec < one_week_ago:
                            continue
                        msg = d.get("message")
                        if isinstance(msg, dict):
                            usage = msg.get("usage") or {}
                            toks = (usage.get("input_tokens") or 0) + (usage.get("output_tokens") or 0)
                            if ts_sec >= one_hour_ago:
                                total_1h += toks
                            total_7d += toks
                    except Exception:
                        pass
        except Exception:
            pass
    if total_7d == 0 and total_1h == 0:
        return "H/W: --% / --%"
    h_rem = max(0, 100 - min(100, int(round((total_1h / 500_000) * 100))))
    w_rem = max(0, 100 - min(100, int(round((total_7d / 5_000_000) * 100))))
    return f"H/W: {h_rem}% / {w_rem}%"


def resolve_token_badge(
    agent: str,
    explicit_badge: str = "",
    rate_limits_path: Path | None = None,
) -> str:
    """Return a short hourly/weekly token percentage string for the avatar pane.

    Format: 'H/W: %/%' (e.g. 'H/W: 100% / 64%'), or 'Local: 100%' for local models.
    Values represent percentage of token quota remaining.
    """
    if explicit_badge:
        return explicit_badge

    agent_norm = (agent or "").strip().lower()
    if agent_norm == "dushich":
        return "Local: 100%"

    # Check for an override / shared rate limits cache file if present
    cache_file = rate_limits_path or DEFAULT_RATE_LIMITS_PATH
    if cache_file.is_file():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    val = data.get(agent) or data.get(agent_norm)
                    if isinstance(val, str) and val.strip():
                        return val.strip()
        except Exception:
            pass

    # In-memory TTL cache
    now = time.time()
    cached = _TOKEN_BADGE_CACHE.get(agent_norm)
    if cached and (now - cached[0]) < CACHE_TTL:
        return cached[1]

    result = "H/W: --% / --%"
    if agent_norm == "aria":
        try:
            sessions = sorted(
                glob.glob(
                    str(Path.home() / ".codex" / "sessions" / "**" / "*.jsonl"),
                    recursive=True,
                ),
                key=os.path.getmtime,
            )
            for s in reversed(sessions[-10:]):
                try:
                    with open(s, "r", encoding="utf-8", errors="ignore") as f:
                        for line in reversed(f.readlines()[-100:]):
                            if "rate_limits" in line:
                                d = json.loads(line)
                                payload = d.get("payload") or {}
                                rl = payload.get("rate_limits") or (
                                    payload.get("info") or {}
                                ).get("rate_limits")
                                if isinstance(rl, dict):
                                    p = rl.get("primary") or {}
                                    sec = rl.get("secondary") or {}
                                    hp = p.get("used_percent")
                                    wp = sec.get("used_percent")
                                    if hp is not None or wp is not None:
                                        h_rem = (
                                            max(0, 100 - int(round(hp)))
                                            if hp is not None
                                            else None
                                        )
                                        w_rem = (
                                            max(0, 100 - int(round(wp)))
                                            if wp is not None
                                            else None
                                        )
                                        h_str = (
                                            f"{h_rem}%"
                                            if h_rem is not None
                                            else "--%"
                                        )
                                        w_str = (
                                            f"{w_rem}%"
                                            if w_rem is not None
                                            else "--%"
                                        )
                                        result = f"H/W: {h_str} / {w_str}"
                                        break
                        if result != "H/W: --% / --%":
                            break
                except Exception:
                    continue
        except Exception:
            pass
    elif agent_norm == "banshee":
        try:
            result = _get_agy_token_quota()
        except Exception:
            result = "H/W: --% / --%"
    elif agent_norm == "gwyn":
        try:
            result = _get_claude_token_quota()
        except Exception:
            result = "H/W: --% / --%"

    _TOKEN_BADGE_CACHE[agent_norm] = (now, result)
    return result


# ---------------------------------------------------------------------------
# Tmux state polling helpers
# ---------------------------------------------------------------------------
def read_aria_tmux_state(socket: str = ARIA_TMUX_SOCKET) -> tuple:
    """Read the live Aria tmux session (``noobia-aria-*``) off-screen.

    Returns a ``(aria_working, dushich_helper_working)`` tuple derived from
    the two panes of the most recent ``noobia-aria-*`` session.
    """
    if not socket:
        return False, False
    socket = socket.lstrip("-L")
    cmd_prefix = ["tmux", f"-L{socket}"] if socket != "default" else ["tmux"]
    try:
        out = subprocess.run(
            cmd_prefix + ["list-sessions", "-F", "#{session_name}"],
            capture_output=True, text=True, timeout=5,
        ).stdout
    except Exception:
        return False, False
    aria_sessions = [
        line.strip()
        for line in out.splitlines()
        if line.strip().startswith("noobia-aria-")
    ]
    if not aria_sessions:
        return False, False
    session = aria_sessions[-1]
    try:
        panes_out = subprocess.run(
            cmd_prefix + [
                "list-panes", "-t", f"{session}:0",
                "-F", "#{pane_index}\t#{pane_title}",
            ],
            capture_output=True, text=True, timeout=5,
        ).stdout
    except Exception:
        return False, False

    aria_text = aria_title = helper_text = helper_title = ""
    for line in panes_out.splitlines():
        if "\t" not in line:
            continue
        index, title = line.split("\t", 1)
        target = f"{session}:0.{index}"
        try:
            text = subprocess.run(
                cmd_prefix + ["capture-pane", "-t", target, "-p"],
                capture_output=True, text=True, timeout=5,
            ).stdout
        except Exception:
            text = ""
        if title.lower().startswith("aria") or "codex" in title.lower():
            aria_text, aria_title = text, title
        elif "dushich" in title.lower():
            helper_text, helper_title = text, title
        else:
            if index == "0":
                aria_text, aria_title = text, title
            elif index == "1":
                helper_text, helper_title = text, title
    aria_working = is_pane_working(aria_text, aria_title)
    helper_working = is_dushich_helper_working(helper_text, helper_title)
    return aria_working, helper_working


def read_banshee_tmux_state(socket: str = "default") -> tuple:
    """Read the live Banshee tmux session (``noobia-banshee-*``) off-screen."""
    return _read_helper_tmux_state("noobia-banshee-", ("banshee", "antigravity"), socket)


def read_gwyn_tmux_state(socket: str = "default") -> tuple:
    """Read the live Gwyn tmux session (``noobia-gwyn-*``) off-screen."""
    return _read_helper_tmux_state("noobia-gwyn-", ("gwyn", "claude"), socket)


def _read_helper_tmux_state(prefix: str, agent_words: tuple, socket: str) -> tuple:
    """Return ``(agent_working, dushich_helper_working)`` for a two-pane session."""
    if not socket:
        return False, False
    socket = socket.lstrip("-L")
    cmd_prefix = ["tmux", f"-L{socket}"] if socket != "default" else ["tmux"]
    try:
        out = subprocess.run(
            cmd_prefix + ["list-sessions", "-F", "#{session_name}"],
            capture_output=True, text=True, timeout=5,
        ).stdout
    except Exception:
        return False, False
    sessions = [
        line.strip()
        for line in out.splitlines()
        if line.strip().startswith(prefix)
    ]
    if not sessions:
        return False, False
    session = sessions[-1]
    try:
        panes_out = subprocess.run(
            cmd_prefix + [
                "list-panes", "-t", f"{session}:0",
                "-F", "#{pane_index}\t#{pane_title}",
            ],
            capture_output=True, text=True, timeout=5,
        ).stdout
    except Exception:
        return False, False

    agent_text = agent_title = helper_text = helper_title = ""
    for line in panes_out.splitlines():
        if "\t" not in line:
            continue
        index, title = line.split("\t", 1)
        target = f"{session}:0.{index}"
        try:
            text = subprocess.run(
                cmd_prefix + ["capture-pane", "-t", target, "-p"],
                capture_output=True, text=True, timeout=5,
            ).stdout
        except Exception:
            text = ""
        if any(word in title.lower() for word in agent_words) or index == "0":
            agent_text, agent_title = text, title
        elif "dushich" in title.lower() or index == "1":
            helper_text, helper_title = text, title
    agent_working = is_pane_working(agent_text, agent_title)
    helper_working = is_dushich_helper_working(helper_text, helper_title)
    return agent_working, helper_working


def read_dushich_solo_tmux_state() -> bool:
    """Read the live Dushich Solo tmux session off-screen."""
    try:
        out = subprocess.run(
            ["tmux", "-Ldushich-clean", "list-sessions", "-F", "#{session_name}"],
            capture_output=True, text=True, timeout=5,
        ).stdout
    except Exception:
        return False
    sessions = [
        line.strip()
        for line in out.splitlines()
        if line.strip().startswith("noobia-dushich-solo-")
    ]
    if not sessions:
        return False
    session = sessions[-1]
    try:
        text = subprocess.run(
            ["tmux", "-Ldushich-clean", "capture-pane", "-t", f"{session}:0.0", "-p"],
            capture_output=True, text=True, timeout=5,
        ).stdout
        title = subprocess.run(
            ["tmux", "-Ldushich-clean", "display-message", "-t", f"{session}:0.0", "-p", "#{pane_title}"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
    except Exception:
        return False
    return is_pane_working(text, title)


# ---------------------------------------------------------------------------
# Reusable quadrant widget.  Defined only when the GTK stack is importable;
# instantiating it (which requires a display) happens only in _run_gui.
# ---------------------------------------------------------------------------
if _GI_AVAILABLE:

    class QuadrantPanel(Gtk.Box):
        """One terminal + animated avatar sidebar, with header and reconnect overlay."""

        def __init__(
            self,
            spec: dict,
            pics_dir: str = DEFAULT_PICS_DIR,
            sidebar_width: int = DEFAULT_SIDEBAR_WIDTH,
            interval: float = POLL_INTERVAL,
            aria_socket: str = ARIA_TMUX_SOCKET,
            window: ForgeWindow | None = None,
        ) -> None:
            super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            self.spec = dict(spec)
            self.title = spec.get("title", "Quadrant")
            self.agent = spec.get("agent", "Dushich")
            self.helper_agent = spec.get("helper_agent", "")
            self.command = list(spec.get("command") or ["bash"])
            self.explicit_badge = spec.get("badge", "")
            self.pics = Path(pics_dir)
            self.sidebar_width = int(sidebar_width)
            self.interval = float(interval)
            self.aria_socket = aria_socket
            self.window = window

            self.tracker = StateTracker()
            self.helper_tracker = StateTracker() if self.helper_agent else None
            self.frame = "idle"
            self.helper_frame = "idle" if self.helper_agent else None
            self.tick = 0
            self._pixbuf_cache: dict = {}
            self._poll_id = None
            self.is_maximized = False

            # Token badge resolution
            self.token_badge = resolve_token_badge(self.agent, self.explicit_badge)

            # ---- header bar -----------------------------------------------
            self.header_event = Gtk.EventBox()
            self.header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            self.header_box.set_margin_start(8)
            self.header_box.set_margin_end(6)
            self.header_box.set_margin_top(3)
            self.header_box.set_margin_bottom(3)

            self.status_dot = Gtk.Label(label="●")
            self.status_dot.override_color(
                Gtk.StateFlags.NORMAL, Gdk.RGBA(0.3, 0.35, 0.4, 1.0)
            )

            self.title_label = Gtk.Label(label=self.title)
            self.title_label.set_halign(Gtk.Align.START)
            self.title_label.set_hexpand(True)
            self.title_label.override_color(
                Gtk.StateFlags.NORMAL, Gdk.RGBA(0.8, 0.85, 0.9, 1.0)
            )

            self.zoom_btn = Gtk.Button(label="⛶")
            self.zoom_btn.set_relief(Gtk.ReliefStyle.NONE)
            self.zoom_btn.set_tooltip_text("Zoom Quadrant (Ctrl+Shift+Z or F11)")
            self.zoom_btn.connect("clicked", self._on_zoom_btn_clicked)

            self.header_box.pack_start(self.status_dot, False, False, 0)
            self.header_box.pack_start(self.title_label, True, True, 0)
            self.header_box.pack_start(self.zoom_btn, False, False, 0)
            self.header_event.add(self.header_box)
            self.header_event.connect("button-press-event", self._on_header_button_press)

            # ---- content box: terminal + scrollbar + avatar sidebar --------
            self.content_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
            self.content_box.set_hexpand(True)
            self.content_box.set_vexpand(True)

            # ---- terminal -------------------------------------------------
            self.term = Vte.Terminal()
            self.term.set_hexpand(True)
            self.term.set_vexpand(True)
            self.term.set_scrollback_lines(50000)
            self.term.set_font(Pango.FontDescription("Monospace 11"))
            bg = Gdk.RGBA()
            bg.parse(BACKGROUND)
            fg = Gdk.RGBA()
            fg.parse(FOREGROUND)
            self.term.set_color_foreground(fg)
            self.term.set_color_background(bg)
            self.term.connect("key-press-event", self._on_key_press)
            self.term.connect("child-exited", self._on_child_exited)

            # Reconnect overlay container
            self.term_overlay = Gtk.Overlay()
            self.term_overlay.set_hexpand(True)
            self.term_overlay.set_vexpand(True)
            self.term_overlay.add(self.term)

            # Clean exit overlay card
            self.reconnect_box = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL, spacing=8
            )
            self.reconnect_box.set_no_show_all(True)
            self.reconnect_box.set_halign(Gtk.Align.CENTER)
            self.reconnect_box.set_valign(Gtk.Align.CENTER)
            self.reconnect_box.set_margin_start(24)
            self.reconnect_box.set_margin_end(24)
            self.reconnect_box.set_margin_top(16)
            self.reconnect_box.set_margin_bottom(16)

            self.reconnect_label = Gtk.Label(label="⚠️ Session terminated")
            self.reconnect_label.override_color(
                Gtk.StateFlags.NORMAL, Gdk.RGBA(0.9, 0.8, 0.4, 1.0)
            )
            self.reconnect_btn = Gtk.Button(label="↺ Reconnect / Respawn")
            self.reconnect_btn.connect("clicked", self._on_reconnect_clicked)

            self.reconnect_box.pack_start(self.reconnect_label, False, False, 0)
            self.reconnect_box.pack_start(self.reconnect_btn, False, False, 0)
            self.term_overlay.add_overlay(self.reconnect_box)
            self.reconnect_box.hide()

            # ---- scrollbar ------------------------------------------------
            self.scrollbar = Gtk.Scrollbar(
                orientation=Gtk.Orientation.VERTICAL,
                adjustment=self.term.get_vadjustment(),
            )
            self.scrollbar.set_hexpand(False)
            self.scrollbar.set_vexpand(True)

            # ---- avatar sidebar ------------------------------------------
            self.drawing_area = Gtk.DrawingArea()
            self.drawing_area.set_size_request(self.sidebar_width, -1)
            self.drawing_area.set_hexpand(False)
            self.drawing_area.set_vexpand(True)
            self.drawing_area.connect("draw", self._on_draw)

            self.content_box.pack_start(self.term_overlay, True, True, 0)
            self.content_box.pack_start(self.scrollbar, False, True, 0)
            self.content_box.pack_start(self.drawing_area, False, True, 0)

            self.pack_start(self.header_event, False, False, 0)
            self.pack_start(self.content_box, True, True, 0)

        # -- zoom & header events ------------------------------------------
        def _on_zoom_btn_clicked(self, _btn) -> None:
            if self.window is not None:
                self.window.toggle_maximize(self)

        def _on_header_button_press(self, _widget, event) -> bool:
            if event.type == Gdk.EventType._2BUTTON_PRESS:
                if self.window is not None:
                    self.window.toggle_maximize(self)
                return True
            return False

        def set_zoom_state(self, is_maximized: bool) -> None:
            self.is_maximized = is_maximized
            if is_maximized:
                self.zoom_btn.set_label("❐")
                self.zoom_btn.set_tooltip_text("Restore Grid (Ctrl+Shift+Z or Escape)")
            else:
                self.zoom_btn.set_label("⛶")
                self.zoom_btn.set_tooltip_text("Zoom Quadrant (Ctrl+Shift+Z or F11)")

        # -- clipboard & zoom shortcut --------------------------------------
        def _on_key_press(self, _term, event) -> bool:
            mask = Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK
            if (event.state & mask) == mask:
                key = event.keyval
                if key in (Gdk.KEY_c, Gdk.KEY_C):
                    self.term.copy_clipboard_format(Vte.Format.TEXT)
                    return True
                if key in (Gdk.KEY_v, Gdk.KEY_V):
                    self.term.paste_clipboard()
                    return True
                if key in (Gdk.KEY_z, Gdk.KEY_Z):
                    if self.window is not None:
                        self.window.toggle_maximize(self)
                    return True
            if event.keyval in (Gdk.KEY_F11,):
                if self.window is not None:
                    self.window.toggle_maximize(self)
                return True
            return False

        # -- terminal lifecycle & reconnect --------------------------------
        def _on_child_exited(self, _term, status) -> None:
            self.reconnect_label.set_text(f"Session terminated (code {status})")
            self.reconnect_box.show_all()
            if self.agent and status != 0:
                GLib.timeout_add(2000, self._auto_respawn_if_visible)
                return
            if self._poll_id is not None:
                GLib.source_remove(self._poll_id)
                self._poll_id = None

        def _auto_respawn_if_visible(self) -> bool:
            if self.reconnect_box.get_visible():
                self.spawn()
            return False

        def _on_reconnect_clicked(self, _btn) -> None:
            self.spawn()

        def spawn(self) -> None:
            """Launch the quadrant's command in the terminal (via idle)."""
            self.reconnect_box.hide()
            argv = self.command or ["bash"]

            def _do_spawn() -> bool:
                self.term.spawn_async(
                    Vte.PtyFlags.DEFAULT,
                    None,
                    argv,
                    None,
                    GLib.SpawnFlags.DEFAULT,
                    None,
                    None,
                    -1,
                    None,
                    None,
                )
                self.start_polling()
                return False

            GLib.idle_add(_do_spawn)

        def start_polling(self) -> None:
            """Begin the 0.4s state-poll loop (call once per panel)."""
            if self._poll_id is None:
                self._poll_id = GLib.timeout_add(
                    int(self.interval * 1000), self.poll
                )

        # -- pixbuf helpers -------------------------------------------------
        def _get_pixbuf(self, path: str, w: int, h: int):
            key = (str(path), w, h)
            if key not in self._pixbuf_cache:
                self._pixbuf_cache[key] = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                    str(path), w, h, False
                )
            return self._pixbuf_cache[key]

        # -- state polling --------------------------------------------------
        def poll(self) -> bool:
            now = time.monotonic()
            try:
                text = self.term.get_text_format(Vte.Format.TEXT) or ""
            except Exception:
                text = ""
            title = self.term.get_window_title() or ""

            aria_working = helper_tmux_working = False
            if self.agent == "Aria" and self.aria_socket:
                try:
                    aria_working, helper_tmux_working = read_aria_tmux_state(
                        self.aria_socket
                    )
                except Exception:
                    aria_working = helper_tmux_working = False

            banshee_working = False
            if self.agent == "Banshee":
                try:
                    banshee_working, b_helper = read_banshee_tmux_state(
                        self.aria_socket
                    )
                    helper_tmux_working = helper_tmux_working or b_helper
                except Exception:
                    banshee_working = False

            gwyn_working = False
            if self.agent == "Gwyn":
                try:
                    gwyn_working, g_helper = read_gwyn_tmux_state(
                        self.aria_socket
                    )
                    helper_tmux_working = helper_tmux_working or g_helper
                except Exception:
                    gwyn_working = False

            dushich_working = False
            if self.agent == "Dushich":
                try:
                    dushich_working = read_dushich_solo_tmux_state()
                except Exception:
                    dushich_working = False

            primary_working = (
                is_pane_working(text, title)
                or aria_working
                or banshee_working
                or dushich_working
                or gwyn_working
            )

            # Update status dot in header bar
            if primary_working:
                self.status_dot.override_color(
                    Gtk.StateFlags.NORMAL, Gdk.RGBA(0.25, 0.85, 0.4, 1.0)
                )
            else:
                self.status_dot.override_color(
                    Gtk.StateFlags.NORMAL, Gdk.RGBA(0.3, 0.35, 0.4, 1.0)
                )

            new_frame = select_frame_name(
                self.tracker.update(primary_working, now), self.tick
            )
            changed = new_frame != self.frame
            self.frame = new_frame

            if self.helper_agent and self.helper_tracker is not None:
                helper_working = is_dushich_helper_working(text, title)
                if self.agent in ("Aria", "Banshee", "Gwyn"):
                    helper_working = helper_working or helper_tmux_working
                h_frame = select_frame_name(
                    self.helper_tracker.update(helper_working, now), self.tick
                )
                changed = changed or h_frame != self.helper_frame
                self.helper_frame = h_frame

            # Periodically refresh token quota badge (every ~10 ticks = 4s)
            if self.tick % 10 == 0:
                new_badge = resolve_token_badge(self.agent, self.explicit_badge)
                if new_badge != self.token_badge:
                    self.token_badge = new_badge
                    changed = True

            self.tick += 1
            if changed:
                self.drawing_area.queue_draw()
            return True

        # -- sidebar rendering with token quota badge -----------------------
        def _on_draw(self, area, cr):
            width = max(1, area.get_allocated_width())
            height = max(1, area.get_allocated_height())
            if not self.agent:
                if ROSE_PATH.exists():
                    rose = self._get_pixbuf(str(ROSE_PATH), width, height)
                    Gdk.cairo_set_source_pixbuf(cr, rose, 0, 0)
                    cr.paint()
                return False

            has_helper = bool(self.helper_agent)
            layout = compute_sidebar_layout(
                width, height, aspect_ratio=ASPECT_RATIO, has_helper=has_helper
            )
            y = 0
            panels = [("top_h", "top_w", self.frame, self.agent)]
            if self.helper_agent:
                panels.append(
                    ("helper_h", "helper_w", self.helper_frame, self.helper_agent)
                )
            for h_key, w_key, frame, agent in panels:
                panel_h = layout[h_key]
                if agent and panel_h > 0:
                    png = self.pics / agent / f"{frame}.png"
                    if png.exists():
                        pixbuf = self._get_pixbuf(
                            str(png), layout[w_key], panel_h
                        )
                        Gdk.cairo_set_source_pixbuf(cr, pixbuf, 0, y)
                        cr.paint()
                        y += panel_h

            bottom_h = layout["bottom_h"]
            if bottom_h > 0:
                # Render token quota badge directly above Rose on a compact line
                badge_h = 20 if bottom_h >= 26 else 0
                if badge_h > 0:
                    badge_text = self.token_badge or "H/W: --% / --%"

                    # Badge container card/pill
                    cr.save()
                    cr.set_source_rgba(0.08, 0.10, 0.13, 0.95)
                    cr.rectangle(2, y + 1, width - 4, badge_h - 2)
                    cr.fill_preserve()
                    cr.set_source_rgba(0.20, 0.24, 0.29, 0.9)
                    cr.set_line_width(1.0)
                    cr.stroke()

                    # Render text using Pango layout
                    pango_layout = PangoCairo.create_layout(cr)
                    font_desc = Pango.FontDescription("Monospace Bold 8")
                    pango_layout.set_font_description(font_desc)
                    pango_layout.set_text(badge_text, -1)
                    _, extents = pango_layout.get_pixel_extents()

                    tx = max(4, (width - extents.width) // 2)
                    ty = y + max(1, (badge_h - extents.height) // 2)

                    if "100%" in badge_text and "Local" in badge_text:
                        cr.set_source_rgb(0.25, 0.85, 0.4)  # green
                    elif "%" in badge_text and "--" not in badge_text:
                        cr.set_source_rgb(0.35, 0.65, 0.95)  # blue
                    else:
                        cr.set_source_rgb(0.55, 0.60, 0.66)  # dim gray

                    cr.move_to(tx, ty)
                    PangoCairo.show_layout(cr, pango_layout)
                    cr.restore()

                    y += badge_h
                    bottom_h -= badge_h

                if bottom_h > 0 and ROSE_PATH.exists():
                    rose = self._get_pixbuf(
                        str(ROSE_PATH), layout["bottom_w"], bottom_h
                    )
                    Gdk.cairo_set_source_pixbuf(cr, rose, 0, y)
                    cr.paint()
            return False

    class ForgeWindow(Gtk.Window):
        """Top-level Nexus Forge window managing 2x2 grid & quadrant zoom."""

        def __init__(
            self,
            title: str,
            quadrants: dict,
            pics_dir: str = DEFAULT_PICS_DIR,
            sidebar_width: int = DEFAULT_SIDEBAR_WIDTH,
            interval: float = POLL_INTERVAL,
            aria_socket: str = ARIA_TMUX_SOCKET,
            left_only: bool = False,
        ) -> None:
            super().__init__(title=title)
            self.base_title = title
            self.left_only = left_only
            self.maximized_panel: QuadrantPanel | None = None
            self.panels: dict[str, QuadrantPanel] = {}

            self.set_default_size(1600, 960)
            self.maximize()
            self.connect("destroy", Gtk.main_quit)
            self.connect("key-press-event", self._on_window_key_press)

            names = quadrant_names(left_only=left_only)
            for name in names:
                panel = QuadrantPanel(
                    quadrants.get(name, DEFAULT_QUADRANTS.get(name, {})),
                    pics_dir=pics_dir,
                    sidebar_width=sidebar_width,
                    interval=interval,
                    aria_socket=aria_socket,
                    window=self,
                )
                panel.set_hexpand(True)
                panel.set_vexpand(True)
                self.panels[name] = panel

            self.grid = Gtk.Grid()
            self.grid.set_row_homogeneous(True)
            self.grid.set_column_homogeneous(True)
            self.grid.set_row_spacing(4)
            self.grid.set_column_spacing(4)

            if left_only:
                self.grid.attach(self.panels["top_left"], 0, 0, 1, 1)
                self.grid.attach(self.panels["bottom_left"], 0, 1, 1, 1)
            else:
                self.grid.attach(self.panels["top_left"], 0, 0, 1, 1)
                self.grid.attach(self.panels["bottom_left"], 0, 1, 1, 1)
                self.grid.attach(self.panels["top_right"], 1, 0, 1, 1)
                self.grid.attach(self.panels["bottom_right"], 1, 1, 1, 1)

            self.add(self.grid)

        def _on_window_key_press(self, _win, event) -> bool:
            mask = Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK
            if (event.state & mask) == mask and event.keyval in (Gdk.KEY_z, Gdk.KEY_Z):
                self.toggle_maximize()
                return True
            if event.keyval in (Gdk.KEY_F11,):
                self.toggle_maximize()
                return True
            if event.keyval in (Gdk.KEY_Escape,) and self.maximized_panel is not None:
                self.toggle_maximize()
                return True
            return False

        def toggle_maximize(self, panel: QuadrantPanel | None = None) -> None:
            """Toggle full-window zoom for the given (or focused) quadrant."""
            if self.maximized_panel is not None:
                # Restore to 2x2 grid
                self.grid.set_row_homogeneous(True)
                self.grid.set_column_homogeneous(True)
                for p in self.panels.values():
                    p.show_all()
                    p.set_zoom_state(False)
                self.set_title(self.base_title)
                self.maximized_panel = None
            else:
                target = panel
                if target is None:
                    # Find focused panel among visible quadrants
                    for p in self.panels.values():
                        if p.has_focus() or p.term.has_focus():
                            target = p
                            break
                if target is None:
                    target = next(iter(self.panels.values()), None)
                if target is None:
                    return

                self.grid.set_row_homogeneous(False)
                self.grid.set_column_homogeneous(False)
                for p in self.panels.values():
                    if p is not target:
                        p.hide()
                target.set_zoom_state(True)
                self.maximized_panel = target
                self.set_title(
                    f"{self.base_title} - [{target.title}] (Ctrl+Shift+Z or Escape to restore)"
                )

        def start(self) -> None:
            for panel in self.panels.values():
                panel.spawn()
                panel.start_polling()
            self.show_all()

else:  # pragma: no cover - GTK unavailable

    class QuadrantPanel:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            raise RuntimeError(
                "GTK3/VTE is not available; nexus-forge GUI cannot start: "
                f"{_GI_IMPORT_ERROR!r}"
            )

    class ForgeWindow:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            raise RuntimeError(
                "GTK3/VTE is not available; nexus-forge GUI cannot start: "
                f"{_GI_IMPORT_ERROR!r}"
            )


# ---------------------------------------------------------------------------
# Headless self-test: verify the quadrant table, config loader, badge logic,
# layout math, and agent/Rose pixbuf + Cairo text paints.
# ---------------------------------------------------------------------------
def _verify_quadrants() -> None:
    assert set(DEFAULT_QUADRANTS) == {
        "top_left", "bottom_left", "top_right", "bottom_right"
    }
    tl = DEFAULT_QUADRANTS["top_left"]
    assert tl["title"] == "Aria + Dushich Helper"
    assert tl["agent"] == "Aria" and tl["helper_agent"] == ""
    bl = DEFAULT_QUADRANTS["bottom_left"]
    assert bl["title"] == "Dushich Solo"
    assert bl["agent"] == "Dushich" and bl["helper_agent"] == ""
    tr = DEFAULT_QUADRANTS["top_right"]
    assert tr["title"] == "Banshee + Dushich Helper"
    assert tr["agent"] == "Banshee" and tr["helper_agent"] == ""
    br = DEFAULT_QUADRANTS["bottom_right"]
    assert br["title"] == "Gwyn + Dushich Helper"
    assert br["agent"] == "Gwyn" and br["helper_agent"] == ""
    for name, spec in DEFAULT_QUADRANTS.items():
        assert isinstance(spec["command"], list) and spec["command"], name
        assert spec["agent"] in ("", "Aria", "Banshee", "Dushich", "Gwyn"), name
        assert spec["helper_agent"] == "", name
    assert quadrant_names(left_only=True) == ["top_left", "bottom_left"]
    assert len(quadrant_names()) == 4


def _verify_layout() -> None:
    for has_helper in (False, True):
        for total_height in (0, 1, 2, 140, 180, 320, 480, 720, 1000):
            layout = compute_sidebar_layout(
                DEFAULT_SIDEBAR_WIDTH, total_height,
                aspect_ratio=ASPECT_RATIO, has_helper=has_helper,
            )
            assert layout["top_w"] == max(1, DEFAULT_SIDEBAR_WIDTH)
            assert layout["top_h"] >= 1
            if has_helper:
                assert layout["helper_h"] >= 1
            if total_height >= 2:
                used = layout["top_h"]
                if has_helper:
                    used += layout["helper_h"]
                used += layout["bottom_h"]
                assert used == total_height, (has_helper, total_height, layout)


def _verify_token_badge() -> None:
    # Explicit badge takes top precedence
    assert resolve_token_badge("Aria", explicit_badge="Custom: 42%") == "Custom: 42%"
    # Dushich Solo is local
    assert resolve_token_badge("Dushich") == "Local: 100%"
    # Unknown agent falls back gracefully
    assert resolve_token_badge("UnknownAgent") == "H/W: --% / --%"


def _verify_config_loader() -> None:
    # Empty / none returns default
    quads = build_quadrants_table(None)
    assert set(quads) == {"top_left", "bottom_left", "top_right", "bottom_right"}
    # Override top_left
    custom_cfg = {
        "quadrants": {
            "top_left": {
                "title": "Custom Shell",
                "command": ["/bin/zsh"],
                "badge": "H/W: 10% / 20%",
            }
        }
    }
    merged = build_quadrants_table(custom_cfg)
    assert merged["top_left"]["title"] == "Custom Shell"
    assert merged["top_left"]["command"] == ["/bin/zsh"]
    assert merged["top_left"]["badge"] == "H/W: 10% / 20%"
    assert merged["bottom_left"]["title"] == "Dushich Solo"


def _self_test(args: argparse.Namespace) -> int:
    """Headless smoke test: quadrant table, config loader, badges, layout, pixbufs + Cairo."""
    if not _GI_AVAILABLE:
        print("self-test FAILED: GTK3/PyGObject not importable", file=sys.stderr)
        return 1
    import gi  # noqa: F401

    gi.require_version("Gdk", "3.0")
    gi.require_version("GdkPixbuf", "2.0")
    gi.require_version("PangoCairo", "1.0")
    from gi.repository import GdkPixbuf, Gdk, Pango, PangoCairo

    import cairo

    _verify_quadrants()
    _verify_layout()
    _verify_token_badge()
    _verify_config_loader()

    pics = Path(args.pics_dir)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 140, 400)
    ctx = cairo.Context(surface)
    last = None
    for agent in ("Aria", "Banshee", "Dushich", "Gwyn"):
        for frame in REQUIRED_FRAMES:
            png = pics / agent / f"{frame}.png"
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(png), 140, 210, False)
            assert isinstance(pixbuf, GdkPixbuf.Pixbuf), str(png)
            assert (pixbuf.get_width(), pixbuf.get_height()) == (140, 210)
            last = pixbuf
    assert last is not None
    rose = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(ROSE_PATH), 140, 300, False)
    assert isinstance(rose, GdkPixbuf.Pixbuf), str(ROSE_PATH)

    # Paint avatar, token badge, and Rose into off-screen surface
    ctx.save()
    Gdk.cairo_set_source_pixbuf(ctx, last, 0, 0)
    ctx.paint()

    # Draw badge pill
    y = 210
    width = 140
    badge_h = 20
    ctx.set_source_rgba(0.08, 0.10, 0.13, 0.95)
    ctx.rectangle(2, y + 1, width - 4, badge_h - 2)
    ctx.fill_preserve()
    ctx.set_source_rgba(0.20, 0.24, 0.29, 0.9)
    ctx.set_line_width(1.0)
    ctx.stroke()

    # Draw text via PangoCairo
    pango_layout = PangoCairo.create_layout(ctx)
    pango_layout.set_font_description(Pango.FontDescription("Monospace Bold 8"))
    pango_layout.set_text("H/W: 100% / 64%", -1)
    ctx.set_source_rgb(0.35, 0.65, 0.95)
    ctx.move_to(10, y + 3)
    PangoCairo.show_layout(ctx, pango_layout)

    # Draw Rose below badge
    Gdk.cairo_set_source_pixbuf(ctx, rose, 0, y + badge_h)
    ctx.paint()
    ctx.restore()

    print("self-test OK")
    return 0


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------
def _run_gui(args: argparse.Namespace) -> int:
    uid = os.getuid()
    runtime_dir = os.environ.setdefault("XDG_RUNTIME_DIR", f"/run/user/{uid}")
    if not os.environ.get("WAYLAND_DISPLAY") and Path(f"{runtime_dir}/wayland-0").exists():
        os.environ["WAYLAND_DISPLAY"] = "wayland-0"
    os.environ.setdefault("DISPLAY", ":0")
    if not _GI_AVAILABLE:
        print(
            "nexus-forge requires GTK3 + VTE 2.91 (python3-gi, python3-gi-cairo).",
            file=sys.stderr,
        )
        return 1

    cfg = load_config(args.config)
    quadrants = build_quadrants_table(cfg)

    title = args.title or cfg.get("title", "nexus-forge")
    pics_dir = args.pics_dir or cfg.get("pics_dir", DEFAULT_PICS_DIR)
    sidebar_width = args.sidebar_width or cfg.get("sidebar_width", DEFAULT_SIDEBAR_WIDTH)
    interval = args.interval or cfg.get("interval", POLL_INTERVAL)
    aria_socket = args.aria_socket or cfg.get("aria_socket", ARIA_TMUX_SOCKET)

    window = ForgeWindow(
        title=title,
        quadrants=quadrants,
        pics_dir=pics_dir,
        sidebar_width=sidebar_width,
        interval=interval,
        aria_socket=aria_socket,
        left_only=args.left_only,
    )
    window.start()
    Gtk.main()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="nexus-forge: multi-terminal GTK3+VTE window for Noobia agents."
    )
    parser.add_argument("--title", default=None)
    parser.add_argument("--pics-dir", default=None)
    parser.add_argument("--sidebar-width", type=int, default=None)
    parser.add_argument("--interval", type=float, default=None)
    parser.add_argument(
        "--aria-socket",
        default=None,
        help="tmux socket that hosts the noobia-aria-* sessions",
    )
    parser.add_argument(
        "--left-only",
        action="store_true",
        help="show only the two left quadrants (Aria+Dushich, Dushich Solo)",
    )
    parser.add_argument(
        "--config",
        "-c",
        default=None,
        help="path to custom JSON configuration file",
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        if args.pics_dir is None:
            args.pics_dir = DEFAULT_PICS_DIR
        return _self_test(args)
    return _run_gui(args)


if __name__ == "__main__":
    sys.exit(main())
