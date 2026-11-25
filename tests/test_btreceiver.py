# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Run btreceiver_contract.py on CPython and on unix MicroPython.

Bluetooth Receiver's screen on a display with no window, against the app's
demo phone: pairing, connected, playing, paused and a track with no cover,
with its buttons and volume slider driven by touch. Then btreceiver_layout.py:
the screen at every display size, everything inside it.

Each half needs LVGL, svgio, jpegio and multimer. A half whose interpreter
lacks them skips, loudly; ``BTRECEIVER_REQUIRE=1`` makes that a failure.

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
CONTRACT = TESTS / "btreceiver_contract.py"
LAYOUT = TESTS / "btreceiver_layout.py"


def _can_run(interpreter):
    """Whether *interpreter* has what the app's screen needs."""
    try:
        cmd = [interpreter, "-c", "import lvgl, svgio, jpegio, multimer"]
        return subprocess.run(cmd, capture_output=True, timeout=60, env=_env()).returncode == 0
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
        if _can_run(candidate):
            return candidate
    return None


def _env():
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(LIB), str(TESTS), env.get("PYTHONPATH", "")])
    env["MICROPYPATH"] = ":".join([str(LIB), str(TESTS), ".frozen"])
    return env


def _run(interpreter, script, *args):
    env = _env()
    return subprocess.run(
        [interpreter, str(script)] + list(args),
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
            message = ("no interpreter with lvgl, svgio, jpegio and multimer for this half: "
                       "the Bluetooth Receiver checks did NOT run here")
            if os.environ.get("BTRECEIVER_REQUIRE") == "1":
                self.fail(message)
            sys.stderr.write("\n*** " + message + " ***\n")
            self.skipTest(message)

    def contract(self, script=CONTRACT):
        result = _run(self.interpreter, script)
        return result, result.stdout + result.stderr

    def test_the_screen_follows_the_phone(self):
        result, out = self.contract()
        self.assertEqual(result.returncode, 0, out)
        self.assertIn("ALL PASSED", out)

    def test_the_screen_fits_every_display(self):
        result, out = self.contract(LAYOUT)
        self.assertEqual(result.returncode, 0, out)
        self.assertIn("ALL PASSED", out)


class CPythonReceiver(_Contract, unittest.TestCase):
    interpreter = sys.executable if _can_run(sys.executable) else None


class MicroPythonReceiver(_Contract, unittest.TestCase):
    interpreter = _micropython()
