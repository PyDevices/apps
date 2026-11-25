# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Shell: what's around an app, and what it hands each app's scope.

This one is the plainest: an app gets the whole screen, and a Home button
sits in the corner when there's a home screen to go back to. With
``bar=True`` (what ``appkit.run`` makes) the Shell shows the status bar
(`appkit.bar`) instead, with Home and the app's title on it, and each app
gets the screen below it unless its ``app.json`` says ``"bar": "own"`` or ``"none"``. Those apps,
and every app under the compact cap, keep the corner Home button. On a round
screen (`is_round`) the button is a circle with the Home icon, set in
from the top right along the diagonal so all of it is inside the circle. A board that
wants a header, its own look or its own buttons subclasses it: override
`Shell.make_root` to give apps a smaller area (with the bar on, inside
`Shell.bar_area`), `Shell.make_home_button` for its own Home button, or
`Shell.prepare` to hand them other services.
"""

import sys

import lvgl as lv
from icons import lvgl as lvicons

from . import data, hover

#: How far a round screen's Home button keeps in from the circle's edge, in pixels.
ROUND_MARGIN = 4


def is_round():
    """Whether the default display is a round panel.

    The board's display driver says so with a ``round`` attribute; without
    one, a GC9A01 is taken to be round, since the controller is made for
    round panels. A screen that isn't square never is. It only looks at a
    ``board_config`` something has already imported, so it imports nothing.
    """
    disp = lv.display_get_default()
    if disp is None or disp.get_horizontal_resolution() != disp.get_vertical_resolution():
        return False
    board = sys.modules.get("board_config")
    drv = getattr(board, "display_drv", None)
    if drv is None:
        return False
    r = getattr(drv, "round", None)
    if r is None:
        r = type(drv).__name__.upper().startswith("GC9A01")
    return bool(r)


def round_corner(size, d, margin=ROUND_MARGIN):
    """Where a *d*-pixel circle goes at the top right of a round screen
    *size* pixels across: ``(x, y)`` of its top left, on the diagonal, as
    far out as it can go and stay *margin* pixels inside the edge."""
    r = size // 2
    off = int((r - margin - d / 2) * 0.7071)  # along the diagonal, cos 45
    return r + off - d // 2, r - off - d // 2


class Shell:
    """*data_root* moves every app's ``data_dir``, and the launcher's
    restart file, for the whole program (see ``appkit.data``)."""

    def __init__(self, launcher, *, data_root=None, bar=False):
        self.launcher = launcher
        self.home_button = None
        self.picker = None
        #: The status bar (`appkit.bar.Bar`), or None without one.
        self.bar = None
        self._scope = None   # the app the bar's room was last given to
        self._area = None    # the area below the bar that app was given
        if data_root is not None:
            data.set_root(data_root)
        hover.apply()
        # Made before any app starts, so no app's close() deletes them.
        if bar:
            self.bar = self.make_bar()
            self.bar._on_change = self._bar_moved
        elif launcher.home is not None:
            self.home_button = self.make_home_button()
        #: Typing from a keyboard on the board's USB host port
        #: (`appkit.hostkeys.HostKeys`), or None where there's no such port.
        self.host_keys = self.make_host_keys()

    def make_bar(self):
        """The status bar, made once when the shell is, with Home on it when
        there's a home screen. Override it for items or a look of your own."""
        from . import connections
        from .bar import Bar

        connections.register()
        launcher = self.launcher
        on_home = None
        if launcher.home is not None:
            on_home = lambda: launcher.request(launcher.home)  # noqa: E731
        return Bar(on_home=on_home, on_picker=self.open_picker)

    def make_host_keys(self):
        """A keyboard on the board's USB host port types into the focused
        field: the `appkit.hostkeys.HostKeys` that reads it, made once when
        the shell is, or None on a device whose host port isn't registered
        (`appkit.connections.usb_host`)."""
        from . import connections

        if not connections.usb_host():
            return None
        import endpointkit

        from .hostkeys import HostKeys

        # The bar polls endpointkit once a second; without it, this looks as often.
        return HostKeys(endpointkit.registry, look_ms=None if self.bar is not None else 1000)

    def bar_mode(self, scope):
        """What the app's ``app.json`` asks for: ``"shell"`` (the default),
        ``"own"`` or ``"none"``."""
        info = getattr(self.launcher, "info", {}).get(scope.name) or {}
        mode = info.get("bar", "shell")
        if mode not in ("shell", "own", "none"):
            raise ValueError('app %r: "bar" is %r; use "shell", "own" or "none"' % (scope.name, mode))
        return mode

    def make_home_button(self):
        """The Home button, made once when the shell is: an LVGL object that
        switches to the home screen when clicked, or None for no button.

        Override it for a button of your own look. Put it on
        ``lv.layer_top()`` or ``lv.layer_sys()``, so it shows over every
        app's screen; `prepare` hides it on the home screen itself.
        """
        launcher = self.launcher
        b = lv.button(lv.layer_top())
        if is_round():
            # The corner is outside the circle: a round button on the diagonal.
            size = lv.display_get_default().get_horizontal_resolution()
            d = max(36, size // 6)
            b.set_size(d, d)
            b.set_style_radius(lv.RADIUS_CIRCLE, 0)
            b.set_style_pad_all(0, 0)
            lvicons.image(b, "home", 24).center()
            b.set_pos(*round_corner(size, d))
        else:
            b.align(lv.ALIGN.TOP_RIGHT, -8, 8)
            lv.label(b).set_text("Home")
        b.add_event_cb(lambda e: launcher.request(launcher.home), lv.EVENT.CLICKED, None)
        return b

    def open_picker(self, kind=None):
        """Open the picker over the running app: the list of kinds, or
        *kind*'s page (``"audio.out"``). It's made the first time; returns it."""
        if self.picker is None:
            from . import connections
            from .picker import Picker

            connections.register()
            self.picker = Picker()
        self.picker.open(kind)
        return self.picker

    def prepare(self, scope):
        """Fill *scope* before the app's ``main`` runs: its ``root``, ``size``
        and ``rect``. ``worker``, ``data_dir`` and ``store()`` have defaults
        on every scope; a subclass may set others here."""
        if self.bar is not None:
            self._scope = None   # no app is told while the bar is set up for this one
            if self.bar_mode(scope) == "shell":
                self.bar.show()
            else:
                self.bar.hide()
            self.bar.set_home(scope.name != self.launcher.home)
            scope.bar = self.bar
            self._title(scope)
        self._area = None
        scope.root = self.make_root(scope)
        self.measure(scope)
        self._scope = scope
        corner = self._corner_home(scope)
        if corner and self.home_button is None:
            # With the bar, made the first time an app has no Home on it.
            from . import scope as scopes

            self.home_button = self.make_home_button()
            if self.home_button is not None:
                scopes.keep(self.home_button)
        if self.home_button is not None:
            if corner:
                self.home_button.remove_flag(lv.obj.FLAG.HIDDEN)
            else:
                self.home_button.add_flag(lv.obj.FLAG.HIDDEN)

    def _title(self, scope):
        """Put *scope*'s title on the bar, and give an app under it the
        bar's header and a fresh status line (``scope.header``,
        ``scope.status``). The home screen gets `home_title` and no status
        line; an app with its own bar or none gets an empty title."""
        bar = self.bar
        if bar.header is None:   # the compact cap has no room for one
            return
        if scope.name == self.launcher.home:
            bar.open(self.home_title(), status=False)
        elif self.bar_mode(scope) == "shell":
            title = getattr(self.launcher, "info", {}).get(scope.name, {}).get("title", scope.name)
            scope.header, scope.status = bar.open(title)
        else:
            bar.open("", status=False)

    def home_title(self):
        """What the bar says on the home screen, which has no title of its
        own: the board's name, as the network knows it, so a bench of boards
        tells apart at a glance. Empty where there's no ``boarddev``."""
        try:
            import boarddev

            return boarddev.name() or ""
        except Exception:  # noqa: BLE001 - no boarddev, or no name yet
            return ""

    def _corner_home(self, scope):
        """Whether *scope*'s app gets the corner Home button: away from the
        home screen, when the bar isn't there to carry Home (no bar, an app
        with ``"bar": "none"`` or ``"own"``, or the compact cap)."""
        if self.launcher.home is None or scope.name == self.launcher.home:
            return False
        return self.bar is None or not self.bar.is_shown() or self.bar.home is None

    def make_root(self, scope):
        """The LVGL object the app builds on: a screen of its own, or with
        the bar showing, an area of it below the bar."""
        screen = scope.screen()
        if self.bar is None or self.bar_mode(scope) != "shell":
            return screen
        return self.bar_area(screen)

    def bar_area(self, screen):
        """A plain area of *screen* below the bar, which grows to the whole
        screen while the app hides the bar. A subclass's `make_root` builds
        in it when the bar is on."""
        area = lv.obj(screen)
        area.set_style_radius(0, 0)
        area.set_style_border_width(0, 0)
        area.set_style_pad_all(0, 0)
        area.set_style_bg_opa(lv.OPA.TRANSP, 0)
        self._fit(area, self.bar.chrome_height())
        self._area = area
        return area

    @staticmethod
    def _fit(area, top):
        h = lv.display_get_default().get_vertical_resolution()
        area.set_size(lv.pct(100), h - top)
        area.set_pos(0, top)

    def _bar_moved(self, shown):
        """The running app hid or showed the bar: its area follows."""
        scope = self._scope
        if scope is None or self.bar_mode(scope) != "shell" or self.bar.compact:
            return
        area = self._area
        if area is not None and area.get_parent() is not None:
            self._fit(area, self.bar.chrome_height())
            self.measure(scope)

    def measure(self, scope):
        """Set ``scope.size`` and ``scope.rect`` from ``scope.root``."""
        root = scope.root
        root.update_layout()
        area = lv.area_t()
        root.get_coords(area)
        w = area.x2 - area.x1 + 1
        h = area.y2 - area.y1 + 1
        scope.size = (w, h)
        scope.rect = (area.x1, area.y1, w, h)
