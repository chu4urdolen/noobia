import GLib from 'gi://GLib';
import Gio from 'gi://Gio';
import Meta from 'gi://Meta';
import { Extension } from 'resource:///org/gnome/shell/extensions/extension.js';

const DBUS_IFACE = `
<node>
  <interface name="org.noobia.Corners">
    <method name="ListWindows">
      <arg type="s" direction="out" name="windows_json"/>
    </method>
    <method name="PlaceWindow">
      <arg type="u" direction="in" name="window_id"/>
      <arg type="s" direction="in" name="corner"/>
      <arg type="b" direction="out" name="ok"/>
    </method>
    <method name="PlaceAllByMatch">
      <arg type="s" direction="out" name="result_json"/>
    </method>
  </interface>
</node>`;

const CORNER_MATCHERS = [
    {
        corner: 'topleft',
        roles: ['noobia-corner-topleft'],
        titles: ['Noobia • Aria', 'noobia-codex'],
    },
    {
        corner: 'topright',
        roles: ['noobia-corner-topright'],
        titles: ['Noobia • Banshee', 'noobia-banshee'],
    },
    {
        corner: 'bottomleft',
        roles: ['noobia-corner-bottomleft'],
        titles: ['Noobia • Dushich', 'dushich'],
    },
    {
        corner: 'bottomright',
        roles: ['noobia-corner-bottomright'],
        titles: ['Noobia • Terminal'],
    },
];

export default class NoobiaCornersExtension extends Extension {
    enable() {
        this._timeouts = new Set();

        this._dbusImpl = Gio.DBusExportedObject.wrapJSObject(DBUS_IFACE, this);
        try {
            this._dbusImpl.export(Gio.DBus.session, '/org/noobia/Corners');
        } catch (e) {
            console.error('NoobiaCornersExtension DBus export error:', e);
        }

        this._windowCreatedId = global.display.connect(
            'window-created',
            (_display, window) => this._onWindowCreated(window)
        );

        this._schedulePlaceAll([200, 800, 2000]);
    }

    disable() {
        if (this._windowCreatedId) {
            global.display.disconnect(this._windowCreatedId);
            this._windowCreatedId = 0;
        }
        for (const id of this._timeouts) {
            GLib.Source.remove(id);
        }
        this._timeouts.clear();

        if (this._dbusImpl) {
            try {
                this._dbusImpl.unexport();
            } catch (e) {
                // ignore
            }
            this._dbusImpl = null;
        }
    }

    ListWindows() {
        const out = [];
        for (const w of global.display.list_all_windows()) {
            const r = w.get_frame_rect();
            out.push({
                id: w.get_id(),
                seq: w.get_stable_sequence?.(),
                title: w.get_title?.() ?? '',
                role: w.get_role?.() ?? '',
                wm_class: w.get_wm_class?.() ?? '',
                gtk_app_id: w.get_gtk_application_id?.() ?? '',
                gtk_win_path: w.get_gtk_window_object_path?.() ?? '',
                rect: { x: r.x, y: r.y, width: r.width, height: r.height },
            });
        }
        return JSON.stringify(out);
    }

    PlaceWindow(windowId, corner) {
        const win = global.display.list_all_windows().find(w => w.get_id() === windowId);
        if (!win)
            return false;
        this._placeWindowInCorner(win, corner);
        return true;
    }

    PlaceAllByMatch() {
        const res = this._placeAllTerminals();
        return JSON.stringify(res);
    }

    _onWindowCreated(window) {
        const actor = window.get_compositor_private();
        if (actor) {
            const firstFrameId = actor.connect('first-frame', () => {
                actor.disconnect(firstFrameId);
                this._scheduleWindowChecks(window, [100, 400, 1000, 2200]);
            });
        } else {
            this._scheduleWindowChecks(window, [200, 600, 1500]);
        }
    }

    _scheduleWindowChecks(window, delays) {
        for (const delay of delays) {
            const timerId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, delay, () => {
                this._timeouts.delete(timerId);
                this._checkAndPlaceWindow(window);
                return GLib.SOURCE_REMOVE;
            });
            this._timeouts.add(timerId);
        }
    }

    _schedulePlaceAll(delays) {
        for (const delay of delays) {
            const timerId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, delay, () => {
                this._timeouts.delete(timerId);
                this._placeAllTerminals();
                return GLib.SOURCE_REMOVE;
            });
            this._timeouts.add(timerId);
        }
    }

    _matchCorner(window) {
        const role = window.get_role?.() ?? '';
        const title = window.get_title?.() ?? '';
        const gtkWinPath = window.get_gtk_window_object_path?.() ?? '';

        for (const m of CORNER_MATCHERS) {
            if (role && m.roles.includes(role))
                return m.corner;
        }
        for (const m of CORNER_MATCHERS) {
            if (title && m.titles.some(t => title.includes(t)))
                return m.corner;
        }
        if (gtkWinPath === '/org/gnome/Terminal/window/1')
            return 'topleft';
        if (gtkWinPath === '/org/gnome/Terminal/window/2')
            return 'topright';
        if (gtkWinPath === '/org/gnome/Terminal/window/3')
            return 'bottomleft';
        if (gtkWinPath === '/org/gnome/Terminal/window/4')
            return 'bottomright';

        return null;
    }

    _checkAndPlaceWindow(window) {
        if (!window)
            return;
        const corner = this._matchCorner(window);
        if (!corner)
            return;
        this._placeWindowInCorner(window, corner);
    }

    _placeAllTerminals() {
        const results = [];
        for (const w of global.display.list_all_windows()) {
            const corner = this._matchCorner(w);
            if (corner) {
                const rect = this._placeWindowInCorner(w, corner);
                results.push({ id: w.get_id(), title: w.get_title?.(), corner, rect });
            }
        }
        return results;
    }

    _placeWindowInCorner(window, corner) {
        if (!window)
            return null;

        if (window.maximized_horizontally || window.maximized_vertically) {
            if (window.unmaximize.length === 0)
                window.unmaximize();
            else
                window.unmaximize(Meta.MaximizeFlags.BOTH);
        }
        window.unmake_fullscreen?.();

        const monitor = window.get_monitor();
        const workArea = window.get_work_area_for_monitor(monitor);
        if (!workArea)
            return null;

        const leftW = Math.floor(workArea.width / 2);
        const rightW = workArea.width - leftW;
        const topH = Math.floor(workArea.height / 2);
        const bottomH = workArea.height - topH;

        let x = workArea.x;
        let y = workArea.y;
        let w = leftW;
        let h = topH;

        if (corner === 'topright') {
            x = workArea.x + leftW;
            w = rightW;
        } else if (corner === 'bottomleft') {
            y = workArea.y + topH;
            h = bottomH;
        } else if (corner === 'bottomright') {
            x = workArea.x + leftW;
            y = workArea.y + topH;
            w = rightW;
            h = bottomH;
        }

        if (window.override_constraints) {
            window.override_constraints(
                Meta.WindowConstraint.NONE,
                Meta.WindowConstraint.NONE,
                Meta.WindowConstraint.NONE,
                Meta.WindowConstraint.NONE
            );
        }

        window.move_frame(true, x, y);
        window.move_resize_frame(true, x, y, w, h);
        return { x, y, width: w, height: h };
    }
}
