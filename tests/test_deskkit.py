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


class ContractTest(unittest.TestCase):
    def _run(self, plant=None):
        interpreter = _micropython()
        if interpreter is None:
            if os.environ.get("PYDEVICES_REQUIRE_MICROPYTHON") == "1":
                self.fail("no MicroPython: the swipe checks did NOT run")
            self.skipTest("no MicroPython: the swipe checks did NOT run")
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
        for plant in ("swapped_swipes", "no_idle_return", "never_dark"):
            done = self._run(plant)
            self.assertNotEqual(done.returncode, 0, plant + " was not caught\n" + done.stdout)


if __name__ == "__main__":
    unittest.main()
