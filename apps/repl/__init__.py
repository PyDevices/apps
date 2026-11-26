# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""REPL: the board's own Python prompt on its screen, typed on a keyboard.

A USB keyboard on the board's host port and a BLE keyboard both work; the
app finds each on its own, and finds it again after it's unplugged. The
terminal is vtterm, drawn straight into the panel's framebuffer under the
app's area, so colors, line editing and Ctrl-C into a running program all
work as they do over USB.

The REPL is MicroPython's, through ``os.dupterm``. Opening the app ends the
program's main loop, as Ctrl-C would, so the REPL can run; timers and the
other apps keep going. A board's one dupterm slot is shared with WebREPL:
while a WebREPL client is connected, the app waits for it to leave.

It needs vtterm (``mip.install("github:PyDevices/omnipython/packages/vtterm")``)
and firmware whose palettes has its ANSI palette. Shift+Page Up and Page Down
page back through what scrolled off the screen.

In a browser page the REPL is the page's own until a serial port is chosen
under Serial ports in Connections (Chrome or Edge): then the app is a
terminal to the board on that port, typed on the computer's keyboard.
Choosing another port moves the terminal there, and letting it go brings
the page's REPL back.
"""

import os
import sys

import lvgl as lv
from board_config import display_drv
from palettes.ansi import AnsiPalette
from vtterm import Terminal
from vtterm.console import Console
from vtterm.keyboards import start_all
from vtterm.keys import key_bytes, scroll_key

#: How often keys are read and output drawn, in ms.
TICK_MS = 20
#: Height of the keyboard status line under the terminal, in pixels.
STATUS_H = 20
#: events.KEYDOWN
KEYDOWN = 0x300
#: How often the app asks for the dupterm slot while WebREPL holds it, in ms.
WAIT_MS = 1000
#: The speed a board's serial REPL runs at, in a browser page.
BAUDRATE = 115200
#: What the status line says in a browser page before a port is chosen.
CHOOSE_TEXT = "Choose a board under Serial ports in Connections"


class _Area:
    """The part of the panel under the app's root, as a display vtterm draws on.

    Rows go straight into the framebuffer, and only the rows drawn are made
    visible: LVGL owns the rest of the panel and its buffer swaps.
    """

    color_depth = 16

    def __init__(self, display, x, y, w, h):
        self.display = display
        self.x = x
        self.y = y
        self.width = w
        self.height = h
        self._box = None

    def blit_rect(self, buf, x, y, w, h):
        self.display.blit_rect(buf, self.x + x, self.y + y, w, h)
        b = self._box
        self._box = (y, y + h) if b is None else (min(b[0], y), max(b[1], y + h))

    def fill(self, color):
        self.display.fill_rect(self.x, self.y, self.width, self.height, color)
        self._box = (0, self.height)

    def show(self):
        b, self._box = self._box, None
        if b is None:
            return
        flush = getattr(self.display, "flush_rect", None)
        if flush is None or not flush(self.x, self.y + b[0], self.width, b[1] - b[0]):
            self.display.show()


def main(scope):
    status, x, y, w, rows_h = _root(scope)
    status.set_text("Starting")
    shown = [None]

    def say(text):
        if text != shown[0]:
            shown[0] = text
            status.set_text(text)

    def area():
        return _Area(display_drv, x, y, w, rows_h)

    serial = _webserial()
    chosen = []
    mode = [None]

    def switch(endpoints):
        want = _Serial if endpoints or not hasattr(os, "dupterm") else _Own
        now = mode[0]
        if now is not None and type(now) is want:
            now.use(endpoints)
            return
        if now is not None:
            now.stop()
            scope.stop_timers()
        mode[0] = want(scope, area, say)
        mode[0].start(endpoints)

    if serial is not None:
        chosen = scope.follow("serial", switch)
    elif not hasattr(os, "dupterm"):
        say("This Python has no REPL to show")
        return

    def close():
        if mode[0] is not None:
            mode[0].stop()

    scope.on_close(close)
    # After LVGL has painted the root, or it would paint over the terminal.
    scope.after(150, lambda _t=None: switch(chosen))


def _webserial():
    """The `webserial` module in a browser page, or None elsewhere."""
    if sys.platform not in ("webassembly", "emscripten"):
        return None
    try:
        import webserial
    except ImportError:
        return None
    return webserial


def _keys(sources, terminal):
    """The bytes the keys pressed since the last call type, or None."""
    out = None
    for src in sources:
        try:
            evs = src.poll()
        except Exception as e:  # noqa: BLE001 - shown; the source keeps trying
            evs = ()
            src.status = str(e)
        for e in evs:
            if e.type == KEYDOWN:
                if scroll_key(terminal.screen, e.key, e.mod):
                    continue
                b = key_bytes(e.key, e.mod, terminal.screen.app_cursor)
                if b:
                    out = b if out is None else out + b
    return out


def _close_all(sources):
    for src in sources:
        try:
            src.close()
        except Exception as e:  # noqa: BLE001 - closing the rest matters more
            print("repl app: closing", src, e)


class _Own:
    """This Python's own REPL, through ``os.dupterm``."""

    def __init__(self, scope, area, say):
        self.scope = scope
        self.area = area
        self.say = say
        self.console = None
        self.sources = []
        self.missing = []

    def status(self, waiting=False):
        parts = [src.status for src in self.sources] + self.missing
        if waiting:
            parts.insert(0, "WebREPL is connected: the REPL comes here when it leaves")
        self.say("   ".join(parts))

    def start(self, endpoints):
        self.console = Console(Terminal(self.area(), palette=AnsiPalette(length=256, color_depth=16)))
        self.sources, self.missing = start_all()
        self.status()
        self.take()

    def use(self, endpoints):
        pass

    def take(self, _t=None):
        try:
            self.console.attach(0)
        except OSError:
            self.status(waiting=True)
            self.scope.after(WAIT_MS, self.take)
            return
        self.status()
        fg = sys.modules.get("appkit.foreground")
        if fg is not None and fg._serving:
            # The REPL runs once the main loop returns; timers keep going.
            fg.stop()
        else:
            self.console.push(b"\r")  # a fresh prompt drawn here
        self.scope.every(TICK_MS, self.tick)

    def tick(self, _t=None):
        console = self.console
        out = _keys(self.sources, console.terminal)
        if out:
            console.push(out)
        console.refresh()
        self.status()

    def stop(self):
        if self.console is not None:
            self.console.detach()
        _close_all(self.sources)
        self.sources = []


