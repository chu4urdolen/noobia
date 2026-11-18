#!/usr/bin/env python3
"""nexus-forge: a multi-terminal GTK3 + VTE 2.91 window for Noobia agents.

A 2x2 resizable grid of quadrants, each pairing a live terminal with an
animated avatar sidebar.  The quadrants:

    top-left     Aria + Dushich Helper   (Aria codex, Dushich helper)
    bottom-left  Dushich Solo            (dushich, no helper)
    top-right    Banshee + Dushich Helper (banshee, Dushich helper)
    bottom-right Nexus Shell             (bare interactive shell)

Every quadrant reuses the pure helpers from `avatar_pane` / `dushich_window`
(`StateTracker`, `is_pane_working`, `select_frame_name`,
`compute_sidebar_layout`, `is_dushich_helper_working`, ...).  The sidebar
draws the primary agent frame on top, an optional helper-agent frame in the
middle, and `Rose.png` filling any remaining height at the bottom via the
4-argument `Gdk.cairo_set_source_pixbuf(cr, pixbuf, 0, y)` call.

State is driven by polling each terminal's live text + window title (plus
`tmux list-panes`/`capture-pane` for `noobia-aria-*` sessions when the
quadrant's agent is Aria) every 0.4s.

Run `nexus_forge.py --self-test` for a headless smoke test of the quadrant
table, the sidebar layout math, and every agent/Rose pixbuf + Cairo paint.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
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
    from gi.repository import Gtk, Vte, Gdk, GdkPixbuf, GLib, Pango

    _GI_AVAILABLE = True
except Exception as _gi_import_error:  # pragma: no cover - environment specific
    Gtk = None
    Vte = None
    Gdk = None
    GdkPixbuf = None
    GLib = None
    Pango = None
    _GI_AVAILABLE = False
    _GI_IMPORT_ERROR = _gi_import_error


ASPECT_RATIO = 1.5
DEFAULT_SIDEBAR_WIDTH = 140
POLL_INTERVAL = 0.4
BACKGROUND = "#121417"
FOREGROUND = "#e6edf3"
ARIA_TMUX_SOCKET = "default"

# ---------------------------------------------------------------------------
# The quadrant table: which agent, optional helper, and launch command each
# of the four quadrants runs.  Pure data -- no GTK required.
# ---------------------------------------------------------------------------
DEFAULT_QUADRANTS = {
    "top_left": {
        "title": "Aria + Dushich Helper",
        "agent": "Aria",
        "helper_agent": "",
        "command": [
            "/bin/bash",
            "-lc",
            "s=$(tmux list-sessions -F '#{session_name}:#{session_attached}' 2>/dev/null | awk -F: '/^noobia-aria-.*:0$/{print $1; exit}'); if [ -n \"$s\" ]; then exec tmux attach-session -t \"$s\"; fi; NOOBIA_ARIA_NO_GUI=1 exec /noobia/aria/codex-with-dushich",
        ],
    },
    "bottom_left": {
        "title": "Dushich Solo",
        "agent": "Dushich",
        "helper_agent": "",
        "command": [
            "/bin/bash",
            "-lc",
            "for _ in $(seq 1 40); do /usr/bin/curl -fsS --max-time 1 http://127.0.0.1:11434/api/version >/dev/null 2>&1 && break; sleep 0.5; done; s=$(tmux -Ldushich-clean list-sessions -F '#{session_name}:#{session_attached}' 2>/dev/null | awk -F: '/^noobia-dushich-solo-.*:0$/{print $1; exit}'); if [ -n \"$s\" ]; then exec tmux -Ldushich-clean attach-session -t \"$s\"; fi; exec /noobia/dushich/solo/launch",
        ],
    },
    "top_right": {
        "title": "Banshee + Dushich Helper",
        "agent": "Banshee",
        "helper_agent": "",
        "command": [
            "/bin/bash",
            "-lc",
            "s=$(tmux list-sessions -F '#{session_name}:#{session_attached}' 2>/dev/null | awk -F: '/^noobia-banshee-.*:0$/{print $1; exit}'); if [ -n \"$s\" ]; then exec tmux attach-session -t \"$s\"; fi; exec /noobia/banshee/launch",
        ],
    },
    "bottom_right": {
        "title": "Gwyn App Nub",
        "agent": "Gwyn",
        "helper_agent": "",
        "command": ["/bin/bash", "-lc", "exec /noobia/gwyn-app-nub/launch"],
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


def read_aria_tmux_state(socket: str = ARIA_TMUX_SOCKET) -> tuple:
    """Read the live Aria tmux session (``noobia-aria-*``) off-screen.

    Returns a ``(aria_working, dushich_helper_working)`` tuple derived from
    the two panes of the most recent ``noobia-aria-*`` session.  Panes are
    located with ``tmux list-panes`` and read with ``capture-pane``.  Any
    error (no tmux, no session, not attached) yields ``(False, False)`` so
    callers can simply OR this with their local terminal state.
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
    # Most recently created session is the one we are wrapping.
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
            # Fall back to pane position (0 = Aria, 1 = Dushich helper).
            if index == "0":
                aria_text, aria_title = text, title
            elif index == "1":
                helper_text, helper_title = text, title
    aria_working = is_pane_working(aria_text, aria_title)
    helper_working = is_dushich_helper_working(helper_text, helper_title)
    return aria_working, helper_working


