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

In a browser page there is no REPL of the page's own, so the app is a
terminal to a board's: plug the board into the computer, choose it under
Serial ports in Connections (Chrome or Edge), and its REPL comes here, typed
on the computer's keyboard. Choosing another port moves the terminal there.
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
    if not hasattr(os, "dupterm"):
        return _main_serial(scope)
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
    status.set_text("Starting")
    rows_h = (h - STATUS_H) // 16 * 16
    st = {"console": None, "sources": [], "missing": [], "shown": None}

    def show_status(waiting=False):
        parts = [src.status for src in st["sources"]] + st["missing"]
        if waiting:
            parts.insert(0, "WebREPL is connected: the REPL comes here when it leaves")
        text = "   ".join(parts)
        if text != st["shown"]:
            st["shown"] = text
            status.set_text(text)

    def start(_t=None):
        # After LVGL has painted the root, or it would paint over the terminal.
        area = _Area(display_drv, x, y, w, rows_h)
        st["console"] = Console(Terminal(area, palette=AnsiPalette(length=256, color_depth=16)))
        st["sources"], st["missing"] = start_all()
        show_status()
        take()

    def take(_t=None):
        console = st["console"]
        try:
            console.attach(0)
        except OSError:
            show_status(waiting=True)
            scope.after(WAIT_MS, take)
            return
        show_status()
        fg = sys.modules.get("appkit.foreground")
        if fg is not None and fg._serving:
            # The REPL runs once the main loop returns; timers keep going.
            fg.stop()
        else:
            console.push(b"\r")  # a fresh prompt drawn here
        scope.every(TICK_MS, tick)

    def tick(_t=None):
        console = st["console"]
        app_cursor = console.terminal.screen.app_cursor
        out = None
        for src in st["sources"]:
            try:
                evs = src.poll()
            except Exception as e:  # noqa: BLE001 - shown; the source keeps trying
                evs = ()
                src.status = str(e)
            for e in evs:
                if e.type == KEYDOWN:
                    if scroll_key(console.terminal.screen, e.key, e.mod):
                        continue
                    b = key_bytes(e.key, e.mod, app_cursor)
                    if b:
                        out = b if out is None else out + b
        if out:
            console.push(out)
        console.refresh()
        show_status()

    def close():
        console = st["console"]
        if console is not None:
            console.detach()
        for src in st["sources"]:
            try:
                src.close()
            except Exception as e:  # noqa: BLE001 - closing the rest matters more
                print("repl app: closing", src, e)

    scope.on_close(close)
    scope.after(150, start)


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


def _main_serial(scope):
    """A terminal to the board on the serial port chosen in Connections: a browser page's REPL."""
    import webserial

    status, x, y, w, rows_h = _root(scope)
    status.set_text("Starting")
    st = {"term": None, "port": None, "sources": [], "shown": None, "said": None}

    def say(text):
        if text != st["shown"]:
            st["shown"] = text
            status.set_text(text)

    def use(endpoints):
        port = st["port"]
        if port is not None:
            st["port"] = None
            port.close()
        if not endpoints:
            say(CHOOSE_TEXT)
            return
        try:
            st["port"] = webserial.open(endpoints[0], BAUDRATE)
        except OSError as e:
            say(str(e))
            return
        say("Opening %s" % st["port"].name)
        st["said"] = None

    def start(_t=None):
        # After LVGL has painted the root, or it would paint over the terminal.
        area = _Area(display_drv, x, y, w, rows_h)
        st["term"] = Terminal(area, palette=AnsiPalette(length=256, color_depth=16))
        st["sources"] = start_all()[0]  # the page's own keyboard; a board's USB and BLE don't apply
        use(scope.follow("serial", use))
        scope.every(TICK_MS, tick)

    def tick(_t=None):
        term = st["term"]
        port = st["port"]
        out = None
        for src in st["sources"]:
            try:
                evs = src.poll()
            except Exception:  # noqa: BLE001 - the source keeps trying
                evs = ()
            for e in evs:
                if e.type == KEYDOWN:
                    if scroll_key(term.screen, e.key, e.mod):
                        continue
                    b = key_bytes(e.key, e.mod, term.screen.app_cursor)
                    if b:
                        out = b if out is None else out + b
        if port is None:
            return
        if port.error:
            say("%s: %s" % (port.name, port.error))
            return
        if not port.is_open():
            return
        if st["said"] is None:
            st["said"] = port.name
            say(port.name)
            port.write(b"\r")  # a fresh prompt from the board
        answers = term.answers()
        if answers:
            out = answers if out is None else out + answers
        if out:
            port.write(out)
        data = port.read()
        if data:
            term.write(data)

    def close():
        port = st["port"]
        st["port"] = None
        if port is not None:
            port.close()
        for src in st["sources"]:
            try:
                src.close()
            except Exception as e:  # noqa: BLE001 - closing the rest matters more
                print("repl app: closing", src, e)

    scope.on_close(close)
    scope.after(150, start)
