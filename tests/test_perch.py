# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Perch on a display with no window: `perch_contract.py` passes, and each
fault it knows how to plant makes it fail.

    PERCH_INTERPRETER=/path/to/micropython python -m unittest tests.test_perch

It runs twice. On MicroPython it needs the unix port built with LVGL and
svgio, named in ``PERCH_INTERPRETER``. On CPython it runs on the Python that
runs this file, which needs the desktop ``lvgl``, ``svgio`` (with resvg-py
and Pillow) and ``multimer``. A half whose interpreter is missing skips,
unless ``PERCH_REQUIRE=1`` says both must run.
"""

import os
import subprocess
import sys
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
INTERPRETER = os.getenv("PERCH_INTERPRETER")
PLANTS = ("no_paint", "hidden", "same_colours", "no_walk", "deaf", "hoard", "leak")


def _run(plant=None, script="perch_contract.py", heap="24M", cpython=False):
    env = dict(os.environ)
    env.pop("PERCH_PLANT", None)
    if plant:
        env["PERCH_PLANT"] = plant
    command = [sys.executable] if cpython else [INTERPRETER, "-X", "heapsize=" + heap]
    return subprocess.run(
        command + [os.path.join(TESTS, script)],
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


def _cpython_has():
    """Why the CPython half can't run here, or None: it needs LVGL, svgio and multimer."""
    for name in ("lvgl", "svgio", "multimer"):
        try:
            __import__(name)
        except ImportError as e:
            return "no %s for this Python: %s" % (name, e)
    return None


@unittest.skipIf(_cpython_has() and os.getenv("PERCH_REQUIRE") != "1", _cpython_has())
class PerchOnCPythonTest(unittest.TestCase):
    """The same contract on this Python, with the desktop LVGL and svgio."""

    def test_the_contract_passes(self):
        done = _run(cpython=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("ok", done.stdout)

    def test_every_plant_fails_it(self):
        for plant in PLANTS:
            with self.subTest(plant=plant):
                done = _run(plant, cpython=True)
                self.assertNotEqual(done.returncode, 0, "the contract passed with %s planted" % plant)
                self.assertIn("FAILED:", done.stdout, done.stdout + done.stderr)

    def test_drawings_are_the_same_as_records_and_as_text(self):
        done = _run(script="perch_drawings.py", cpython=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        if "nothing to compare" in done.stdout:
            self.skipTest("this Python's svgio doesn't read the compact form")
        done = _run("loose_number", script="perch_drawings.py", cpython=True)
        self.assertNotEqual(done.returncode, 0, "the drawings matched with numbers written loosely")
        self.assertIn("FAILED:", done.stdout, done.stdout + done.stderr)
