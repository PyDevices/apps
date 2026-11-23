# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""appkit's connections: `connections_checks.py` on CPython and MicroPython,
and each of its plants failing it.

    python -m unittest discover -s tests/appkit -p test_connections.py
"""

import sys
import unittest

from _harness import TESTS, need_micropython, run

CHECKS = TESTS / "connections_checks.py"
PLANTS = ("no_wifi", "board_finds_rokus", "board_skips_audio", "noisy_absence", "starts_usb_host", "never_starts_usb_host")


def _run(interpreter, plant=None):
    extra = {"CONNECTIONS_PLANT": plant} if plant else None
    return run([*interpreter, CHECKS], timeout=120, extra_env=extra)


class ConnectionsCPython(unittest.TestCase):
    def test_the_checks_pass(self):
        r = _run([sys.executable])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_each_plant_fails_them(self):
        for plant in PLANTS:
            with self.subTest(plant=plant):
                r = _run([sys.executable], plant)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)


class ConnectionsMicroPython(unittest.TestCase):
    def test_the_checks_pass(self):
        r = _run([need_micropython(self)])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_each_plant_fails_them(self):
        interpreter = need_micropython(self)
        for plant in PLANTS:
            with self.subTest(plant=plant):
                r = _run([interpreter], plant)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
