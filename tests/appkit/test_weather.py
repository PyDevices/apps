# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Weather fits each screen it runs on: `weather_contract.py` at five sizes,
round and not, on CPython and MicroPython, and each plant in its ``PLANTS``
failing it at the size it breaks.

    python -m unittest discover -s tests/appkit -p test_weather.py

It needs LVGL on the interpreter; without it, it skips.
"""

import sys
import unittest

from _harness import TESTS, need_micropython, run

CONTRACT = TESTS / "weather_contract.py"
SIZES = ("240x240r", "320x240", "480x320", "800x480", "480x480r")
PLANTS = (("full_size", "240x240r"), ("corner", "800x480"), ("square_rows", "240x240r"))


def _run(case, interpreter, size, plant=None):
    extra = {"WEATHER_SIZE": size}
    if plant:
        extra["WEATHER_PLANT"] = plant
    r = run([*interpreter, CONTRACT], timeout=120, extra_env=extra)
    if r.returncode == 2:
        case.skipTest(r.stdout.strip())
    return r


class WeatherCPython(unittest.TestCase):
    def test_it_fits_every_size(self):
        for size in SIZES:
            with self.subTest(size=size):
                r = _run(self, [sys.executable], size)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_each_plant_fails_it(self):
        for plant, size in PLANTS:
            with self.subTest(plant=plant):
                r = _run(self, [sys.executable], size, plant)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)


class WeatherMicroPython(unittest.TestCase):
    def test_it_fits_every_size(self):
        for size in SIZES:
            with self.subTest(size=size):
                r = _run(self, [need_micropython(self), "-X", "heapsize=16M"], size)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
