#!/usr/bin/env python3
"""Solo Dushich GTK3 + VTE 2.91 window.

Left pane: a native Vte.Terminal (50,000-line scrollback, vertical
scrollbar) running the target command. Right pane: a fixed-width sidebar
drawing the primary agent frame at native pixel resolution, an optional
helper agent frame below it, and Rose.png filling any remaining space.
The sidebar redraws smoothly on any window resize/maximize/unmaximize.
"""

from __future__ import annotations

import argparse
import json
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

ASPECT_RATIO = 1.5
ACTIVE_STATUSES = ("queued", "running")
DEFAULT_BRIDGE_DIR = "/home/aria/.codex/dushich-bridge"
DEFAULT_BANSHEE_RUNS_DIR = "/noobia/banshee/private/task-runs"
DEFAULT_GWYN_RUNS_DIR = "/noobia/gwyn-app-nub/private/task-runs"


def compute_sidebar_layout(
    sidebar_width: int, total_height: int, aspect_ratio: float = 1.5, has_helper: bool = False
) -> dict:
    """Split the sidebar into top (primary), helper, and bottom (Rose) areas."""
    w = max(1, sidebar_width)
    ideal_h = max(1, round(w * aspect_ratio))
    if not has_helper:
        top_h = min(max(1, total_height), ideal_h)
        helper_h = 0
        bottom_h = max(0, total_height - top_h)
    elif total_height <= 2 * ideal_h:
        top_h = max(1, total_height // 2)
        helper_h = max(1, total_height - top_h)
        bottom_h = 0
    else:
        top_h = ideal_h
        helper_h = ideal_h
        bottom_h = max(0, total_height - top_h - helper_h)
    return {
        "top_w": w,
        "top_h": top_h,
        "helper_w": w,
        "helper_h": helper_h,
        "bottom_w": w,
        "bottom_h": bottom_h,
    }


def _any_active_state(paths: list[Path]) -> bool:
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            continue
        if isinstance(data, dict) and data.get("status") in ACTIVE_STATUSES:
            return True
    return False


def is_dushich_helper_working(
    helper_pane_text: str = "",
    helper_pane_title: str = "",
    bridge_dir: str = DEFAULT_BRIDGE_DIR,
    banshee_runs_dir: str = DEFAULT_BANSHEE_RUNS_DIR,
    gwyn_runs_dir: str = DEFAULT_GWYN_RUNS_DIR,
) -> bool:
    """True while the Dushich helper is visibly or queued/running in the bridge."""
    if is_pane_working(helper_pane_text, helper_pane_title):
        return True
    candidates: list[Path] = []
    for base in (bridge_dir, banshee_runs_dir, gwyn_runs_dir):
        root = Path(base)
        if root.is_dir():
            candidates.extend(sorted(root.glob("*/state.json")))
            candidates.extend(sorted(root.glob("*/*/state.json")))
    return _any_active_state(candidates)


def _self_test(args: argparse.Namespace) -> int:
    """Headless smoke test: layouts, all frame pixbufs, and cairo painting."""
    import gi

    gi.require_version("Gdk", "3.0")
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf, Gdk

    import cairo

    for has_helper in (False, True):
        for total_height in (180, 480, 720, 1000):
            layout = compute_sidebar_layout(args.sidebar_width, total_height, has_helper=has_helper)
            assert layout["top_w"] == max(1, args.sidebar_width)
            if has_helper:
                used = layout["top_h"] + layout["helper_h"] + layout["bottom_h"]
            else:
                used = layout["top_h"] + layout["bottom_h"]
            assert used == min(total_height, max(total_height, 0)) or used <= total_height

    pics = Path(args.pics_dir)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 10, 10)
    ctx = cairo.Context(surface)
    for agent in ("Aria", "Banshee", "Dushich"):
        for frame in REQUIRED_FRAMES:
            png = pics / agent / f"{frame}.png"
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(png), 180, 270, False)
            assert isinstance(pixbuf, GdkPixbuf.Pixbuf), str(png)
            assert (pixbuf.get_width(), pixbuf.get_height()) == (180, 270)
    ctx.save()
    Gdk.cairo_set_source_pixbuf(ctx, pixbuf, 0, 0)
    ctx.paint()
    ctx.restore()
    print("self-test OK")
    return 0


