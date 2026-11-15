# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""touchkit's Home button: the board's boot script only makes a TouchShell."""

import contextlib
import io
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
            "wifi": types.SimpleNamespace(radio=radio),
            "wifi_manager": types.SimpleNamespace(connect=mock.MagicMock(return_value=None)),
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

    def test_a_missing_deskkit_is_an_error_not_a_skip(self):
        fakes, worker, _ = self._net(connected=True, due=True)
        del fakes["deskkit"], fakes["deskkit.localtime"]
        fakes["deskkit"] = None  # an import of None raises ImportError
        with self.assertRaises(ImportError):
            self._up(fakes)
        worker.submit.assert_not_called()


if __name__ == "__main__":
    unittest.main()


class StartWebreplTest(unittest.TestCase):
    """WebREPL is started once, never over one that is listening, never on CircuitPython."""

    def _start(self, webrepl, implementation="micropython"):
        fakes = {
            "lvgl": mock.MagicMock(),
            "webrepl": webrepl,
            "touchkit.settings": types.SimpleNamespace(get=lambda key, default=None: default),
        }
        with mock.patch.dict(sys.modules, fakes):
            sys.modules.pop("touchkit.net", None)
            sys.modules.pop("touchkit", None)
            from touchkit import net

            out = io.StringIO()
            with mock.patch.object(net.sys, "implementation", types.SimpleNamespace(name=implementation)):
                with contextlib.redirect_stdout(out):
                    net.start_webrepl()
            sys.modules.pop("touchkit.net", None)
        return out.getvalue()

    def test_it_starts_webrepl_when_nothing_has(self):
        web = types.SimpleNamespace(listen_s=None, start=mock.MagicMock())
        self._start(web)
        web.start.assert_called_once_with()

    def test_it_leaves_a_listener_boot_py_started_alone(self):
        web = types.SimpleNamespace(listen_s=object(), start=mock.MagicMock())
        self._start(web)
        web.start.assert_not_called()

    def test_a_desktop_without_webrepl_is_quiet(self):
        with mock.patch.dict(sys.modules, {"webrepl": None}):
            self.assertEqual(self._start(None), "")

    def test_circuitpython_skips_it_without_a_word(self):
        web = mock.MagicMock()
        self.assertEqual(self._start(web, "circuitpython"), "")
        web.start.assert_not_called()


class OfflineJoinTest(unittest.TestCase):
    """An offline board joins through wifi_manager, which CircuitPython has too."""

    def _up(self, wifi, manager, cp=True):
        fakes = {
            "lvgl": mock.MagicMock(),
            "wifi": wifi,
            "wifi_manager": manager,
            "webrepl": mock.MagicMock(),
            "touchkit.settings": types.SimpleNamespace(get=lambda key, default=None: default),
        }
        with mock.patch.dict(sys.modules, fakes):
            sys.modules.pop("touchkit.net", None)
            sys.modules.pop("touchkit", None)
            from touchkit import net

            net._CP = cp
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                results = [net.up() for _ in range(3)]
            sys.modules.pop("touchkit.net", None)
        return results, out.getvalue()

    def test_circuitpython_joins_through_wifi_manager_without_printing_an_error(self):
        # CircuitPython's built-in wifi has a radio and nothing else.
        wifi = types.SimpleNamespace(radio=types.SimpleNamespace(connected=False))
        manager = types.SimpleNamespace(connect=mock.MagicMock(return_value=None))
        results, printed = self._up(wifi, manager)
        self.assertEqual(results, [False, False, False])
        self.assertEqual(printed, "")
        self.assertEqual(manager.connect.call_args.kwargs["setup"], False)

    def test_micropython_starts_one_join_in_the_background(self):
        wifi = types.SimpleNamespace(radio=types.SimpleNamespace(connected=False))
        manager = types.SimpleNamespace(connect=mock.MagicMock(return_value=None))
        results, printed = self._up(wifi, manager, cp=False)
        self.assertEqual(results, [False, False, False])
        self.assertEqual(printed, "")
        manager.connect.assert_called_once_with(setup=False, wait=False)

    def test_circuitpython_waits_longer_after_each_failed_join(self):
        # Its join blocks for seconds: an app polling every 500 ms mustn't
        # start one on every poll.
        wifi = types.SimpleNamespace(radio=types.SimpleNamespace(connected=False))
        manager = types.SimpleNamespace(connect=mock.MagicMock(return_value=None))
        now = [0]
        fakes = {
            "lvgl": mock.MagicMock(),
            "wifi": wifi,
            "wifi_manager": manager,
            "touchkit.settings": types.SimpleNamespace(get=lambda key, default=None: default),
        }
        with mock.patch.dict(sys.modules, fakes):
            sys.modules.pop("touchkit.net", None)
            sys.modules.pop("touchkit", None)
            from touchkit import net

            net._CP = True  # this board runs CircuitPython
            with mock.patch.object(net, "_now_ms", lambda: now[0]):
                tries = []
                for step in range(0, 800_000, 500):  # a poll every 500 ms
                    now[0] = step
                    before = manager.connect.call_count
                    net.up()
                    if manager.connect.call_count > before:
                        tries.append(step)
                self.assertEqual(tries, [0, 30_000, 90_000, 210_000, 450_000, 750_000])
                # Joined, the wait starts over from 30 s.
                wifi.radio.connected = True
                with mock.patch.object(net, "keep_time"), mock.patch.object(net, "start_webrepl"):
                    self.assertTrue(net.up())
                wifi.radio.connected = False
                now[0] += 1
                net.up()
                self.assertEqual(net._retry_ms, net._CP_RETRY_MS)
            sys.modules.pop("touchkit.net", None)


