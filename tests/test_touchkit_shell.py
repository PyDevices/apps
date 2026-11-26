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
            "icons": mock.MagicMock(),
            "icons.lvgl": mock.MagicMock(),
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
                shell.TouchShell(launcher, bar=False)
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
            "icons": mock.MagicMock(),
            "icons.lvgl": mock.MagicMock(),
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


class LendBootTest(unittest.TestCase):
    """An app that reads BOOT itself borrows it, and BOOT goes home again after."""

    def test_lent_boot_stops_going_home_until_given_back(self):
        fakes = {"appkit": mock.MagicMock(), "lvgl": mock.MagicMock(), "multimer": mock.MagicMock(),
                 "icons": mock.MagicMock(), "icons.lvgl": mock.MagicMock(),
                 "touchkit.ui": mock.MagicMock(), "machine": mock.MagicMock()}
        fakes["appkit"].Shell = object
        with mock.patch.dict(sys.modules, fakes):
            sys.modules.pop("touchkit.shell", None)
            sys.modules.pop("touchkit", None)
            from touchkit import shell

            pin = mock.MagicMock()
            s = types.SimpleNamespace(boot_pin=pin)
            give_back = shell.TouchShell.lend_boot(s)
            pin.irq.assert_called_once_with(handler=None)
            give_back()
            self.assertIs(pin.irq.call_args.kwargs["handler"], shell._boot_irq)
            none = types.SimpleNamespace(boot_pin=None)
            shell.TouchShell.lend_boot(none)()
            sys.modules.pop("touchkit.shell", None)
            sys.modules.pop("touchkit", None)


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
            "touchkit.settings": types.SimpleNamespace(
                get=lambda key, default=None: default, move_hostname=lambda: None
            ),
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
            "touchkit.settings": types.SimpleNamespace(
                get=lambda key, default=None: default, move_hostname=lambda: None
            ),
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
            "touchkit.settings": types.SimpleNamespace(
                get=lambda key, default=None: default, move_hostname=lambda: None
            ),
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
            "touchkit.settings": types.SimpleNamespace(
                get=lambda key, default=None: default, move_hostname=lambda: None
            ),
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
            "touchkit.settings": types.SimpleNamespace(
                get=lambda key, default=None: default, move_hostname=lambda: None
            ),
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


class _FakeStation:
    """One ``network.WLAN(STA_IF)``: what it was told, and what it reports."""

    def __init__(self, active, connected, status):
        self._active = active
        self._connected = connected
        self._status = status
        self.told = []

    def active(self, flag=None):
        if flag is None:
            return self._active
        self.told.append(("active", flag))
        self._active = flag

    def isconnected(self):
        return self._connected

    def status(self, what=None):
        return self._status

    def connect(self, *args):
        self.told.append(("connect",) + args)

    def disconnect(self):
        self.told.append(("disconnect",))


class BootPyJoinedTest(unittest.TestCase):
    """A board whose boot.py joined Wi-Fi keeps that connection through Home's boot."""

    def _fakes(self, station, listening):
        network = types.SimpleNamespace(
            STA_IF=0,
            STAT_IDLE=1000,
            STAT_CONNECTING=1001,
            STAT_GOT_IP=1010,
            WLAN=lambda _interface: station,
        )
        self.manager = types.SimpleNamespace(connect=mock.MagicMock(return_value=None))
        self.webrepl = types.SimpleNamespace(
            listen_s=object() if listening else None, start=mock.MagicMock()
        )
        self.lvgl = mock.MagicMock()
        return {
            "network": network,
            "lvgl": self.lvgl,
            "wifi": types.SimpleNamespace(radio=types.SimpleNamespace(connected=station._connected)),
            "wifi_manager": self.manager,
            "webrepl": self.webrepl,
            "touchkit.settings": types.SimpleNamespace(
                get=lambda key, default=None: default, move_hostname=lambda: None
            ),
        }

    def _boot(self, station, listening=False):
        fakes = self._fakes(station, listening)
        with mock.patch.dict(sys.modules, fakes):
            sys.modules.pop("touchkit.net", None)
            sys.modules.pop("touchkit", None)
            from touchkit import net

            net._CP = False
            with mock.patch.object(net, "keep_time") as keep_time:
                net.boot()
                self.keep_time = keep_time
                timers = self.lvgl.timer_create.call_args_list
                self.poll = timers[0].args[0] if timers else None
                self.net = net
                if self.poll:
                    self.timer = mock.MagicMock()
                    self.poll(self.timer)
            sys.modules.pop("touchkit.net", None)

    def test_a_connected_station_is_not_joined_again(self):
        station = _FakeStation(active=True, connected=True, status=1010)
        self._boot(station, listening=True)
        self.manager.connect.assert_not_called()
        self.assertEqual(station.told, [])

    def test_a_connected_station_keeps_the_webrepl_boot_py_started(self):
        station = _FakeStation(active=True, connected=True, status=1010)
        self._boot(station, listening=True)
        self.webrepl.start.assert_not_called()

    def test_a_connected_station_still_gets_the_clock_kept(self):
        station = _FakeStation(active=True, connected=True, status=1010)
        self._boot(station, listening=True)
        self.keep_time.assert_called()

    def test_a_connected_station_without_webrepl_gets_it(self):
        station = _FakeStation(active=True, connected=True, status=1010)
        self._boot(station, listening=False)
        self.webrepl.start.assert_called_once_with()
        self.manager.connect.assert_not_called()

    def test_an_active_idle_station_is_joined_as_before(self):
        station = _FakeStation(active=True, connected=False, status=1000)
        self._boot(station)
        self.assertEqual(
            self.manager.connect.call_args_list,
            [mock.call(setup=False), mock.call(setup=False, wait=False)],
        )

    def test_a_station_that_was_never_started_is_joined_as_before(self):
        station = _FakeStation(active=False, connected=False, status=1000)
        self._boot(station)
        self.assertEqual(
            self.manager.connect.call_args_list,
            [mock.call(setup=False), mock.call(setup=False, wait=False)],
        )

    def test_circuitpython_is_left_to_its_own_path(self):
        # No network module there: wifi_manager joins, or finds itself joined.
        station = _FakeStation(active=True, connected=True, status=1010)
        fakes = self._fakes(station, listening=False)
        fakes["network"] = None  # an import of None raises ImportError
        with mock.patch.dict(sys.modules, fakes):
            sys.modules.pop("touchkit.net", None)
            sys.modules.pop("touchkit", None)
            from touchkit import net

            net._CP = True
            self.assertIsNone(net._station_state())
            sys.modules.pop("touchkit.net", None)


class WebreplOnTest(unittest.TestCase):
    def _on(self, listen_s):
        fakes = {
            "lvgl": mock.MagicMock(),
            "webrepl": types.SimpleNamespace(listen_s=listen_s, start=mock.MagicMock()),
            "touchkit.settings": types.SimpleNamespace(
                get=lambda key, default=None: default, move_hostname=lambda: None
            ),
        }
        with mock.patch.dict(sys.modules, fakes):
            sys.modules.pop("touchkit.net", None)
            sys.modules.pop("touchkit", None)
            from touchkit import net

            result = net.webrepl_on()
            sys.modules.pop("touchkit.net", None)
        return result

    def test_a_listener_boot_py_opened_counts(self):
        self.assertTrue(self._on(object()))

    def test_no_listener_does_not(self):
        self.assertFalse(self._on(None))
