# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""deskkit and the weather app's parts that need no screen and no network."""

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import unittest
from unittest import mock

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent
sys.path.insert(0, str(ROOT / "lib"))

REPLY = {
    "utc_offset_seconds": -18000,
    "current": {
        "time": "2026-11-03T21:15",
        "temperature_2m": 59.2,
        "apparent_temperature": 58.6,
        "weather_code": 63,
        "is_day": 0,
    },
    "daily": {
        "time": ["2026-11-03", "2026-11-04"],
        "weather_code": [63, 0],
        "temperature_2m_max": [64.0, 58.4],
        "temperature_2m_min": [51.3, 47.0],
        "precipitation_probability_max": [80, 0],
    },
}


def _forecast():
    fakes = {name: mock.MagicMock() for name in ("lvgl", "requests", "wifi_manager", "appkit", "appkit.data")}
    with mock.patch.dict(sys.modules, fakes):
        for name in ("deskkit", "deskkit.forecast", "deskkit.localtime"):
            sys.modules.pop(name, None)
        from deskkit import forecast

        return forecast, fakes


class ForecastTest(unittest.TestCase):
    def test_a_reply_becomes_what_the_screen_shows(self):
        forecast, _ = _forecast()
        got = forecast.parse(REPLY)
        self.assertEqual(got["temp"], 59.2)
        self.assertFalse(got["is_day"])
        self.assertEqual(got["as_of"], "21:15")
        self.assertEqual(got["utc_offset"], -18000)
        self.assertEqual([d[0] for d in got["days"]], ["Tue", "Wed"])
        self.assertEqual(got["days"][0][4], 80)

    def test_celsius_is_worked_out_on_the_board(self):
        forecast, _ = _forecast()
        forecast._place = {"units": "C"}
        self.assertEqual(forecast.degrees(212), 100)
        forecast._place = {"units": "F"}
        self.assertEqual(forecast.degrees(59.2), 59)

    def test_a_failed_fetch_keeps_the_last_forecast_and_retries_later(self):
        forecast, fakes = _forecast()
        forecast.net.requests.return_value.get.side_effect = OSError(110)
        forecast._place = {"lat": 1, "lon": 2}
        forecast.latest = "old"
        forecast.localtime.resync_if_due = lambda: None
        self.assertFalse(forecast.fetch())
        self.assertEqual(forecast.latest, "old")
        self.assertIsNotNone(forecast.last_error)
        self.assertFalse(forecast.is_stale())  # tried just now
        forecast._tried_at -= forecast.RETRY_S
        self.assertTrue(forecast.is_stale())