class DroppedNetworkTest(unittest.TestCase):
    """CircuitPython's radio stops retrying, so the board's poll never stops."""

    def _boot(self, wifi, joined, cp=True, no_clock=False):
        lvgl = mock.MagicMock()
        manager = types.SimpleNamespace(connect=mock.MagicMock(return_value="10.0.0.5" if joined else None))
        fakes = {
            "lvgl": lvgl,
            "wifi": wifi,
            "wifi_manager": manager,
            "touchkit.settings": types.SimpleNamespace(get=lambda key, default=None: default),
        }
        with mock.patch.dict(sys.modules, fakes):
            sys.modules.pop("touchkit.net", None)
            sys.modules.pop("touchkit", None)
            from touchkit import net

            net._CP = cp
            if no_clock:
                net._now_ms = mock.MagicMock(side_effect=AttributeError("monotonic"))
            with mock.patch.object(net, "keep_time"), mock.patch.object(net, "start_webrepl"):
                net.boot()
                polls = lvgl.timer_create.call_args_list
                poll = polls[0].args[0] if polls else None
                timer = mock.MagicMock()
                if poll:
                    poll(timer)
            sys.modules.pop("touchkit.net", None)
        return poll, timer

    def test_circuitpython_keeps_polling_after_joining_at_boot(self):
        wifi = types.SimpleNamespace(radio=types.SimpleNamespace(connected=True))
        poll, timer = self._boot(wifi, joined=True)
        self.assertIsNotNone(poll)
        timer.delete.assert_not_called()

    def test_circuitpython_keeps_polling_after_a_late_join(self):
        wifi = types.SimpleNamespace(radio=types.SimpleNamespace(connected=True))
        poll, timer = self._boot(wifi, joined=False)
        self.assertIsNotNone(poll)
        timer.delete.assert_not_called()

    def test_a_desktop_without_time_monotonic_boots_offline(self):
        # Windows MicroPython has no time.monotonic: only CircuitPython needs it.
        wifi = types.SimpleNamespace(radio=types.SimpleNamespace(connected=False))
        poll, _ = self._boot(wifi, joined=False, cp=False, no_clock=True)
        self.assertIsNotNone(poll)

    def test_micropython_stops_polling_once_joined(self):
        wifi = types.SimpleNamespace(radio=types.SimpleNamespace(connected=True))
        poll, timer = self._boot(wifi, joined=False, cp=False)
        timer.delete.assert_called_once()
