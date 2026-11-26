# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""touchkit.shell -- the board's chrome and launcher.

* `TouchShell` shows appkit's status bar along the top: Home, the app's
  title, its status line (``scope.status``, see ``touchkit.ui.status``),
  then the clock and the icons. ``scope.header`` is the bar's stretch that
  holds the title, and ``scope.root`` is everything below the bar. Under
  the compact cap, which has no room for a title, the app gets a short
  row of its own below the cap instead, with Home at its left; on a round
  screen the row starts and ends inside the circle (`round_row`). An app whose ``app.json`` says ``"bar": "none"``
  gets the whole screen, with a square glass Home button (`appkit.glass`)
  on LVGL's system layer, where the app shows through it and it never
  presses the app's own widgets. Without the bar (``bar=False``) every
  app gets the header with that Home button at its left. The board's BOOT
  button goes home too, through a pin interrupt.
* `TouchLauncher` keeps a short history of switches for Info,
  and takes the USB sound card off when the next app isn't one that plays
  through it, so the PC goes back to its own speakers.

Work too heavy for a timer runs through appkit's ``scope.foreground()``,
and ``main.py`` ends in ``appkit.serve()``.
"""

import gc

import lvgl as lv
import multimer
from icons import lvgl as lvicons
from multimer import ticks_diff, ticks_ms

from appkit import Launcher, Shell, foreground, glass
from appkit import shell as appshell

from . import ui

#: How often LVGL reads the touch panel, in ms, unless an app asks otherwise.
TOUCH_MS = 33
#: Under the compact cap: the cap's row (the cap and the Home button beside
#: it) and the Home button's width, in pixels.
CAP_ROW = 30
CAP_HOME_W = 44
#: Under the compact cap a long title ends in dots down to this width, in pixels, before the status line does.
TITLE_MIN = 40

launcher = None  # the running launcher, once a TouchShell has been made for it
boot_presses = 0


# -- the launcher -------------------------------------------------------------


class TouchLauncher(Launcher):
    """appkit's launcher, keeping the last switches."""

    def __init__(self, *args, **kw):
        Launcher.__init__(self, *args, **kw)
        #: ``(app, how, ms, free bytes after the old app closed)``, newest last.
        self.history = []

    def switch(self, name):
        how = Launcher.switch(self, name)
        last = self.last or (how, None, None)
        self.history.append((name, how, last[1], last[2]))
        if len(self.history) > 50:
            del self.history[0]
        return how


# -- the shell ---------------------------------------------------------------------


def _set_launcher(running):
    global launcher
    launcher = running


def _cap_title_row():
    """The height of the title row under the compact cap."""
    return ui.small.line_height + 6


def round_row(size, y, margin=None):
    """``(x0, x1)``: where a row *y* pixels down a round screen *size*
    pixels across starts and ends, *margin* pixels inside the circle
    (appkit's ``ROUND_MARGIN`` by default)."""
    if margin is None:
        margin = appshell.ROUND_MARGIN
    r = size // 2
    dy = r - y
    half = int(max(0, (r - margin) * (r - margin) - dy * dy) ** 0.5)
    return r - half, r + half


def _under_cap(shell):
    """Whether the status bar is the compact cap: then the Home button is
    just its icon, clear of the cap."""
    bar = getattr(shell, "bar", None)
    return bar is not None and bar.compact


