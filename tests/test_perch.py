# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Perch on a display with no window: `perch_contract.py` passes, and each
fault it knows how to plant makes it fail.

    PERCH_INTERPRETER=/path/to/micropython python -m unittest tests.test_perch

The contract needs an interpreter with LVGL and svgio: MicroPython's unix
port built with both, named in ``PERCH_INTERPRETER``. Without one the tests
skip, unless ``PERCH_REQUIRE=1`` says they must run.
"""

import os
import subprocess
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
INTERPRETER = os.getenv("PERCH_INTERPRETER")
PLANTS = ("no_paint", "hidden", "same_colours", "no_walk", "deaf", "hoard", "leak")


def _run(plant=None, script="perch_contract.py", heap="24M"):
    env = dict(os.environ)
    env.pop("PERCH_PLANT", None)
    if plant:
        env["PERCH_PLANT"] = plant
    return subprocess.run(
        [INTERPRETER, "-X", "heapsize=" + heap, os.path.join(TESTS, script)],
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )


class PerchTest(unittest.TestCase):
    def setUp(self):
        if not INTERPRETER:
            if os.getenv("PERCH_REQUIRE") == "1":
                self.fail("PERCH_INTERPRETER names no interpreter")
            self.skipTest("PERCH_INTERPRETER names no interpreter with LVGL and svgio")

    def test_the_contract_passes(self):
        done = _run()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("ok", done.stdout)

    def test_every_plant_fails_it(self):
        # "cramped" needs an svgio whose decoders take working memory
        roomy = subprocess.run(
            [INTERPRETER, "-c", "import svgio; print(hasattr(svgio.SvgDecoder(), 'memory'))"], capture_output=True, text=True, timeout=60
        ).stdout.strip()
        for plant in PLANTS + (("cramped",) if roomy == "True" else ()):
            with self.subTest(plant=plant):
                done = _run(plant)
                self.assertNotEqual(done.returncode, 0, "the contract passed with %s planted" % plant)
                self.assertIn("FAILED:", done.stdout, done.stdout + done.stderr)

    def test_drawings_are_the_same_as_records_and_as_text(self):
        done = _run(script="perch_drawings.py", heap="128M")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("ok", done.stdout)
        if "nothing to compare" in done.stdout:
            self.skipTest("this interpreter's svgio doesn't read the compact form")
        done = _run("loose_number", script="perch_drawings.py", heap="128M")
        self.assertNotEqual(done.returncode, 0, "the drawings matched with numbers written loosely")
        self.assertIn("FAILED:", done.stdout, done.stdout + done.stderr)
