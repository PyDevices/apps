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


class BootButtonTest(unittest.TestCase):
    def boot_pin(self, board):
        fakes = {
            "appkit": mock.MagicMock(),
            "lvgl": mock.MagicMock(),
            "multimer": mock.MagicMock(),
            "touchkit.ui": mock.MagicMock(),
            "board_config": board,
            "machine": mock.MagicMock(),
        }
        fakes["appkit"].Shell = object
        with mock.patch.dict(sys.modules, fakes):
            sys.modules.pop("touchkit.shell", None)
            sys.modules.pop("touchkit", None)
            from touchkit import shell

            s = types.SimpleNamespace(boot_pin="unset")
            with mock.patch("builtins.print") as printed:
                shell.TouchShell._boot_button(s)
            sys.modules.pop("touchkit.shell", None)
            sys.modules.pop("touchkit", None)
        return s.boot_pin, printed.call_count

    def test_a_board_without_the_role_says_nothing(self):
        # The S3 Touch-LCD-7's GPIO0 is a line of its RGB panel, so it has no
        # boot_button role, and Home is the button on the screen.
        self.assertEqual(self.boot_pin(types.SimpleNamespace()), (None, 0))

    def test_a_role_that_fails_says_why(self):
        class Board:
            @property
            def boot_button(self):
                raise OSError("pin busy")

        self.assertEqual(self.boot_pin(Board()), (None, 1))

    def test_a_board_with_the_role_takes_its_presses(self):
        pin = mock.MagicMock()
        self.assertEqual(self.boot_pin(types.SimpleNamespace(boot_button=pin)), (pin, 0))
        pin.irq.assert_called_once()


class ClockOnJoinTest(unittest.TestCase):
    """The clock is set when the board joins a network, not when an app asks."""

    def _net(self, connected, due):
        radio = types.SimpleNamespace(connected=connected)
        worker = mock.MagicMock()
        worker.pending.return_value = False
        localtime = types.SimpleNamespace(due=lambda: due, resync_if_due=object())
        fakes = {
            "lvgl": mock.MagicMock(),
            "wifi": types.SimpleNamespace(radio=radio, connect_from_secrets=mock.MagicMock()),
            "webrepl": mock.MagicMock(),
            "appkit.worker": types.SimpleNamespace(shared=lambda: worker),
            "deskkit": types.SimpleNamespace(localtime=localtime),
            "deskkit.localtime": localtime,
            "touchkit.settings": types.SimpleNamespace(get=lambda key, default=None: default),
        }
        return fakes, worker, localtime

    def _up(self, fakes):
        with mock.patch.dict(sys.modules, fakes):
            sys.modules.pop("touchkit.net", None)
            sys.modules.pop("touchkit", None)
            from touchkit import net

            result = net.up()
            timer = fakes["lvgl"].timer_create.call_args
            sys.modules.pop("touchkit.net", None)
            return net, result, timer

    def test_joining_sets_the_clock_on_the_worker(self):
        fakes, worker, localtime = self._net(connected=True, due=True)
        net, result, timer = self._up(fakes)
        self.assertTrue(result)
        worker.submit.assert_called_once_with(localtime.resync_if_due, key="touchkit.clock")
        self.assertEqual(timer.args[1], net._CLOCK_CHECK_MS)  # and checks again each minute

    def test_a_join_asks_once_and_leaves_retries_to_the_timer(self):
        fakes, worker, _ = self._net(connected=True, due=True)
        with mock.patch.dict(sys.modules, fakes):
            sys.modules.pop("touchkit.net", None)
            sys.modules.pop("touchkit", None)
            from touchkit import net

            for _ in range(5):  # an app polling up()
                net.up()
            self.assertEqual(worker.submit.call_count, 1)
            fakes["lvgl"].timer_create.call_args.args[0](None)  # a minute on, still unset
            self.assertEqual(worker.submit.call_count, 2)
            sys.modules.pop("touchkit.net", None)

    def test_a_set_clock_is_left_alone_until_a_day_has_passed(self):
        fakes, worker, _ = self._net(connected=True, due=False)
        self._up(fakes)
        worker.submit.assert_not_called()

    def test_nothing_is_asked_before_the_board_has_joined(self):
        fakes, worker, _ = self._net(connected=False, due=True)
        _, result, _ = self._up(fakes)
        self.assertFalse(result)
        worker.submit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
