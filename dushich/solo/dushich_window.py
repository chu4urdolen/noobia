#!/usr/bin/env python3
"""Solo Dushich GTK3 + VTE 2.91 native terminal & full-resolution avatar window.

Left side: a native Vte.Terminal (50,000-line scrollback, vertical scrollbar,
copy/paste shortcuts) running Solo Dushich.
Right side: a fixed-pixel-width sidebar (default 180px) rendering the current
1024x1536 Dushich status PNG (idle / working_1..4 / final for 2.0s) at full
native pixel resolution on top, with Rose.png filling the remaining height
below it. Smoothly rescales on any window resize, maximize, or unmaximize.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from avatar_pane import (
    DEFAULT_PICS_DIR,
    REQUIRED_FRAMES,
    ROSE_PATH,
    StateTracker,
    is_pane_working,
    read_pane_text,
    select_frame_name,
)

ASPECT_RATIO = 1.5


def compute_sidebar_layout(sidebar_width: int, total_height: int, aspect_ratio: float = 1.5) -> dict:
    """Split the sidebar height into top (Dushich) and bottom (Rose) areas."""
    top_w = max(1, sidebar_width)
    top_h = min(max(1, total_height), max(1, round(top_w * aspect_ratio)))
    bottom_h = max(0, total_height - top_h)
    return {"top_w": top_w, "top_h": top_h, "bottom_w": top_w, "bottom_h": bottom_h}


def ensure_display_env() -> None:
    """Ensure WAYLAND_DISPLAY / DISPLAY / XDG_RUNTIME_DIR are set for the local desktop."""
    uid = os.getuid()
    runtime_dir = os.environ.setdefault("XDG_RUNTIME_DIR", f"/run/user/{uid}")
    if not os.environ.get("WAYLAND_DISPLAY") and Path(f"{runtime_dir}/wayland-0").exists():
        os.environ["WAYLAND_DISPLAY"] = "wayland-0"
    os.environ.setdefault("DISPLAY", ":0")


def _self_test(args: argparse.Namespace) -> int:
    """Headless smoke test: layout math + load all frames as pixbufs."""
    gi = __import__("gi")
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf

    layout = compute_sidebar_layout(args.sidebar_width, 720)
    assert layout["top_w"] == args.sidebar_width
    assert layout["top_h"] + layout["bottom_h"] == 720

    frames_dir = Path(args.pics_dir) / args.agent
    for frame in REQUIRED_FRAMES:
        png = frames_dir / f"{frame}.png"
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(png), 180, 270, False)
        assert isinstance(pixbuf, GdkPixbuf.Pixbuf)
        assert (pixbuf.get_width(), pixbuf.get_height()) == (180, 270)
    rose = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(ROSE_PATH), 180, 300, False)
    assert isinstance(rose, GdkPixbuf.Pixbuf)
    print("self-test OK")
    return 0


def _run_gui(args: argparse.Namespace) -> int:
    ensure_display_env()
    gi = __import__("gi")
    gi.require_version("Gtk", "3.0")
    gi.require_version("Vte", "2.91")
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import Gtk, Vte, GdkPixbuf, GLib, Pango, Gdk

    state = {
        "tracker": StateTracker(),
        "frame": "idle",
        "tick": 0,
        "pixbufs": {},
        "drawing_area": None,
        "term": None,
    }

    window = Gtk.Window(title=args.title)
    window.set_default_size(1100, 720)
    window.connect("destroy", Gtk.main_quit)

    hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
    window.add(hbox)

    term = Vte.Terminal()
    term.set_hexpand(True)
    term.set_vexpand(True)
    term.set_scrollback_lines(50000)
    term.set_font(Pango.FontDescription("Monospace 12"))
    bg = Gdk.RGBA()
    bg.parse("#121417")
    fg = Gdk.RGBA()
    fg.parse("#e6edf3")
    term.set_color_background(bg)
    term.set_color_foreground(fg)
    state["term"] = term
    hbox.pack_start(term, True, True, 0)

    def on_key_press(_widget, event):
        mods = event.state & Gtk.accelerator_get_default_mod_mask()
        ctrl_shift = Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK
        if mods == ctrl_shift:
            keyname = Gdk.keyval_name(event.keyval)
            if keyname in ("C", "c"):
                term.copy_clipboard_format(Vte.Format.TEXT)
                return True
            if keyname in ("V", "v"):
                term.paste_clipboard()
                return True
        return False

    term.connect("key-press-event", on_key_press)

    scrollbar = Gtk.Scrollbar(
        orientation=Gtk.Orientation.VERTICAL, adjustment=term.get_vadjustment()
    )
    hbox.pack_start(scrollbar, False, True, 0)

    drawing_area = Gtk.DrawingArea()
    drawing_area.set_size_request(args.sidebar_width, -1)
    drawing_area.set_hexpand(False)
    drawing_area.set_vexpand(True)
    state["drawing_area"] = drawing_area
    hbox.pack_start(drawing_area, False, True, 0)

    def get_pixbuf(path: Path, w: int, h: int):
        mtime = path.stat().st_mtime_ns if path.exists() else 0
        key = (str(path), w, h, mtime)
        if key not in state["pixbufs"]:
            if len(state["pixbufs"]) > 32:
                state["pixbufs"].clear()
            state["pixbufs"][key] = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                str(path), max(1, w), max(1, h), False
            )
        return state["pixbufs"][key]

    frames_dir = Path(args.pics_dir) / args.agent

    def on_draw(area, cr):
        width = max(1, area.get_allocated_width())
        height = max(1, area.get_allocated_height())
        layout = compute_sidebar_layout(width, height, ASPECT_RATIO)
        top_png = frames_dir / f"{state['frame']}.png"
        if top_png.exists():
            top_pixbuf = get_pixbuf(top_png, layout["top_w"], layout["top_h"])
            Gdk.cairo_set_source_pixbuf(cr, top_pixbuf, 0, 0)
            cr.paint()
        if layout["bottom_h"] > 0 and ROSE_PATH.exists():
            rose_pixbuf = get_pixbuf(ROSE_PATH, layout["bottom_w"], layout["bottom_h"])
            Gdk.cairo_set_source_pixbuf(cr, rose_pixbuf, 0, layout["top_h"])
            cr.paint()
        return False

    drawing_area.connect("draw", on_draw)

    def on_child_exited(_term, _status):
        window.destroy()

    term.connect("child-exited", on_child_exited)

    argv = args.command if isinstance(args.command, list) and args.command else ["/bin/bash"]

    def _spawn():
        term.spawn_async(
            Vte.PtyFlags.DEFAULT,
            "/noobia",
            argv,
            None,
            GLib.SpawnFlags.DEFAULT,
            None,
            None,
            -1,
            None,
            None,
        )
        term.grab_focus()
        return False

    GLib.idle_add(_spawn)

    def poll(_source):
        text = ""
        title = ""
        if args.target_pane:
            read_text, read_title = read_pane_text(args.tmux_socket, args.target_pane)
            if read_text is not None:
                text = read_text
                title = read_title
        if not text:
            try:
                text = term.get_text_format(Vte.Format.TEXT) or ""
            except Exception:
                text = ""
        title = title or (term.get_window_title() or "")
        isw = is_pane_working(text, title)
        new_frame = select_frame_name(
            state["tracker"].update(isw, time.monotonic()), state["tick"]
        )
        state["tick"] += 1
        if new_frame != state["frame"]:
            state["frame"] = new_frame
            drawing_area.queue_draw()
        return True

    GLib.timeout_add(int(args.interval * 1000), poll, None)

    window.show_all()
    Gtk.main()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Solo Dushich GTK/VTE window.")
    parser.add_argument("--agent", default="Dushich")
    parser.add_argument("--pics-dir", default=DEFAULT_PICS_DIR)
    parser.add_argument("--sidebar-width", type=int, default=180)
    parser.add_argument("--interval", type=float, default=0.4)
    parser.add_argument("--tmux-socket", default="dushich-clean")
    parser.add_argument("--target-pane", default="")
    parser.add_argument("--title", default="Solo Dushich")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--command", nargs=argparse.REMAINDER, default=["/bin/bash"])
    args = parser.parse_args()
    if args.self_test:
        return _self_test(args)
    return _run_gui(args)


if __name__ == "__main__":
    sys.exit(main())