class TouchShell(Shell):
    """The board's look: the status bar with the app's title and status
    line on it, and BOOT going home. *bar* False leaves the bar off and
    puts a Home button in the header."""

    def __init__(self, launcher, *, data_root=None, bar=True):
        _set_launcher(launcher)
        ui.apply_theme()  # first: the Home button is made in Shell.__init__
        Shell.__init__(self, launcher, data_root=data_root, bar=bar)
        self.boot_pin = None
        if launcher.home is not None:
            self._boot_button()

    def make_home_button(self):
        if getattr(self, "bar", None) is None:
            # In the header, at its left, beside the title.
            b = lv.button(lv.layer_sys())
            b.set_size(ui.HOME_W, ui.HEADER - 12)
            b.set_pos(6, 6)
            b.set_style_bg_color(ui.KEY, 0)
            b.set_style_radius(12, 0)
            # The Home icon, as on the bar's Home button.
            lvicons.image(b, "home", 24, ui.WHITE).center()
        elif _under_cap(self):
            # In the cap's row: glass, so an app with the whole screen shows
            # through it, the icon alone.
            b = glass.button(lv.layer_sys(), "home", CAP_HOME_W, 12)
            b.set_ext_click_area(4)
            if appshell.is_round():
                # The corners are outside the circle: at the left of the
                # title row, inside it.
                x0, _ = round_row(lv.display_get_default().get_horizontal_resolution(), CAP_ROW)
                b.set_size(CAP_HOME_W, _cap_title_row() - 2)
                b.set_pos(x0, CAP_ROW + 1)
            else:
                # Beside the cap.
                b.set_size(CAP_HOME_W, CAP_ROW - 4)
                b.set_pos(4, 2)
        else:
            # Over an app that takes the whole screen: a square of glass,
            # which the app shows through, as Huey's Perch's controls do.
            disp = lv.display_get_default()
            side = glass.side(disp.get_horizontal_resolution(), disp.get_vertical_resolution())
            b = glass.button(lv.layer_sys(), "home", side)
            b.set_pos(8, 8)
        launcher = self.launcher
        b.add_event_cb(lambda e: go(launcher.home), lv.EVENT.CLICKED, None)
        return b

    def _boot_button(self):
        try:
            import board_config as board

            pin = board.boot_button  # a lazy role: reading it may hand back a factory
            from machine import Pin

            if not hasattr(pin, "irq"):
                pin = pin()
            pin.irq(trigger=Pin.IRQ_FALLING, handler=_boot_irq)
            self.boot_pin = pin
        except AttributeError:  # no boot_button role: Home is on the screen
            self.boot_pin = None
        except Exception as e:  # the role is there but didn't come up
            print("touchkit: no BOOT button: %r" % (e,))
            self.boot_pin = None

    def lend_boot(self):
        """Hand the BOOT button to the app that's running, which reads it as
        a button of its own (Backline's footswitch). BOOT stops going home
        until the function this returns is called; Home on the screen still
        works.

        Returns:
            A function that gives BOOT back to the shell. It does nothing
            on a board with no BOOT role.
        """
        pin = self.boot_pin
        if pin is None:
            return lambda: None
        pin.irq(handler=None)

        def give_back():
            from machine import Pin

            pin.irq(trigger=Pin.IRQ_FALLING, handler=_boot_irq)
        return give_back

    def make_root(self, scope):
        scr = scope.screen()
        scr.set_style_bg_color(ui.BG, 0)
        scr.set_style_text_font(ui.font, 0)
        scr.set_style_text_color(ui.WHITE, 0)
        scr.remove_flag(lv.obj.FLAG.SCROLLABLE)
        bar = getattr(self, "bar", None) is not None
        if bar and self.bar_mode(scope) != "shell":
            return scr  # the whole screen, as the app asked
        if scope.name == self.launcher.home:
            # Home draws its own top bar, below the status bar when there is one.
            return self.bar_area(scr) if bar else scr
        w, h = scr.get_width(), scr.get_height()
        if bar and not self.bar.compact:
            # The title and the status line are on the bar (appkit's Shell
            # put them there): the app has everything below it, as a plain
            # area that doesn't scroll.
            body = ui.plain(lv.obj(self.bar_area(scr)))
            body.set_size(lv.pct(100), lv.pct(100))
            return body
        if bar:
            # The cap floats at the top middle with Home beside it; the
            # title and status line get a row of their own below.
            parent = self.bar_area(scr)
            parent.set_flex_flow(lv.FLEX_FLOW.COLUMN)
            parent.set_style_pad_row(0, 0)
            hdr_h = CAP_ROW + _cap_title_row()
            top, f = CAP_ROW, ui.small
            if appshell.is_round():
                # Inside the circle where the row starts: Home, then the
                # title, then the status line, the whole row centred.
                x0, x1 = round_row(w, CAP_ROW)
                left, right = x0 + CAP_HOME_W + 6, w - x1
            else:
                left, right = 8, 8
        else:
            parent = scr
            hdr_h = ui.HEADER
            top, left, right = 0, ui.HOME_W + 24, 16
            f = ui.big if w >= 480 else ui.font
        hdr = ui.plain(lv.obj(parent))
        hdr.set_size(w, hdr_h)
        hdr.set_style_bg_color(ui.PANEL, 0)
        hdr.set_style_bg_opa(lv.OPA.COVER, 0)
        title = self.launcher.info.get(scope.name, {}).get("title", scope.name)
        # A narrow screen gets the smaller font, and a title that still
        # doesn't fit ends in dots rather than running off the edge.
        t = ui.label(hdr, title, f, ui.WHITE)
        t.set_long_mode(lv.label.LONG_MODE.DOTS)
        t.set_size(w - left - right, f.line_height)
        t.align(lv.ALIGN.LEFT_MID, left, top // 2)
        status = ui.label(hdr, "", ui.tiny if bar else ui.small, ui.MUTED)
        status.set_long_mode(lv.label.LONG_MODE.DOTS)
        # The title keeps TITLE_MIN of the row; the status line ends in dots past the rest.
        status.set_style_max_width(max(0, min(w // 2, w - left - right - TITLE_MIN - 8)), 0)
        status.set_height(status.get_style_text_font(0).line_height)  # dots, never a second line
        status.align(lv.ALIGN.RIGHT_MID, -right, top // 2)

        def fit(e=None):
            # The title gives way first: it takes what the status line leaves.
            sw = status.get_width() + 8 if status.get_text() else 0
            t.set_width(max(TITLE_MIN, w - left - right - sw))

        status.add_event_cb(fit, lv.EVENT.SIZE_CHANGED, None)
        scope.header = hdr
        scope.status = status
        body = ui.plain(lv.obj(parent))
        if bar:
            body.set_width(w)
            body.set_flex_grow(1)
        else:
            body.set_pos(0, ui.HEADER)
            body.set_size(w, h - ui.HEADER)
        return body


def go(name):
    """Switch to app *name* after the current callback."""
    if launcher is not None and launcher.current != name:
        launcher.request(name)


_boot_at = 0


def _boot_go(_):
    if launcher is not None:
        go(launcher.home)


def _boot_irq(pin):
    # A pin IRQ runs between bytecodes; switching from it would close an app
    # in the middle of whatever it was doing, so the switch is scheduled.
    global _boot_at, boot_presses
    now = ticks_ms()
    if ticks_diff(now, _boot_at) < 400:
        return  # contact bounce, or a second press mid-switch
    _boot_at = now
    boot_presses += 1
    try:
        multimer.schedule(_boot_go, None)
    except RuntimeError:
        pass  # the schedule queue is full: the press is lost, press again


def redraw_home_button():
    """Have LVGL redraw the Home button: for an app that draws straight into
    the framebuffer under it."""
    s = launcher.shell if launcher is not None else None
    b = getattr(s, "home_button", None)
    if b is not None:
        b.invalidate()


def quiet_app_timers(app):
    """Stop the App's own service and refresh timers: display_driver hands
    presentation and input to LVGL, after which they fire and return at
    once, 130 times a second, costing the foreground loop."""
    for t in tuple(app.timers):
        if t.name == "app.service" or str(t.name).startswith("refresh:"):
            t.deinit()


# -- touch -----------------------------------------------------------------------------


def _pointer_indev():
    from display_driver import app

    for dev in app.devices:
        ind = getattr(dev, "user_data", None)
        if ind is not None and ind.get_type() == lv.INDEV_TYPE.POINTER:
            return ind
    return None


def touch_period(scope, ms):
    """Have LVGL read the touch panel every *ms* while app *scope* is open.

    A read costs about 0.8 ms and some garbage. An app whose audio stalls on
    every collection that garbage forces can slow it, to 100 ms say.
    """
    ind = _pointer_indev()
    if ind is None:
        return
    ind.get_read_timer().set_period(ms)
    scope.on_close(lambda: ind.get_read_timer().set_period(TOUCH_MS))


# -- what's still running (System, and the switch tests) -------------------------------------


def heap_text():
    n = launcher.switches if launcher is not None else 0
    if not hasattr(gc, "mem_free"):  # CPython counts no heap of its own
        return "heap: this interpreter doesn't count it, %d switches" % (n,)
    free = gc.mem_free()
    return "heap free %.1f MB, in use %d KB, %d switches" % (free / 1e6, gc.mem_alloc() // 1024, n)


def audit():
    """What the apps share and must leave as they found it: the audio pumps,
    I2S, the USB host and its streams, the SD card, the foreground loop."""
    out = {}
    try:
        import audiopump

        out["audiopump"] = bool(audiopump.running())
    except Exception as e:
        out["audiopump"] = repr(e)
    try:
        import _audioif

        out["i2s"] = _audioif.i2s_state()
    except (ImportError, AttributeError):
        out["i2s"] = None  # no I2S port here: a desktop
    except Exception as e:
        out["i2s"] = repr(e)
    try:
        from audiodev import pump

        h = pump.health() or {}
        out["pump_clients"] = h.get("clients")
        out["pump_running"] = h.get("running")
    except Exception as e:
        out["pump"] = repr(e)
    try:
        import usb.core

        # find() would start the host, which an audit must not do: count only
        # when something already has. usb.core has no public "is it running".
        running = getattr(usb.core, "_started", None) is not None
        out["host_devices"] = len(list(usb.core.find(find_all=True))) if running else None
    except Exception as e:
        out["usb"] = repr(e)
    try:
        import os

        os.stat("/sd")
        out["sd"] = "mounted"
    except OSError:
        out["sd"] = None
    out["foreground"] = foreground.current() is not None
    scope = launcher.scope if launcher is not None else None
    out["timers"] = len(scope.timers) if scope is not None else None
    out["free"] = gc.mem_free() if hasattr(gc, "mem_free") else None
    return out
