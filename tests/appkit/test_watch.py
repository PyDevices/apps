# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Watch, the home screen for round and small screens: `watch_contract.py` on
CPython and MicroPython, and each plant in its ``PLANTS`` failing it.

    python -m unittest discover -s tests/appkit -p test_watch.py

It needs LVGL on the interpreter; without it, it skips.
"""

import sys
import unittest

from _harness import TESTS, need_micropython, run

CONTRACT = TESTS / "watch_contract.py"
PLANTS = ("no_battery", "own_order", "tap_does_nothing", "face_forgotten", "no_arc", "hidden_listed")


def _run(case, interpreter, plant=None):
    # Each run gets a data root of its own: the saved face and the hidden apps start fresh.
    extra = {"WATCH_PLANT": plant} if plant else None
    r = run([*interpreter, CONTRACT], timeout=120, extra_env=extra)
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


class WatchMicroPython(unittest.TestCase):
    def test_the_contract_holds(self):
        r = _run(self, [need_micropython(self), "-X", "heapsize=16M"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
