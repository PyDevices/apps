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
        forecast.requests.get.side_effect = OSError(110)
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
        forecast.requests.get.return_value.json.return_value = REPLY
        self.assertTrue(forecast.fetch())
        self.assertIn("latitude=36.24&longitude=-90.06", forecast.requests.get.call_args[0][0])
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
        forecast.requests.get.return_value.json.return_value = {
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
        lt.machine = mock.MagicMock()
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
        lt.machine = mock.MagicMock()  # as on a board
        lt.requests = mock.MagicMock()
        if error is not None:
            lt.requests.get.side_effect = error
        else:
            lt.requests.get.return_value.json.return_value = reply
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
        lt.requests.get.assert_not_called()
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
        lt.machine = None
        self.assertFalse(lt.follow_ip_zone())
        lt.requests.get.assert_not_called()

    def test_the_daily_resync_asks_again(self):
        lt = self._localtime(reply=self.CHICAGO)
        lt.sync = mock.MagicMock(return_value=True)
        lt._synced_at = None
        lt.resync_if_due()
        self.assertEqual(lt.offset_s, -21600)
        lt.requests.get.return_value.json.return_value = {
            "success": True,
            "timezone": {"id": "America/Chicago", "offset": -18000},
        }
        lt._synced_at = 0  # a day and more ago
        with mock.patch.object(lt, "is_set", return_value=True):
            lt.resync_if_due()
        self.assertEqual(lt.offset_s, -18000)  # daylight saving began

    def test_no_lookup_when_the_clock_could_not_be_set(self):
        lt = self._localtime(reply=self.CHICAGO)
        lt.sync = mock.MagicMock(return_value=False)
        lt.resync_if_due()
        lt.requests.get.assert_not_called()


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
    named = os.environ.get("PYDEVICES_MICROPYTHON") or shutil.which("micropython")
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
            if os.environ.get("PYDEVICES_REQUIRE_MICROPYTHON") == "1":
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


if __name__ == "__main__":
    unittest.main()