class IpPlaceTest(unittest.TestCase):
    """The forecast for the IP's city, until a place is chosen."""

    KENNETT = {"name": "Kennett", "lat": 36.24, "lon": -90.06, "units": "F", "from_ip": True}

    def _forecast(self):
        forecast, _ = _forecast()
        forecast._place_file = lambda: "/nonexistent/deskkit/place.json"
        forecast.ip_place = dict(self.KENNETT)
        forecast.localtime.resync_if_due = lambda: None
        forecast._save = mock.MagicMock()
        return forecast

    def test_a_chosen_place_wins_over_the_ips(self):
        forecast = self._forecast()
        self.assertEqual(forecast.current()["name"], "Kennett")
        forecast._place = {"name": "Boston", "lat": 1, "lon": 2}
        self.assertEqual(forecast.current()["name"], "Boston")

    def test_the_ips_place_gets_a_forecast_and_is_never_saved(self):
        forecast = self._forecast()
        forecast.net.requests.return_value.get.return_value.json.return_value = REPLY
        self.assertTrue(forecast.fetch())
        self.assertIn("latitude=36.24&longitude=-90.06", forecast.net.requests.return_value.get.call_args[0][0])
        self.assertEqual(forecast.localtime.offset_s, -18000)
        forecast._save.assert_not_called()
        self.assertIsNone(forecast.place())

    def test_units_on_the_ips_place_stay_in_ram(self):
        forecast = self._forecast()
        forecast.set_units("C")
        self.assertEqual(forecast.degrees(212), 100)
        forecast._save.assert_not_called()

    def test_choosing_a_zip_saves_it_and_keeps_the_units(self):
        forecast = self._forecast()
        forecast.ip_place["units"] = "C"
        forecast.net.requests.return_value.get.return_value.json.return_value = {
            "results": [{"name": "Boston", "latitude": 42.36, "longitude": -71.06}]
        }
        forecast.fetch = mock.MagicMock()
        got = forecast.choose("02108")
        self.assertEqual((got["zip"], got["units"]), ("02108", "C"))
        forecast._save.assert_called_once()
        self.assertEqual(forecast.current()["name"], "Boston")

    def test_keep_fresh_finds_the_place_first_then_fetches(self):
        forecast = self._forecast()
        forecast.ip_place = None
        lt = forecast.localtime
        lt.net = mock.MagicMock()
        lt.net.sets_clock.return_value = True  # as on a board
        lt._looked = False
        submitted = []
        scope = mock.MagicMock()
        scope.worker.submit.side_effect = lambda work, done, key: submitted.append((work, done))

        def look():
            forecast.ip_place = dict(self.KENNETT)
            lt._looked = True

        lt.resync_if_due = look
        forecast.keep_fresh(scope)
        work, done = submitted.pop()
        self.assertIs(work, look)
        work()
        done(None, None)
        self.assertIs(submitted.pop()[0], forecast.fetch)


class LocalTimeTest(unittest.TestCase):
    def test_a_date_header_reads_as_utc_fields(self):
        forecast, _ = _forecast()
        got = forecast.localtime.parse_http_date("Wed, 04 Nov 2026 02:36:50 GMT")
        self.assertEqual(got, (2026, 11, 4, 2, 36, 50))

    def test_a_bad_date_header_is_refused(self):
        forecast, _ = _forecast()
        with self.assertRaises(ValueError):
            forecast.localtime.parse_http_date("yesterday")

    def test_local_time_follows_the_offset(self):
        forecast, _ = _forecast()
        lt = forecast.localtime
        lt.offset_s = -18000
        with mock.patch.object(lt.time, "time", return_value=1793673000):  # 02:30 UTC
            self.assertEqual(lt.clock_time()[:2], (21, 30))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class StatusBarClockTest(unittest.TestCase):
    """The status bar's clock reads the zone deskkit found, as Clock does."""

    def test_the_bar_shows_the_same_local_time_as_clock(self):
        appkit = mock.MagicMock()
        fakes = {name: mock.MagicMock() for name in ("lvgl", "icons", "icons.lvgl", "requests", "wifi_manager",
                                                     "appkit.data")}
        fakes["appkit"] = appkit
        with mock.patch.dict(sys.modules, fakes):
            for name in ("deskkit", "deskkit.forecast", "deskkit.localtime", "appkit.net", "appkit.bar"):
                sys.modules.pop(name, None)
            # The real appkit.net and appkit.bar, by their files: the package
            # brings the Launcher and the Shell, which this needs neither of.
            appkit.net = _load("appkit.net", ROOT / "lib" / "appkit" / "net.py")
            appkit.__path__ = [str(ROOT / "lib" / "appkit")]
            bar = _load("appkit.bar", ROOT / "lib" / "appkit" / "bar.py")
            from deskkit import localtime

            localtime.offset_s = -21600  # UTC-6, as the IP lookup sets it
            with mock.patch.object(time, "time", return_value=1793673000):  # 02:30 UTC
                hour, minute, _ = localtime.clock_time()
                _, text = bar.clock_item().read()
        self.assertEqual((hour, minute), (20, 30))
        self.assertEqual(text, "20:30")


