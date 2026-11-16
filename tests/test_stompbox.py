# SPDX-FileCopyrightText: 2026 PyDevices
#
# SPDX-License-Identifier: MIT
"""Stompbox's level meter and clip light (``stompbox_check.py``) on CPython
and unix MicroPython, then once per planted fault.

    python -m unittest tests.test_stompbox

The interpreters are found as ``test_engine.py`` finds them, and both need
audiodsp. A missing MicroPython is skipped, loudly.
"""

import os
import subprocess
import sys
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
ROOT = str(TESTS.parent)
CHECK = str(TESTS / "stompbox_check.py")
sys.path.insert(0, str(TESTS))

from test_engine import _find  # noqa: E402

PLANTS = ("noclip", "nomaster", "sparse", "mono")


class StompboxMeterTest(unittest.TestCase):
    def _run(self, kind, plant=None):
        env = dict(os.environ)
        if kind == "cpython":
            env["PYTHONPATH"] = os.pathsep.join([ROOT, env.get("PYTHONPATH", "")])
            cmd = [sys.executable, CHECK]
        else:
            exe = _find("OMNIPYTHON_MICROPYTHON", "micropython")
            if exe is None:
                message = "no micropython: Stompbox's meter check did NOT run on it"
                sys.stderr.write("\n*** %s ***\n" % message)
                self.skipTest(message)
            env["MICROPYPATH"] = ":".join([ROOT, ".frozen"])
            cmd = [exe, "-X", "heapsize=64M", CHECK]
        if plant:
            cmd += ["--plant", plant]
        with self.subTest(plant=plant):
            r = subprocess.run(cmd, env=env, cwd=self.tmp, capture_output=True, text=True, timeout=300)
            out = r.stdout + r.stderr
            if plant is None:
                self.assertEqual(r.returncode, 0, out)
                self.assertIn("all passed", r.stdout, out)
            else:
                self.assertNotEqual(r.returncode, 0, out)
                self.assertIn("(plant: %s)" % plant, r.stdout, out)

    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_meter_cpython(self):
        self._run("cpython")

    def test_meter_micropython(self):
        self._run("micropython")

    def test_plants_cpython(self):
        for plant in PLANTS:
            self._run("cpython", plant)

    def test_plants_micropython(self):
        for plant in PLANTS:
            self._run("micropython", plant)


if __name__ == "__main__":
    unittest.main()
