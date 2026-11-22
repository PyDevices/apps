# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""appkit's keys: `keys_contract.py` on CPython and MicroPython, and
each plant in its ``PLANTS`` failing it.

    python -m unittest discover -s tests/appkit -p test_keys.py

It needs LVGL on the interpreter; without it, it skips.
"""

import sys
import unittest

from _harness import TESTS, need_micropython, run

CONTRACT = TESTS / "keys_contract.py"
PLANTS = ("no_shift", "keyboard_stays", "focus_ignored", "encoder_cant_type", "keyboard_holds_dead_field")


def _run(case, interpreter, plant=None):
    extra = {"KEYS_PLANT": plant} if plant else None
    r = run([*interpreter, CONTRACT], timeout=120, extra_env=extra)
    if r.returncode == 2:
        case.skipTest(r.stdout.strip())
    return r


class KeysCPython(unittest.TestCase):
    def test_the_contract_holds(self):
        r = _run(self, [sys.executable])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_each_plant_fails_it(self):
        for plant in PLANTS:
            with self.subTest(plant=plant):
                r = _run(self, [sys.executable], plant)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)


class KeysMicroPython(unittest.TestCase):
    def test_the_contract_holds(self):
        r = _run(self, [need_micropython(self), "-X", "heapsize=16M"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