class SyncTest(unittest.TestCase):
    def _localtime(self):
        forecast, _ = _forecast()
        lt = forecast.localtime
        lt.net = mock.MagicMock()
        lt.net.sets_clock.return_value = True  # as on a board
        return lt

    def test_ntp_sets_the_clock(self):
        lt = self._localtime()
        self.assertTrue(lt.sync())
        lt.net.ntp.assert_called_once()
        lt.net.requests.assert_not_called()

    def test_where_ntp_is_blocked_a_date_header_sets_it(self):
        lt = self._localtime()
        lt.net.ntp.side_effect = OSError(110)
        resp = lt.net.requests.return_value.get.return_value
        resp.headers = {"date": "Wed, 04 Nov 2026 02:36:50 GMT"}
        with mock.patch("builtins.print"):
            self.assertTrue(lt.sync())
        lt.net.set_clock.assert_called_once_with(2026, 11, 4, 2, 36, 50)
        resp.close.assert_called_once()

    def test_a_missing_http_client_is_said_and_the_clock_stays_unset(self):
        lt = self._localtime()
        lt.net.ntp.side_effect = OSError(110)
        lt.net.requests.side_effect = ImportError("HTTP on CircuitPython needs adafruit_requests")
        with mock.patch("builtins.print") as said:
            self.assertFalse(lt.sync())
        self.assertIn("adafruit_requests", said.call_args[0][0])
        lt.net.set_clock.assert_not_called()


