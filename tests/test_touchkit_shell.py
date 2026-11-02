# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""touchkit's Home button: the board's boot script only makes a TouchShell."""

import os
import sys
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "lib"))


class _Launcher:
    home = "home"
    current = "mp3"

    def __init__(self):
        self.asked = []

    def request(self, name):
        self.asked.append(name)


class HomeButtonTest(unittest.TestCase):
    def test_the_button_goes_home_with_no_more_setup_than_making_the_shell(self):
        fakes = {
            "lvgl": mock.MagicMock(),
            "multimer": mock.MagicMock(),
            "touchkit.ui": mock.MagicMock(),
        }
        with mock.patch.dict(sys.modules, fakes):
            sys.modules.pop("touchkit.shell", None)
            sys.modules.pop("touchkit", None)
            from touchkit import shell

            shell.ui = fakes["touchkit.ui"]
            calls = []
            fakes["lvgl"].button.return_value.add_event_cb.side_effect = (
                lambda cb, *a: calls.append(cb)
            )
            launcher = _Launcher()
            with mock.patch.object(shell.TouchShell, "_boot_button"):
                shell.TouchShell(launcher)
            self.assertEqual(len(calls), 1)
            calls[0](types.SimpleNamespace())
            self.assertEqual(launcher.asked, ["home"])
            sys.modules.pop("touchkit.shell", None)
            sys.modules.pop("touchkit", None)


if __name__ == "__main__":
    unittest.main()
