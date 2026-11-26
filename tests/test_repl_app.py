# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The REPL app pages back through vtterm's scrollback on Shift+Page Up.

The app runs here with LVGL, the display and ``os.dupterm`` replaced by
stand-ins, so what's checked is its key handling and vtterm's screen. vtterm
(with palettes, the omnipython ``lib/`` folder and pygraphics) comes from ``$VTTERM_PATH``, else an omnipython
checkout beside this one; without it the test is skipped, and fails when
``REPL_REQUIRE=1`` is set.
"""

import importlib
import os
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
PAGE_UP = 1073741899
SHIFT = 0x0003
KEYDOWN = 0x300


def _find_vtterm():
    explicit = os.environ.get("VTTERM_PATH")
    candidates = [Path(explicit)] if explicit else [p / "omnipython" / "packages" for p in ROOT.parents]
    for c in candidates:
        if (c / "vtterm" / "vtterm" / "keys.py").is_file():
            return [str(c / "vtterm"), str(c / "palettes" / "lib"), str(c.parent / "lib")]
    return None


class _Display:
    width, height, color_depth = 640, 480, 16

    def __init__(self):
        self.blits = 0

    def blit_rect(self, buf, x, y, w, h):
        self.blits += 1

    def fill_rect(self, *a):
        pass

    def fill(self, c):
        pass

    def show(self):
        pass


class _Event:
    def __init__(self, key, mod):
        self.type, self.key, self.mod = KEYDOWN, key, mod


class _Keyboard:
    status = "fake"

    def __init__(self):
        self.pending = []

    def poll(self):
        out, self.pending = self.pending, []
        return out

    def close(self):
        pass


class _Scope:
    def __init__(self):
        self.root = mock.MagicMock()
        self.rect = (0, 0, 640, 480)
        self.timers = []
        self.closers = []

    def after(self, ms, fn):
        self.timers.append(fn)

    def every(self, ms, fn):
        self.ticks = fn

    def on_close(self, fn):
        self.closers.append(fn)

    def stop_timers(self):
        self.ticks = None

    def follow(self, kind, fn):
        self.follows = (kind, fn)
        return self.chosen


class _Port:
    """A board's REPL on a serial port: what it sends, and what it was sent."""

    def __init__(self, name):
        self.name = name
        self.error = None
        self.inbox = b""
        self.sent = b""
        self.closed = False

    def is_open(self):
        return not self.closed

    def read(self):
        out, self.inbox = self.inbox, b""
        return out or None

    def write(self, buf):
        self.sent += bytes(buf)
        return len(buf)

    def close(self):
        self.closed = True


class _WebSerial:
    def __init__(self):
        self.ports = []

    def open(self, endpoint, baudrate):
        port = _Port(endpoint.label)
        port.baudrate = baudrate
        self.ports.append(port)
        return port


class ReplScrollbackTest(unittest.TestCase):
    def setUp(self):
        paths = _find_vtterm()
        if paths is None:
            if os.environ.get("REPL_REQUIRE"):
                self.fail("no vtterm: set VTTERM_PATH")
            self.skipTest("no vtterm checkout: the REPL app's check did NOT run")
        for p in paths:
            sys.path.insert(0, p)
        self.addCleanup(lambda: [sys.path.remove(p) for p in paths])
        self.display = _Display()
        self.keyboard = _Keyboard()
        slots = {}

        def dupterm(stream, index=0):
            old = slots.get(index)
            slots[index] = stream
            return old

        patches = [
            mock.patch.dict(sys.modules, {
                "lvgl": mock.MagicMock(),
                "board_config": types.SimpleNamespace(display_drv=self.display),
            }),
            mock.patch.object(os, "dupterm", dupterm, create=True),
        ]
        sys.path.insert(0, str(ROOT))
        self.addCleanup(sys.path.remove, str(ROOT))
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        for name in [n for n in sys.modules if n == "vtterm" or n.startswith("vtterm.")]:
            del sys.modules[name]
        sys.modules.pop("apps.repl", None)
        self.repl = importlib.import_module("apps.repl")
        self.repl.start_all = lambda: ([self.keyboard], [])
        self.slots = slots

    def test_shift_page_up_pages_back_and_is_not_typed(self):
        scope = _Scope()
        self.repl.main(scope)
        scope.timers[0]()                      # start: the terminal and the dupterm slot
        console = self.slots[0]
        console.write("".join("line %d\r\n" % i for i in range(100)).encode())
        screen = console.terminal.screen
        self.assertGreater(len(screen.history), 0)
        self.assertEqual(screen.view, 0)
        self.keyboard.pending = [_Event(PAGE_UP, SHIFT)]
        scope.ticks()
        self.assertEqual(screen.view, screen.rows - 1)
        self.assertEqual(bytes(console._rx), b"\r", "only the first prompt was typed; the key never reached the program")
        console._rx[:] = b""
        self.keyboard.pending = [_Event(PAGE_UP, 0)]
        scope.ticks()
        self.assertEqual(bytes(console._rx), b"\x1b[5~", "a plain Page Up still goes to the program")


    def test_a_chosen_serial_port_is_a_terminal_to_its_board(self):
        """In a browser page, choosing a serial port moves the REPL to the
        board on it, and letting it go brings the page's own back."""
        serial = _WebSerial()
        self.repl._webserial = lambda: serial
        scope = _Scope()
        scope.chosen = [types.SimpleNamespace(label="Espressif (303a:1001)")]
        self.repl.main(scope)
        self.assertEqual(scope.follows[0], "serial")
        scope.timers[0]()
        self.assertNotIn(0, self.slots, "the page's own REPL was taken while a board is chosen")
        port = serial.ports[0]
        self.assertEqual(port.baudrate, self.repl.BAUDRATE)
        scope.ticks()
        self.assertEqual(port.sent, b"\r", "the board wasn't asked for a prompt")
        port.inbox = b"\r\n>>> "
        self.keyboard.pending = [_Event(ord("a"), 0)]
        scope.ticks()
        self.assertEqual(port.sent, b"\ra", "a key went to the board")
        term = scope.ticks.__self__.term
        shown = [term.screen.text(y) for y in range(term.screen.rows)]
        self.assertTrue(any(">>>" in row for row in shown), "the board's prompt isn't on the screen: %r" % shown[:3])
        scope.follows[1]([])
        self.assertTrue(port.closed, "letting the port go left it open")
        self.assertIn(0, self.slots, "the page's own REPL didn't come back")


if __name__ == "__main__":
    unittest.main()