class IpZoneTest(unittest.TestCase):
    """The timezone from the board's IP address, while no place is chosen."""

    def _localtime(self, place=None, reply=None, error=None):
        forecast, _ = _forecast()
        lt = forecast.localtime
        # localtime imports forecast when it asks for the place: give it this one.
        here = {"deskkit": mock.MagicMock(), "deskkit.forecast": forecast}
        patcher = mock.patch.dict(sys.modules, here)
        patcher.start()
        self.addCleanup(patcher.stop)
        sys.modules["deskkit"].forecast = forecast
        lt.net = mock.MagicMock()
        lt.net.sets_clock.return_value = True  # as on a board
        self.http = lt.net.requests.return_value
        if error is not None:
            self.http.get.side_effect = error
        else:
            self.http.get.return_value.json.return_value = reply
        forecast.place = lambda: place
        return lt

    CHICAGO = {
        "success": True,
        "city": "Kennett",
        "country_code": "US",
        "latitude": 36.24,
        "longitude": -90.06,
        "timezone": {"id": "America/Chicago", "offset": -21600},
    }

    def test_a_reply_gives_the_zone_and_its_offset_now(self):
        lt = self._localtime()
        self.assertEqual(lt.parse_ip_zone(self.CHICAGO), ("America/Chicago", -21600))

    def test_a_failed_reply_is_refused(self):
        lt = self._localtime()
        with self.assertRaisesRegex(ValueError, "Reserved"):
            lt.parse_ip_zone({"success": False, "message": "Reserved range"})

    def test_with_no_place_the_clock_takes_the_ips_zone(self):
        lt = self._localtime(reply=self.CHICAGO)
        self.assertTrue(lt.follow_ip_zone())
        self.assertEqual((lt.zone, lt.offset_s), ("America/Chicago", -21600))
        with mock.patch.object(lt.time, "time", return_value=1793673000):  # 02:30 UTC
            self.assertEqual(lt.clock_time()[:2], (20, 30))

    def test_a_chosen_place_wins(self):
        lt = self._localtime(place={"utc_offset": -18000}, reply=self.CHICAGO)
        lt.offset_s = -18000
        self.assertFalse(lt.follow_ip_zone())
        self.http.get.assert_not_called()
        self.assertEqual(lt.offset_s, -18000)
        self.assertIsNone(lt.zone)

    def test_a_failed_lookup_keeps_utc_and_says_so_once(self):
        lt = self._localtime(error=OSError(110))
        with mock.patch("builtins.print") as said:
            self.assertFalse(lt.follow_ip_zone())
        self.assertIsNone(lt.offset_s)
        self.assertEqual(said.call_count, 1)
        self.assertIn("keeping UTC", said.call_args[0][0])

    def test_with_no_place_weather_starts_on_the_ips_city(self):
        lt = self._localtime(reply=self.CHICAGO)
        forecast = sys.modules["deskkit.forecast"]
        self.assertTrue(lt.follow_ip_zone())
        self.assertEqual(
            forecast.ip_place,
            {"name": "Kennett", "lat": 36.24, "lon": -90.06, "units": "F", "from_ip": True},
        )

    def test_outside_the_us_it_starts_in_celsius(self):
        reply = dict(self.CHICAGO, city="Lyon", country_code="FR")
        reply["timezone"] = {"id": "Europe/Paris", "offset": 3600}
        lt = self._localtime(reply=reply)
        lt.follow_ip_zone()
        self.assertEqual(sys.modules["deskkit.forecast"].ip_place["units"], "C")

    def test_a_daily_lookup_keeps_a_units_switch(self):
        lt = self._localtime(reply=self.CHICAGO)
        forecast = sys.modules["deskkit.forecast"]
        forecast.ip_place = {"name": "Kennett", "lat": 0, "lon": 0, "units": "C", "from_ip": True}
        lt.follow_ip_zone()
        self.assertEqual(forecast.ip_place["units"], "C")
        self.assertEqual(forecast.ip_place["lat"], 36.24)

    def test_a_reply_without_coordinates_still_sets_the_zone(self):
        reply = {"success": True, "timezone": {"id": "America/Chicago", "offset": -21600}}
        lt = self._localtime(reply=reply)
        self.assertTrue(lt.follow_ip_zone())
        self.assertIsNone(sys.modules["deskkit.forecast"].ip_place)

    def test_a_chosen_place_leaves_no_ip_place(self):
        lt = self._localtime(place={"utc_offset": -18000}, reply=self.CHICAGO)
        lt.follow_ip_zone()
        self.assertIsNone(sys.modules["deskkit.forecast"].ip_place)

    def test_weather_waits_for_the_lookup_then_falls_back_to_the_keypad(self):
        lt = self._localtime(error=OSError(110))
        lt.sync = mock.MagicMock(return_value=True)
        self.assertTrue(lt.finding())
        with mock.patch("builtins.print") as said:
            lt.resync_if_due()
        self.assertEqual(said.call_count, 1)
        self.assertFalse(lt.finding())
        self.assertIsNone(sys.modules["deskkit.forecast"].ip_place)

    def test_a_failed_clock_also_ends_the_wait(self):
        lt = self._localtime(reply=self.CHICAGO)
        lt.sync = mock.MagicMock(return_value=False)
        lt.resync_if_due()
        self.assertFalse(lt.finding())

    def test_a_desktop_keeps_its_own_timezone(self):
        lt = self._localtime(reply=self.CHICAGO)
        lt.net.sets_clock.return_value = False
        self.assertFalse(lt.follow_ip_zone())
        self.http.get.assert_not_called()

    def _in_a_browser(self, lt):
        lt.net.sets_clock.return_value = False  # the browser keeps the time
        patcher = mock.patch.object(lt, "sys", mock.Mock(platform="webassembly"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_browser_page_takes_the_place_from_the_visitors_ip(self):
        lt = self._localtime(reply=self.CHICAGO)
        self._in_a_browser(lt)
        lt._looked = False
        self.assertTrue(lt.finding(), "Weather waits for the lookup, not the ZIP pad")
        lt.resync_if_due()
        self.assertFalse(lt.finding())
        self.assertEqual(sys.modules["deskkit.forecast"].ip_place["name"], "Kennett")
        self.assertEqual(lt.offset_s, -21600)

    GEOJS = {"city": "Malden", "country_code": "US", "latitude": "36.557", "longitude": "-89.9665", "timezone": "America/Chicago"}

    def test_a_browser_page_asks_geojs_when_ipwhois_refuses(self):
        # ipwho.is counts a page's lookups per site, and refuses past the cap.
        lt = self._localtime()
        self._in_a_browser(lt)
        refused = {"success": False, "message": "Rate limit exceeded"}
        self.http.get.side_effect = lambda url, **kw: mock.Mock(json=mock.Mock(return_value=self.GEOJS if "geojs" in url else refused))
        lt.offset_s = None
        with mock.patch("builtins.print"):
            self.assertTrue(lt.follow_ip_zone())
        here = sys.modules["deskkit.forecast"].ip_place
        self.assertEqual((here["name"], here["lat"], here["lon"], here["units"]), ("Malden", 36.557, -89.9665, "F"))
        self.assertEqual(lt.zone, "America/Chicago")
        self.assertIsNone(lt.offset_s, "GeoJS gives no offset: the forecast brings it")

    def test_a_board_does_not_ask_geojs(self):
        lt = self._localtime(reply={"success": False, "message": "Rate limit exceeded"})
        with mock.patch("builtins.print"):
            self.assertFalse(lt.follow_ip_zone())
        self.assertEqual(self.http.get.call_count, 1)

    def test_a_browser_page_asks_once_a_day(self):
        lt = self._localtime(reply=self.CHICAGO)
        self._in_a_browser(lt)
        lt._synced_at = None
        lt.resync_if_due()
        lt.resync_if_due()  # each forecast fetch calls it
        self.assertEqual(self.http.get.call_count, 1)
        lt._synced_at -= lt._RESYNC_S
        lt.resync_if_due()
        self.assertEqual(self.http.get.call_count, 2)

    def test_the_daily_resync_asks_again(self):
        lt = self._localtime(reply=self.CHICAGO)
        lt.sync = mock.MagicMock(return_value=True)
        lt._synced_at = None
        lt.resync_if_due()
        self.assertEqual(lt.offset_s, -21600)
        self.http.get.return_value.json.return_value = {
            "success": True,
            "timezone": {"id": "America/Chicago", "offset": -18000},
        }
        lt._synced_at = 0  # a day and more ago
        with mock.patch.object(lt, "is_set", return_value=True):
            lt.resync_if_due()
        self.assertEqual(lt.offset_s, -18000)  # daylight saving began

    def test_a_failed_lookup_is_tried_again_within_minutes(self):
        # The first lookup after joining can be reset while the link settles.
        lt = self._localtime(error=OSError(104))
        lt.sync = mock.MagicMock(return_value=True)
        lt._synced_at = None
        lt._ip_retry_at = None
        lt._ip_wait_s = 0
        with mock.patch.object(lt.time, "time", return_value=1000), mock.patch.object(lt, "is_set", return_value=True):
            with mock.patch("builtins.print"):
                lt.resync_if_due()
            lt._synced_at = 1000
            self.assertIsNone(lt.offset_s)
            self.assertFalse(lt.due(), "not straight away")
        self.http.get.side_effect = None
        self.http.get.return_value.json.return_value = self.CHICAGO
        with mock.patch.object(lt.time, "time", return_value=1000 + 60), mock.patch.object(lt, "is_set", return_value=True):
            self.assertTrue(lt.due(), "a minute later, not a day")
            lt.resync_if_due()
            self.assertEqual(lt.offset_s, -21600)
            self.assertFalse(lt.due(), "and not again once it worked")

    def test_the_wait_between_failed_lookups_grows_to_an_hour(self):
        lt = self._localtime(error=OSError(104))
        lt._ip_retry_at = None
        lt._ip_wait_s = 0
        waits = []
        with mock.patch.object(lt.time, "time", return_value=0), mock.patch("builtins.print"):
            for _ in range(8):
                lt.follow_ip_zone()
                waits.append(lt._ip_wait_s)
        self.assertEqual(waits, [60, 120, 240, 480, 960, 1920, 3600, 3600])

    def test_no_lookup_when_the_clock_could_not_be_set(self):
        lt = self._localtime(reply=self.CHICAGO)
        lt.sync = mock.MagicMock(return_value=False)
        lt.resync_if_due()
        self.http.get.assert_not_called()


class IconsTest(unittest.TestCase):
    def test_every_weather_code_has_words(self):
        fakes = {"lvgl": mock.MagicMock()}
        path = ROOT / "apps" / "weather" / "icons.py"
        with mock.patch.dict(sys.modules, fakes):
            spec = importlib.util.spec_from_file_location("weather_icons", path)
            icons = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(icons)
        wmo = (0, 1, 2, 3, 45, 48, 51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 71, 73, 75, 77, 80, 81, 82, 85, 86, 95, 96, 99)
        for code in wmo:
            self.assertTrue(icons.name(code, True))
        self.assertEqual(icons.name(0, True), "Sunny")
        self.assertEqual(icons.name(0, False), "Clear")
        self.assertEqual(icons.name(65, True), "Rain")
        self.assertEqual(icons.name(73, True), "Snow")
        self.assertEqual(icons.name(96, True), "Thunderstorm")


def _micropython():
    named = os.environ.get("OMNIPYTHON_MICROPYTHON") or shutil.which("micropython")
    if named:
        return named
    for parent in TESTS.parents:
        candidate = parent / "bin" / "micropython"
        if candidate.is_file():
            return str(candidate)
    return None


def _has_lvgl(interpreter):
    try:
        return subprocess.run([interpreter, "-c", "import lvgl"], capture_output=True, timeout=60, check=False).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


class ContractTest(unittest.TestCase):
    def _run(self, plant=None):
        interpreter = _micropython()
        if interpreter is None or not _has_lvgl(interpreter):
            message = "no MicroPython with LVGL: the swipe checks did NOT run"
            if os.environ.get("OMNIPYTHON_REQUIRE_MICROPYTHON") == "1":
                self.fail(message)
            self.skipTest(message)
        env = dict(os.environ)
        if plant:
            env["DESK_PLANT"] = plant
        return subprocess.run(
            [interpreter, "-X", "heapsize=32M", str(TESTS / "desk_contract.py")],
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )

    def test_swipes_idle_and_night_on_real_lvgl(self):
        done = self._run()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("desk contract: ok", done.stdout)

    def test_the_checks_can_fail(self):
        for plant in ("swapped_swipes", "no_idle_return", "never_dark", "untuned_touch"):
            done = self._run(plant)
            self.assertIn("FAILED:", done.stdout, plant + " was not caught\n" + done.stdout + done.stderr)


class BoardClockTest(unittest.TestCase):
    """The network's time goes to the board's clock chip, where it has one."""

    def _sync(self, board):
        forecast, fakes = _forecast()
        lt = forecast.localtime
        fakes["appkit"].net.sets_clock.return_value = True
        lt.net = fakes["appkit"].net
        with mock.patch.dict(sys.modules, {"board_config": board}):
            self.assertTrue(lt.sync())

    def test_a_board_with_a_clock_chip_has_it_set(self):
        rtc = mock.MagicMock()
        board = mock.MagicMock(PERIPHERALS=frozenset({"rtc"}), rtc=rtc)
        self._sync(board)
        rtc.datetime.assert_called_once()
        t = rtc.datetime.call_args[0][0]
        self.assertEqual(len(t), 8)
        self.assertEqual(t[0], time.gmtime()[0])

    def test_a_board_without_one_is_left_alone(self):
        board = mock.MagicMock(PERIPHERALS=frozenset())
        self._sync(board)
        board.rtc.datetime.assert_not_called()


if __name__ == "__main__":
    unittest.main()
