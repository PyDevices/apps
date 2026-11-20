# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Run controls_contract.py on CPython and on unix MicroPython.

The slider, the LED meter, the lamp button, the pad grid, the encoder's
three ring modes, the envelope view and the routing diagram, built on a
display with no window and driven by hand and by a host. The planted run
stops a slider from reporting its changes, makes an envelope ignore its
rates and flattens a routing diagram, and must fail the checks for each.

MicroPython comes from ``OMNIPYTHON_MICROPYTHON``, ``micropython`` on PATH, or
a ``bin/micropython`` in a folder above this one, and needs LVGL. With none,
its half is skipped loudly; ``OMNIPYTHON_REQUIRE_MICROPYTHON=1`` makes that a
failure.
"""

from pathlib import Path
import os
import shutil
import subprocess
import sys
import unittest

TESTS = Path(__file__).resolve().parent
LIB = TESTS.parent / "lib"
CONTRACT = TESTS / "controls_contract.py"
# The 32 six-operator algorithms the routing diagram is checked against.
EXAMPLES = LIB / "controlkit" / "examples"


def _has_lvgl(interpreter):
    try:
        return subprocess.run([interpreter, "-c", "import lvgl"], capture_output=True, timeout=60).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _micropython():
    """The first MicroPython that can import lvgl, or None."""
    candidates = []
    explicit = os.environ.get("OMNIPYTHON_MICROPYTHON")
    if explicit:
        candidates.append(explicit)
    found = shutil.which("micropython")
    if found:
        candidates.append(found)
    for parent in TESTS.parents:
        candidate = parent / "bin" / "micropython"
        if candidate.is_file() and os.access(str(candidate), os.X_OK):
            candidates.append(str(candidate))
    for candidate in candidates:
        if _has_lvgl(candidate):
            return candidate
    return None


def _run(interpreter, *args):
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(LIB), str(TESTS), str(EXAMPLES), env.get("PYTHONPATH", "")])
    env["MICROPYPATH"] = ":".join([str(LIB), str(TESTS), str(EXAMPLES), ".frozen"])
    return subprocess.run(
        [interpreter, str(CONTRACT)] + list(args),
        cwd=str(TESTS),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )


class _Contract:
    interpreter = None

    def setUp(self):
        if self.interpreter is None:
            message = "no interpreter with lvgl for this half: the controls checks did NOT run here"
            if os.environ.get("OMNIPYTHON_REQUIRE_MICROPYTHON") == "1":
                self.fail(message)
            sys.stderr.write("\n*** " + message + " ***\n")
            self.skipTest(message)

    def contract(self, *args):
        result = _run(self.interpreter, *args)
        return result, result.stdout + result.stderr

    def test_the_controls_hold_their_contract(self):
        result, out = self.contract()
        self.assertEqual(result.returncode, 0, out)
        self.assertIn("ALL PASSED", out)

    def test_a_silent_slider_fails_the_callback_checks(self):
        result, out = self.contract("--plant")
        self.assertEqual(result.returncode, 1, out)
        self.assertIn("FAIL a drag reports its change once", out)
        failed = [line for line in out.splitlines() if line.startswith("FAIL ")]
        self.assertTrue(failed, out)

    def test_an_envelope_that_ignores_its_rates_fails(self):
        result, out = self.contract("--plant")
        self.assertEqual(result.returncode, 1, out)
        self.assertIn("FAIL a faster rate draws a shorter segment", out)

    def test_a_flat_routing_diagram_fails_the_row_checks(self):
        result, out = self.contract("--plant")
        self.assertEqual(result.returncode, 1, out)
        self.assertIn("FAIL carriers take the bottom row and each modulator the row above its target", out)
        self.assertIn("FAIL a node that modulates several sits over the middle of them", out)


class CPythonControls(_Contract, unittest.TestCase):
    interpreter = sys.executable if _has_lvgl(sys.executable) else None


class MicroPythonControls(_Contract, unittest.TestCase):
    interpreter = _micropython()
