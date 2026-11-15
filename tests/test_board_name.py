# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The board's name comes from ``boarddev.name()``: touchkit moves an older
``settings.json`` hostname into it once, and passes no name of its own."""

import contextlib
import importlib.util
import inspect
import io
import json
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "lib"))

# touchkit.settings needs only appkit.data; the rest of appkit wants iconkit.
_spec = importlib.util.spec_from_file_location("appkit.data", os.path.join(ROOT, "lib", "appkit", "data.py"))
data = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(data)


class _BoardDev:
    """``boarddev``'s name, with its rule that a name has no spaces."""

    def __init__(self, saved="omnipython-a1b2c3"):
        self.saved = saved
        self.set = []

    def name(self, new=0):
        if new == 0:
            return self.saved
        if " " in new:
            raise ValueError("a board name holds only letters, digits and hyphens")
        self.set.append(new)
        self.saved = new


class _Touchkit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        data.set_root(self.tmp.name)
        self.addCleanup(data.set_root, None)
        self.boarddev = _BoardDev()
        fakes = {
            "boarddev": self.boarddev,
            "lvgl": mock.MagicMock(),
            "appkit": types.SimpleNamespace(data=data),
            "appkit.data": data,
        }
        patcher = mock.patch.dict(sys.modules, fakes)
        patcher.start()
        self.addCleanup(patcher.stop)
        for m in ("touchkit", "touchkit.settings", "touchkit.net"):
            sys.modules.pop(m, None)
        from touchkit import net, settings

        self.net, self.settings = net, settings

    def write(self, saved):
        with open(os.path.join(self.tmp.name, "settings.json"), "w") as f:
            json.dump(saved, f)

    def read(self):
        with open(os.path.join(self.tmp.name, "settings.json")) as f:
            return json.load(f)


class MoveHostnameTest(_Touchkit):
    def test_a_saved_hostname_becomes_the_board_name_once(self):
        self.write({"hostname": "kitchen", "webrepl": False})
        self.assertEqual(self.settings.move_hostname(), "kitchen")
        self.assertEqual(self.boarddev.set, ["kitchen"])
        self.assertEqual(self.read(), {"webrepl": False})
        self.assertFalse(self.settings.get("webrepl"))
        self.assertIsNone(self.settings.move_hostname())
        self.assertEqual(self.boarddev.set, ["kitchen"])

    def test_a_name_the_board_cannot_take_is_dropped_and_said(self):
        self.write({"hostname": "my panel"})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertIsNone(self.settings.move_hostname())
        self.assertIn("hostname isn't kept", out.getvalue())
        self.assertEqual(self.boarddev.set, [])
        self.assertEqual(self.read(), {})

    def test_no_settings_file_is_left_alone(self):
        self.assertIsNone(self.settings.move_hostname())
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "settings.json")))

    def test_hostname_is_no_longer_a_setting(self):
        self.assertNotIn("hostname", self.settings.DEFAULTS)


class NetTest(_Touchkit):
    def test_the_hostname_shown_is_the_board_name(self):
        self.boarddev.saved = "attic"
        self.assertEqual(self.net.hostname(), "attic")

    def test_boot_moves_the_hostname_then_joins_under_the_board_name(self):
        self.write({"hostname": "porch"})
        wm = types.SimpleNamespace(connect=mock.MagicMock(return_value="10.0.0.5"))
        with mock.patch.dict(sys.modules, {"wifi_manager": wm}), mock.patch.multiple(
            self.net, start_webrepl=mock.DEFAULT, keep_time=mock.DEFAULT, _needs_polling=lambda: False
        ):
            self.net.boot()
        wm.connect.assert_called_once_with(setup=False)
        self.assertEqual(self.boarddev.set, ["porch"])

    def test_setup_passes_no_name(self):
        wm = types.SimpleNamespace(run=mock.MagicMock(return_value=None))
        with mock.patch.dict(sys.modules, {"wifi_manager": wm}):
            self.net.setup_job()
        wm.run.assert_called_once_with()


class DeskClockTest(unittest.TestCase):
    def test_desk_clock_answers_to_the_board_name(self):
        import deskkit

        self.assertIsNone(inspect.signature(deskkit.run).parameters["hostname"].default)


if __name__ == "__main__":
    unittest.main()