def read_banshee_tmux_state(socket: str = "default") -> tuple:
    """Read the live Banshee tmux session (``noobia-banshee-*``) off-screen.

    Returns a ``(banshee_working, dushich_helper_working)`` tuple derived from
    the two panes of the most recent ``noobia-banshee-*`` session.
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
    banshee_sessions = [
        line.strip()
        for line in out.splitlines()
        if line.strip().startswith("noobia-banshee-")
    ]
    if not banshee_sessions:
        return False, False
    session = banshee_sessions[-1]
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

    banshee_text = banshee_title = helper_text = helper_title = ""
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
        if "banshee" in title.lower() or "antigravity" in title.lower() or index == "0":
            banshee_text, banshee_title = text, title
        elif "dushich" in title.lower() or index == "1":
            helper_text, helper_title = text, title
    banshee_working = is_pane_working(banshee_text, banshee_title)
    helper_working = is_dushich_helper_working(helper_text, helper_title)
    return banshee_working, helper_working


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
        """One terminal + animated avatar sidebar, laid out horizontally."""

        def __init__(
            self,
            spec: dict,
            pics_dir: str = DEFAULT_PICS_DIR,
            sidebar_width: int = DEFAULT_SIDEBAR_WIDTH,
            interval: float = POLL_INTERVAL,
            aria_socket: str = ARIA_TMUX_SOCKET,
        ) -> None:
            Gtk.Box.__init__(self, orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
            self.spec = dict(spec)
            self.title = spec.get("title", "Quadrant")
            self.agent = spec.get("agent", "Dushich")
            self.helper_agent = spec.get("helper_agent", "")
            self.command = list(spec.get("command") or ["bash"])
            self.pics = Path(pics_dir)
            self.sidebar_width = int(sidebar_width)
            self.interval = float(interval)
            self.aria_socket = aria_socket

            self.tracker = StateTracker()
            self.helper_tracker = StateTracker() if self.helper_agent else None
            self.frame = "idle"
            self.helper_frame = "idle" if self.helper_agent else None
            self.tick = 0
            self._pixbuf_cache: dict = {}
            self._poll_id = None

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

            self.pack_start(self.term, True, True, 0)
            self.pack_start(self.scrollbar, False, True, 0)
            self.pack_start(self.drawing_area, False, True, 0)

        # -- clipboard ------------------------------------------------------
        def _on_key_press(self, _term, event) -> bool:
            mask = Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK
            if event.state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK) == mask:
                key = event.keyval
                if key in (Gdk.KEY_c, Gdk.KEY_C):
                    self.term.copy_clipboard_format(Vte.Format.TEXT)
                    return True
                if key in (Gdk.KEY_v, Gdk.KEY_V):
                    self.term.paste_clipboard()
                    return True
            return False

        # -- terminal lifecycle --------------------------------------------
        def _on_child_exited(self, _term, status) -> None:
            if self.agent and status != 0:
                GLib.timeout_add(1500, self._respawn)
                return
            if self._poll_id is not None:
                GLib.source_remove(self._poll_id)
                self._poll_id = None

        def _respawn(self) -> bool:
            self.spawn()
            return False

        def spawn(self) -> None:
            """Launch the quadrant's command in the terminal (via idle)."""
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
            )
            new_frame = select_frame_name(
                self.tracker.update(primary_working, now), self.tick
            )
            changed = new_frame != self.frame
            self.frame = new_frame

            if self.helper_agent and self.helper_tracker is not None:
                helper_working = is_dushich_helper_working(text, title)
                if self.agent in ("Aria", "Banshee"):
                    helper_working = helper_working or helper_tmux_working
                h_frame = select_frame_name(
                    self.helper_tracker.update(helper_working, now), self.tick
                )
                changed = changed or h_frame != self.helper_frame
                self.helper_frame = h_frame

            self.tick += 1
            if changed:
                self.drawing_area.queue_draw()
            return True

        # -- sidebar rendering ---------------------------------------------
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
                panels.append(("helper_h", "helper_w", self.helper_frame, self.helper_agent))
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
            if layout["bottom_h"] > 0 and ROSE_PATH.exists():
                rose = self._get_pixbuf(
                    str(ROSE_PATH), layout["bottom_w"], layout["bottom_h"]
                )
                Gdk.cairo_set_source_pixbuf(cr, rose, 0, y)
                cr.paint()
            return False
