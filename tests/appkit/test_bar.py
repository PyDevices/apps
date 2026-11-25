# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""appkit's keys: `bar_contract.py` on CPython and MicroPython, and
each plant in its ``PLANTS`` failing it.

    python -m unittest discover -s tests/appkit -p test_bar.py

It needs LVGL on the interpreter; without it, it skips.
"""

import sys
import unittest

from _harness import TESTS, need_micropython, run

CONTRACT = TESTS / "bar_contract.py"
PLANTS = ("redraws_all", "root_under_bar", "items_stay", "overlays_die", "home_everywhere", "no_way_home",
          "touch_header_behind_bar", "mirror_hidden", "gauge_ignored", "status_over_title", "header_kept",
          "row_always", "row_never", "row_late", "home_untitled", "round_row_off")


def _run(case, interpreter, plant=None):
    extra = {"BAR_PLANT": plant} if plant else None
    r = run([*interpreter, CONTRACT], timeout=120, extra_env=extra)
    if r.returncode == 2:
        case.skipTest(r.stdout.strip())
    return r


class BarCPython(unittest.TestCase):
    def test_the_contract_holds(self):
        r = _run(self, [sys.executable])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_each_plant_fails_it(self):
        for plant in PLANTS:
            with self.subTest(plant=plant):
                r = _run(self, [sys.executable], plant)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)


class BarMicroPython(unittest.TestCase):
    def test_the_contract_holds(self):
        r = _run(self, [need_micropython(self), "-X", "heapsize=16M"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
