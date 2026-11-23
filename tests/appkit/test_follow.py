# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Apps following their kinds: `follow_contract.py` on CPython and
MicroPython, and each plant in its ``PLANTS`` failing it.

    python -m unittest discover -s tests/appkit -p test_follow.py
"""

import sys
import unittest

from _harness import TESTS, need_micropython, run

CONTRACT = TESTS / "follow_contract.py"
PLANTS = (
    "forgets_to_unfollow",
    "every_event",
    "synth_deaf",
    "midi_deaf",
    "weather_deaf",
    "pick_ignored",
    "mp3_deaf",
    "midiengine_deaf",
    "cast_deaf",
)
#: The plants whose checks need LVGL and icons, which skip without them.
SCREEN_PLANTS = ("mp3_deaf", "midiengine_deaf", "cast_deaf")


def _run(case, interpreter, plant=None):
    extra = {"FOLLOW_PLANT": plant} if plant else None
    r = run([*interpreter, CONTRACT], timeout=180, extra_env=extra)
    if r.returncode == 2:
        case.skipTest(r.stdout.strip())
    return r


class FollowCPython(unittest.TestCase):
    def test_the_contract_holds(self):
        r = _run(self, [sys.executable])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(" 0 failed", r.stdout)

    def test_each_plant_fails_it(self):
        screens = "SKIPPED: the" not in _run(self, [sys.executable]).stdout
        for plant in PLANTS:
            if plant in SCREEN_PLANTS and not screens:
                continue
            with self.subTest(plant=plant):
                r = _run(self, [sys.executable], plant)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn("FAILED", r.stdout)


class FollowMicroPython(unittest.TestCase):
    def test_the_contract_holds(self):
        r = _run(self, [need_micropython(self), "-X", "heapsize=8M"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(" 0 failed", r.stdout)


if __name__ == "__main__":
    unittest.main()
