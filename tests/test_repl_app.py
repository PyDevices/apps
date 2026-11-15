# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The REPL app pages back through vtterm's scrollback on Shift+Page Up.

The app runs here with LVGL, the display and ``os.dupterm`` replaced by
stand-ins, so what's checked is its key handling and vtterm's screen. vtterm
(with palettes and pygraphics) comes from ``$VTTERM_PATH``, else a pydevices
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
    candidates = [Path(explicit)] if explicit else [p / "pydevices" / "packages" for p in ROOT.parents]
    for c in candidates:
        if (c / "vtterm" / "vtterm" / "keys.py").is_file():
            return [str(c / "vtterm"), str(c / "palettes" / "lib")]
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
            mock.patch("vtterm.keyboards.start_all", lambda: ([self.keyboard], [])),
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


if __name__ == "__main__":
    unittest.main()
