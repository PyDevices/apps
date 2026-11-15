# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Wander on a display with no window: `wander_contract.py` passes, and each
fault it knows how to plant makes it fail.

    WANDER_INTERPRETER=/path/to/micropython python -m unittest tests.test_wander

The contract needs an interpreter with LVGL and svgio: MicroPython's unix
port built with both, named in ``WANDER_INTERPRETER``. Without one the tests
skip, unless ``WANDER_REQUIRE=1`` says they must run.
"""

import os
import subprocess
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
INTERPRETER = os.getenv("WANDER_INTERPRETER")
PLANTS = ("no_paint", "hidden", "same_colours", "no_walk", "deaf", "hoard", "leak")


def _run(plant=None):
    env = dict(os.environ)
    env.pop("WANDER_PLANT", None)
    if plant:
        env["WANDER_PLANT"] = plant
    return subprocess.run(
        [INTERPRETER, "-X", "heapsize=24M", os.path.join(TESTS, "wander_contract.py")],
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )


class WanderTest(unittest.TestCase):
    def setUp(self):
        if not INTERPRETER:
            if os.getenv("WANDER_REQUIRE") == "1":
                self.fail("WANDER_INTERPRETER names no interpreter")
            self.skipTest("WANDER_INTERPRETER names no interpreter with LVGL and svgio")

    def test_the_contract_passes(self):
        done = _run()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("ok", done.stdout)

    def test_every_plant_fails_it(self):
        for plant in PLANTS:
            with self.subTest(plant=plant):
                done = _run(plant)
                self.assertNotEqual(done.returncode, 0, "the contract passed with %s planted" % plant)
                self.assertIn("FAILED:", done.stdout, done.stdout + done.stderr)