class _Serial:
    """A terminal to the board on the serial port chosen in Connections."""

    def __init__(self, scope, area, say):
        self.scope = scope
        self.say = say
        self.term = Terminal(area(), palette=AnsiPalette(length=256, color_depth=16))
        self.sources = start_all()[0]  # the page's own keyboard; a board's USB and BLE don't apply here
        self.port = None
        self.ready = False

    def start(self, endpoints):
        self.use(endpoints)
        self.scope.every(TICK_MS, self.tick)

    def use(self, endpoints):
        self._let_go()
        if not endpoints:
            self.say(CHOOSE_TEXT)
            return
        try:
            self.port = _webserial().open(endpoints[0], BAUDRATE)
        except OSError as e:
            self.say(str(e))
            return
        self.say("Opening %s" % self.port.name)

    def tick(self, _t=None):
        term = self.term
        out = _keys(self.sources, term)
        port = self.port
        if port is None:
            return
        if port.error:
            self.say("%s: %s" % (port.name, port.error))
            return
        if not port.is_open():
            return
        if not self.ready:
            self.ready = True
            self.say(port.name)
            port.write(b"\r")  # a fresh prompt from the board
        answers = term.answers()
        if answers:
            out = answers if out is None else out + answers
        if out:
            port.write(out)
        data = port.read()
        if data:
            term.write(data)

    def _let_go(self):
        port, self.port = self.port, None
        self.ready = False
        if port is not None:
            port.close()

    def stop(self):
        self._let_go()
        _close_all(self.sources)
        self.sources = []


def _root(scope):
    """Paint the app's root black and put the status line under it; ``(status, x, y, w, rows_h)``."""
    root = scope.root
    root.remove_flag(lv.obj.FLAG.SCROLLABLE)
    root.set_style_bg_color(lv.color_hex(0), 0)
    root.set_style_bg_opa(lv.OPA.COVER, 0)
    x, y, w, h = scope.rect
    status = lv.label(root)
    status.set_style_text_color(lv.color_hex(0x5FAFAF), 0)
    status.set_style_text_font(lv.font_montserrat_14, 0)
    status.set_long_mode(lv.label.LONG_MODE.CLIP)
    status.set_width(w - 8)
    status.align(lv.ALIGN.BOTTOM_LEFT, 4, -2)
    return status, x, y, w, (h - STATUS_H) // 16 * 16
