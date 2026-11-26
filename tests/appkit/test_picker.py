# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""appkit's picker: `picker_contract.py` on CPython and MicroPython, and
each plant in its ``PLANTS`` failing it.

    python -m unittest discover -s tests/appkit -p test_picker.py

It needs LVGL on the interpreter, endpointkit from the omnipython checkout
`_harness` finds, and icons: from that checkout on CPython, frozen into the
build on MicroPython. Without them it skips.
"""

import sys
import unittest

from _harness import TESTS, need_micropython, run

CONTRACT = TESTS / "picker_contract.py"
PLANTS = ("many_moves", "never_asks", "deaf", "keeps_listening", "no_pin_note", "no_address", "grant_asks_first")


def _run(case, interpreter, plant=None):
    extra = {"PICKER_PLANT": plant} if plant else None
    r = run([*interpreter, CONTRACT], timeout=120, extra_env=extra)
    if r.returncode == 2:
        case.skipTest(r.stdout.strip())
    return r


class PickerCPython(unittest.TestCase):
    def test_the_contract_holds(self):
        r = _run(self, [sys.executable])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_each_plant_fails_it(self):
        for plant in PLANTS:
            with self.subTest(plant=plant):
                r = _run(self, [sys.executable], plant)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)


class PickerMicroPython(unittest.TestCase):
    def test_the_contract_holds(self):
        r = _run(self, [need_micropython(self), "-X", "heapsize=16M"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
