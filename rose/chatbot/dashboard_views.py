"""Resizable panels and camera previews, independent of the speech pipeline."""
import json
from pathlib import Path
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, Pango


def fit_size(width, height, available_width, available_height):
    ratio = min(max(1, available_width) / width, max(1, available_height) / height)
    return max(1, int(width * ratio)), max(1, int(height * ratio))


def camera_image(output):
    candidates = []
    def inspect(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {'image', 'annotated_image', 'photo', 'snapshot', 'image_path'} and isinstance(item, str):
                    candidates.append(item)
                else:
                    inspect(item)
        elif isinstance(value, list):
            for item in value:
                inspect(item)
    for line in output.splitlines():
        line = line.strip()
        if line.startswith('/'):
            candidates.append(line)
        try:
            inspect(json.loads(line))
        except ValueError:
            pass
    for candidate in candidates:
        path = Path(candidate)
        if path.is_absolute() and path.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp'} and path.is_file():
            return path
    return None


def text_view(buffer=None, editable=False):
    return Gtk.TextView(buffer=buffer, editable=editable, cursor_visible=editable,
                        wrap_mode=Gtk.WrapMode.WORD_CHAR, left_margin=10,
                        right_margin=10, top_margin=8, bottom_margin=8)


def panel(title, widget):
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    box.set_border_width(8)
    box.get_style_context().add_class('rose-panel')
    heading = Gtk.Label(label=title, xalign=0)
    heading.set_ellipsize(Pango.EllipsizeMode.END)
    heading.get_style_context().add_class('rose-title')
    box.pack_start(heading, False, False, 0)
    box.pack_start(widget, True, True, 0)
    return box


def scroll(view):
    widget = Gtk.ScrolledWindow()
    widget.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    widget.add(view)
    return widget


class RatioPane(Gtk.Paned):
    """Preserve proportions when the parent changes size, including after relaunch."""
    def __init__(self, orientation, ratio=.5, changed=None):
        super().__init__(orientation=orientation)
        self.ratio = min(.9, max(.1, ratio))
        self.extent = 0
        self.restoring = False
        self.changed = changed or (lambda: None)
        self.connect('size-allocate', self.allocate)
        self.connect('notify::position', self.position_changed)

    def current_extent(self):
        allocation = self.get_allocation()
        return allocation.width if self.get_orientation() == Gtk.Orientation.HORIZONTAL else allocation.height

    def allocate(self, widget, allocation):
        self.extent = self.current_extent()
        if self.extent > 1:
            self.restoring = True
            self.set_position(round(self.extent * self.ratio))
            self.restoring = False

    def position_changed(self, *_):
        extent = self.current_extent()
        if not self.restoring and extent > 1 and extent == self.extent:
            self.ratio = min(.9, max(.1, self.get_position() / extent))
            self.changed()


class Photo(Gtk.DrawingArea):
    """Retain original pixels; viewport size never becomes the widget minimum size."""
    def __init__(self):
        super().__init__()
        self.original = None
        self.scaled = None
        self.set_size_request(80, 60)
        self.connect('draw', self.draw_photo)

    def load(self, path):
        self.original = GdkPixbuf.Pixbuf.new_from_file(str(path))
        self.scaled = None
        self.queue_draw()

    def draw_photo(self, widget, context):
        context.set_source_rgb(0, 0, 0)
        context.paint()
        if self.original is None:
            return False
        width, height = self.get_allocated_width(), self.get_allocated_height()
        target = fit_size(self.original.get_width(), self.original.get_height(), width, height)
        if self.scaled is None or target != (self.scaled.get_width(), self.scaled.get_height()):
            self.scaled = self.original.scale_simple(*target, GdkPixbuf.InterpType.BILINEAR)
        Gdk.cairo_set_source_pixbuf(context, self.scaled, (width - target[0]) / 2, (height - target[1]) / 2)
        context.paint()
        return False


class ToolView(Gtk.Box):
    def __init__(self, buffer):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.log = text_view(buffer)
        self.photo = Photo()
        self.stack = Gtk.Stack()
        self.stack.add_named(scroll(self.log), 'text')
        self.stack.add_named(self.photo, 'photo')
        buttons = Gtk.Box(spacing=6)
        for label, mode in [('Text log', 'text'), ('Camera photo', 'photo')]:
            button = Gtk.Button(label=label)
            button.connect('clicked', lambda _, mode=mode: self.show_mode(mode))
            buttons.pack_start(button, False, False, 0)
            if mode == 'photo':
                self.photo_button = button
                button.set_sensitive(False)
        self.pack_start(buttons, False, False, 0)
        self.pack_start(self.stack, True, True, 0)
        self.caption = Gtk.Label(label='Tool output is displayed here, never sent directly to speech.', xalign=0)
        self.caption.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        self.pack_start(self.caption, False, False, 0)
        self.show_mode('text')

    def show_mode(self, mode):
        if mode == 'photo' and self.photo.original is None:
            return
        self.stack.set_visible_child_name(mode)

    def show_photo(self, path):
        self.photo.load(path)
        self.photo_button.set_sensitive(True)
        self.caption.set_text(str(path))
        self.show_mode('photo')
