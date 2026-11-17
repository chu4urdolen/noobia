#!/usr/bin/env python3
"""Launch Rose's dashboard; microphone/backend lifetime is independent."""
from dashboard import Window
from gi.repository import Gtk

if __name__ == '__main__':
    Window()
    Gtk.main()
