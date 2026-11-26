# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Home and the board's own apps: `home_contract.py` on CPython and MicroPython, and
each plant in its ``PLANTS`` failing it.

    python -m unittest discover -s tests/appkit -p test_home.py

It needs LVGL on the interpreter; without it, it skips.
"""

import sys
import unittest

from _harness import TESTS, need_micropython, run

CONTRACT = TESTS / "home_contract.py"
PLANTS = ("tall_tabs", "home_word", "name_not_saved", "no_category", "why_unsaid",
          "one_line", "every_space", "small_icon", "big_everywhere")


def _run(case, interpreter, plant=None):
    extra = {"HOME_PLANT": plant} if plant else None
    r = run([*interpreter, CONTRACT], timeout=120, extra_env=extra)
    if r.returncode == 2:
        case.skipTest(r.stdout.strip())
    return r


class HomeCPython(unittest.TestCase):
    def test_the_contract_holds(self):
        r = _run(self, [sys.executable])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_each_plant_fails_it(self):
        for plant in PLANTS:
            with self.subTest(plant=plant):
                r = _run(self, [sys.executable], plant)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)


class HomeMicroPython(unittest.TestCase):
    def test_the_contract_holds(self):
        r = _run(self, [need_micropython(self), "-X", "heapsize=16M"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