def _run_gui(args: argparse.Namespace) -> int:
    import os
    uid = os.getuid()
    runtime_dir = os.environ.setdefault("XDG_RUNTIME_DIR", f"/run/user/{uid}")
    if not os.environ.get("WAYLAND_DISPLAY") and Path(f"{runtime_dir}/wayland-0").exists():
        os.environ["WAYLAND_DISPLAY"] = "wayland-0"
    os.environ.setdefault("DISPLAY", ":0")
    import gi

    gi.require_version("Gtk", "3.0")
    gi.require_version("Vte", "2.91")
    gi.require_version("Gdk", "3.0")
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import Gtk, Vte, GdkPixbuf, GLib, Pango, Gdk

    state = {
        "tracker": StateTracker(),
        "frame": "idle",
        "tick": 0,
        "pixbufs": {},
        "drawing_area": None,
        "term": None,
        "helper_tracker": StateTracker() if args.helper_agent else None,
        "helper_frame": "idle" if args.helper_agent else None,
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

    def get_pixbuf(path: str, w: int, h: int):
        key = (str(path), w, h)
        if key not in state["pixbufs"]:
            state["pixbufs"][key] = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                str(path), w, h, False
            )
        return state["pixbufs"][key]

    pics = Path(args.pics_dir)

    def on_draw(area, cr):
        width = max(1, area.get_allocated_width())
        height = max(1, area.get_allocated_height())
        layout = compute_sidebar_layout(width, height, has_helper=bool(args.helper_agent))
        y = 0
        panels = [("top_h", "top_w", state["frame"], args.agent)]
        if args.helper_agent:
            panels.append(("helper_h", "helper_w", state["helper_frame"], args.helper_agent))
        for h_key, w_key, frame, agent in panels:
            panel_h = layout[h_key]
            if agent and panel_h > 0:
                pixbuf = get_pixbuf(str(pics / agent / f"{frame}.png"), layout[w_key], panel_h)
                cr.save()
                cr.translate(0, y)
                Gdk.cairo_set_source_pixbuf(cr, pixbuf, 0, 0)
                cr.paint()
                cr.restore()
                y += panel_h
        if layout["bottom_h"] > 0 and ROSE_PATH.exists():
            rose = get_pixbuf(str(ROSE_PATH), layout["bottom_w"], layout["bottom_h"])
            cr.save()
            cr.translate(0, y)
            Gdk.cairo_set_source_pixbuf(cr, rose, 0, 0)
            cr.paint()
            cr.restore()

    drawing_area.connect("draw", on_draw)

    def on_child_exited(_term, status):
        window.destroy()

    term.connect("child-exited", on_child_exited)

    argv = args.command or ["bash"]
    if argv == [""]:
        argv = ["bash"]

    def _spawn():
        term.spawn_async(
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

    GLib.idle_add(_spawn)

    def poll(_source):
        now = time.monotonic()
        if args.target_pane:
            read_text, read_title = read_pane_text(args.tmux_socket, args.target_pane)
            text = read_text or ""
            title = read_title or ""
        else:
            text, title = "", ""
        title = title or (term.get_window_title() or "")
        new_frame = select_frame_name(
            state["tracker"].update(is_pane_working(text, title), now), state["tick"]
        )
        changed = new_frame != state["frame"]
        state["frame"] = new_frame

        if args.helper_agent and state["helper_tracker"] is not None:
            if args.helper_pane:
                h_text, h_title = read_pane_text(args.tmux_socket, args.helper_pane)
                h_text = h_text or ""
            else:
                h_text, h_title = "", ""
            h_working = is_dushich_helper_working(h_text, h_title)
            h_frame = select_frame_name(
                state["helper_tracker"].update(h_working, now), state["tick"]
            )
            changed = changed or h_frame != state["helper_frame"]
            state["helper_frame"] = h_frame

        state["tick"] += 1
        if changed:
            drawing_area.queue_draw()
        return True

    GLib.timeout_add(int(args.interval * 1000), poll, None)

    window.show_all()
    Gtk.main()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Solo Dushich GTK/VTE window.")
    parser.add_argument("--agent", default="Dushich")
    parser.add_argument("--helper-agent", default="")
    parser.add_argument("--pics-dir", default=DEFAULT_PICS_DIR)
    parser.add_argument("--sidebar-width", type=int, default=180)
    parser.add_argument("--interval", type=float, default=0.4)
    parser.add_argument("--tmux-socket", default="dushich-clean")
    parser.add_argument("--target-pane", default="")
    parser.add_argument("--helper-pane", default="")
    parser.add_argument("--title", default="Solo Dushich")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--command", nargs=argparse.REMAINDER, default=None)
    args = parser.parse_args()
    if args.self_test:
        return _self_test(args)
    return _run_gui(args)


if __name__ == "__main__":
    sys.exit(main())
