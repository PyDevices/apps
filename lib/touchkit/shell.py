# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""touchkit.shell -- the board's chrome and launcher.

* `TouchShell` shows appkit's status bar along the top, with Home on it,
  and gives every app but Home a header below it: its title, and a status
  line at the right (``scope.status``, see ``touchkit.ui.status``).
  ``scope.root`` is the area below that. The bar and the header together
  are ``ui.HEADER`` tall. An app whose ``app.json`` says ``"bar": "none"``
  gets the whole screen, with a Home button on LVGL's system layer, where it
  never presses the app's own widgets. Without the bar (``bar=False``) every
  app gets the header with that Home button at its left. The board's BOOT
  button goes home too, through a pin interrupt.
* `TouchLauncher` keeps a short history of switches for System,
  and takes the USB sound card off when the next app isn't one that plays
  through it, so the PC goes back to its own speakers.

Work too heavy for a timer runs through appkit's ``scope.foreground()``,
and ``main.py`` ends in ``appkit.serve()``.
"""

import gc

import lvgl as lv
import multimer
from multimer import ticks_diff, ticks_ms

from appkit import Launcher, Shell, foreground

from . import ui

#: How often LVGL reads the touch panel, in ms, unless an app asks otherwise.
TOUCH_MS = 33

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


def _under_cap(shell):
    """Whether the status bar is the compact cap: then the Home button is
    just its icon, clear of the cap."""
    bar = getattr(shell, "bar", None)
    return bar is not None and bar.compact


class TouchShell(Shell):
    """The board's look: the status bar, a header with the app's title and
    a status line, and BOOT going home. *bar* False leaves the bar off and
    puts a Home button in the header."""

    def __init__(self, launcher, *, data_root=None, bar=True):
        _set_launcher(launcher)
        ui.apply_theme()  # first: the Home button is made in Shell.__init__
        Shell.__init__(self, launcher, data_root=data_root, bar=bar)
        self.boot_pin = None
        if launcher.home is not None:
            self._boot_button()

    def make_home_button(self):
        b = lv.button(lv.layer_sys())
        b.set_size(ui.HEADER - 12 if _under_cap(self) else ui.HOME_W, ui.HEADER - 12)
        b.set_pos(6, 6)
        b.set_style_bg_color(lv.color_hex(0x2A3550), 0)
        b.set_style_radius(12, 0)
        lbl = lv.label(b)
        lbl.set_text(lv.SYMBOL.HOME if _under_cap(self) else lv.SYMBOL.HOME + "  Home")
        lbl.set_style_text_font(ui.font, 0)
        lbl.center()
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
        if bar:
            # Header and body share the area below the bar, which grows to
            # the whole screen while the app hides the bar.
            from appkit.bar import HEIGHT

            parent = self.bar_area(scr)
            parent.set_flex_flow(lv.FLEX_FLOW.COLUMN)
            parent.set_style_pad_row(0, 0)
            if self.bar.compact:  # the cap floats over the header; Home is at its left
                hdr_h, left = ui.HEADER, ui.HEADER - 12 + 24
            else:
                hdr_h, left = ui.HEADER - HEIGHT, 16
        else:
            parent = scr
            hdr_h = ui.HEADER
            left = ui.HOME_W + 24
        hdr = ui.plain(lv.obj(parent))
        hdr.set_size(w, hdr_h)
        hdr.set_style_bg_color(ui.PANEL, 0)
        hdr.set_style_bg_opa(lv.OPA.COVER, 0)
        title = self.launcher.info.get(scope.name, {}).get("title", scope.name)
        # A narrow screen gets the smaller font, and a title that still
        # doesn't fit ends in dots rather than running off the edge.
        f = ui.big if w >= 480 else ui.font
        t = ui.label(hdr, title, f, ui.ACCENT)
        t.set_long_mode(lv.label.LONG_MODE.DOTS)
        t.set_size(w - left - 16, f.line_height)
        t.align(lv.ALIGN.LEFT_MID, left, 0)
        status = ui.label(hdr, "", ui.small, ui.MUTED)
        status.align(lv.ALIGN.RIGHT_MID, -16, 0)
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