else:  # pragma: no cover - GTK unavailable

    class QuadrantPanel:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            raise RuntimeError(
                "GTK3/VTE is not available; nexus-forge GUI cannot start: "
                f"{_GI_IMPORT_ERROR!r}"
            )


# ---------------------------------------------------------------------------
# Headless self-test: verify the quadrant table, the layout math, and every
# agent/Rose pixbuf + a Cairo paint (off-screen, no display required).
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
    assert br["title"] == "Gwyn App Nub"
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
            # A real sidebar (>=2px) is filled exactly with no wasted rows.
            if total_height >= 2:
                used = layout["top_h"]
                if has_helper:
                    used += layout["helper_h"]
                used += layout["bottom_h"]
                assert used == total_height, (has_helper, total_height, layout)


def _self_test(args: argparse.Namespace) -> int:
    """Headless smoke test: quadrant table, layout math, pixbufs + Cairo."""
    if not _GI_AVAILABLE:
        print("self-test FAILED: GTK3/PyGObject not importable", file=sys.stderr)
        return 1
    import gi  # noqa: F401

    gi.require_version("Gdk", "3.0")
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf, Gdk

    import cairo

    _verify_quadrants()
    _verify_layout()

    pics = Path(args.pics_dir)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 10, 10)
    ctx = cairo.Context(surface)
    last = None
    for agent in ("Aria", "Banshee", "Dushich"):
        for frame in REQUIRED_FRAMES:
            png = pics / agent / f"{frame}.png"
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(png), 140, 210, False)
            assert isinstance(pixbuf, GdkPixbuf.Pixbuf), str(png)
            assert (pixbuf.get_width(), pixbuf.get_height()) == (140, 210)
            last = pixbuf
    assert last is not None
    rose = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(ROSE_PATH), 140, 300, False)
    assert isinstance(rose, GdkPixbuf.Pixbuf), str(ROSE_PATH)

    ctx.save()
    Gdk.cairo_set_source_pixbuf(ctx, last, 0, 0)
    ctx.paint()
    Gdk.cairo_set_source_pixbuf(ctx, rose, 0, 100)
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

    names = quadrant_names(left_only=args.left_only)
    window = Gtk.Window(title=args.title)
    window.set_default_size(1600, 960)
    window.maximize()
    window.connect("destroy", Gtk.main_quit)

    panels = {}
    for name in names:
        panel = QuadrantPanel(
            DEFAULT_QUADRANTS[name],
            pics_dir=args.pics_dir,
            sidebar_width=args.sidebar_width,
            interval=args.interval,
            aria_socket=args.aria_socket,
        )
        panel.set_hexpand(True)
        panel.set_vexpand(True)
        panels[name] = panel

    grid = Gtk.Grid()
    grid.set_row_homogeneous(True)
    grid.set_column_homogeneous(True)
    grid.set_row_spacing(4)
    grid.set_column_spacing(4)

    if args.left_only:
        grid.attach(panels["top_left"], 0, 0, 1, 1)
        grid.attach(panels["bottom_left"], 0, 1, 1, 1)
    else:
        grid.attach(panels["top_left"], 0, 0, 1, 1)
        grid.attach(panels["bottom_left"], 0, 1, 1, 1)
        grid.attach(panels["top_right"], 1, 0, 1, 1)
        grid.attach(panels["bottom_right"], 1, 1, 1, 1)
    window.add(grid)

    for panel in panels.values():
        panel.spawn()
        panel.start_polling()

    window.show_all()
    Gtk.main()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="nexus-forge: multi-terminal GTK3+VTE window for Noobia agents."
    )
    parser.add_argument("--title", default="nexus-forge")
    parser.add_argument("--pics-dir", default=DEFAULT_PICS_DIR)
    parser.add_argument("--sidebar-width", type=int, default=DEFAULT_SIDEBAR_WIDTH)
    parser.add_argument("--interval", type=float, default=POLL_INTERVAL)
    parser.add_argument(
        "--aria-socket",
        default=ARIA_TMUX_SOCKET,
        help="tmux socket that hosts the noobia-aria-* sessions",
    )
    parser.add_argument(
        "--left-only",
        action="store_true",
        help="show only the two left quadrants (Aria+Dushich, Dushich Solo)",
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return _self_test(args)
    return _run_gui(args)


if __name__ == "__main__":
    sys.exit(main())
