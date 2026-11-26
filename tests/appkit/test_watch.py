# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Watch, the home screen for round and small screens, and the watch's own
apps (Steps, Battery, LoRa): `watch_contract.py` and `watch_apps_contract.py`
on CPython and MicroPython, and each plant in their ``PLANTS`` failing them.

    python -m unittest discover -s tests/appkit -p test_watch.py

It needs LVGL on the interpreter; without it, it skips.
"""

import sys
import unittest

from _harness import TESTS, need_micropython, run

CONTRACT = TESTS / "watch_contract.py"
PLANTS = ("no_battery", "own_order", "tap_does_nothing", "face_forgotten", "no_arc", "hidden_listed")
APPS_CONTRACT = TESTS / "watch_apps_contract.py"
APPS_PLANTS = ("no_count", "charger_stuck", "radio_left_on", "no_percent")


def _run(case, interpreter, plant=None, contract=CONTRACT):
    # Each run gets a data root of its own: the saved face and the hidden apps start fresh.
    extra = {"WATCH_PLANT": plant} if plant else None
    r = run([*interpreter, contract], timeout=120, extra_env=extra)
    if r.returncode == 2:
        case.skipTest(r.stdout.strip())
    return r


class WatchCPython(unittest.TestCase):
    def test_the_contract_holds(self):
        r = _run(self, [sys.executable])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_each_plant_fails_it(self):
        for plant in PLANTS:
            with self.subTest(plant=plant):
                r = _run(self, [sys.executable], plant)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)

    def test_the_apps_contract_holds(self):
        r = _run(self, [sys.executable], contract=APPS_CONTRACT)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_each_apps_plant_fails_it(self):
        for plant in APPS_PLANTS:
            with self.subTest(plant=plant):
                r = _run(self, [sys.executable], plant, APPS_CONTRACT)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)


class WatchMicroPython(unittest.TestCase):
    def test_the_contract_holds(self):
        r = _run(self, [need_micropython(self), "-X", "heapsize=16M"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_the_apps_contract_holds(self):
        r = _run(self, [need_micropython(self), "-X", "heapsize=16M"], contract=APPS_CONTRACT)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
