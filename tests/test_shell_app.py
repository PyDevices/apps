# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The Shell app puts upysh's commands in the REPL's namespace, or says upysh is missing.

The app runs here with LVGL, the display, touchkit's screen and ``os.dupterm``
replaced by stand-ins, and with a stand-in upysh, so what's checked is the
app's own part: which names reach ``__main__``, and that the REPL app starts.
The REPL app needs vtterm, found as ``test_repl_app`` finds it; without it the
test is skipped, and fails when ``REPL_REQUIRE=1`` is set.
"""

import __main__
import importlib
import os
import sys
import types
import unittest
from unittest import mock

from test_repl_app import ROOT, _Display, _find_vtterm, _Scope


class ShellAppTest(unittest.TestCase):
    def setUp(self):
        paths = _find_vtterm()
        if paths is None:
            if os.environ.get("REPL_REQUIRE"):
                self.fail("no vtterm: set VTTERM_PATH")
            self.skipTest("no vtterm checkout: the Shell app's check did NOT run")
        for p in paths:
            sys.path.insert(0, p)
        self.addCleanup(lambda: [sys.path.remove(p) for p in paths])
        slots = {}

        def dupterm(stream, index=0):
            old = slots.get(index)
            slots[index] = stream
            return old

        self.missing = []
        ui = types.SimpleNamespace(missing=lambda scope, short, text: self.missing.append(short))
        patches = [
            mock.patch.dict(sys.modules, {
                "lvgl": mock.MagicMock(),
                "board_config": types.SimpleNamespace(display_drv=_Display()),
                "touchkit": types.SimpleNamespace(ui=ui),
                "touchkit.ui": ui,
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
        for name in ("apps.repl", "apps.shell"):
            sys.modules.pop(name, None)
        self.shell = importlib.import_module("apps.shell")
        sys.modules["apps.repl"].start_all = lambda: ([], [])
        self.slots = slots

    def _upysh(self):
        upysh = types.ModuleType("upysh")
        upysh.ls = object()
        upysh.cat = lambda f: None
        upysh._private = object()
        self.addCleanup(lambda: [delattr(__main__, n) for n in ("ls", "cat") if hasattr(__main__, n)])
        return upysh

    def test_upysh_names_reach_the_prompt_and_the_repl_starts(self):
        upysh = self._upysh()
        scope = _Scope()
        with mock.patch.dict(sys.modules, {"upysh": upysh}):
            self.shell.main(scope)
        self.assertIs(__main__.ls, upysh.ls)
        self.assertIs(__main__.cat, upysh.cat)
        self.assertFalse(hasattr(__main__, "_private"), "only upysh's public names, as from upysh import * gives")
        scope.timers[0]()  # the REPL app's start: the terminal and the dupterm slot
        self.assertIn(0, self.slots, "the REPL app took the dupterm slot")
        self.assertEqual(self.missing, [])

    def test_without_upysh_it_says_so_and_leaves_the_repl_alone(self):
        scope = _Scope()
        with mock.patch.dict(sys.modules, {"upysh": None}):
            self.shell.main(scope)
        self.assertEqual(self.missing, ["upysh isn't installed"])
        self.assertEqual(scope.timers, [], "the REPL app never started")
        self.assertEqual(self.slots, {})


if __name__ == "__main__":
    unittest.main()
