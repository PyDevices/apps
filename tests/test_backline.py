# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""``backline_contract.py`` on CPython and unix MicroPython, then once per
planted fault, and the floor view on a display with no window.

    python -m unittest tests.test_backline

The interpreters: this Python, and ``$OMNIPYTHON_MICROPYTHON``, else
``micropython`` on the PATH, else ``bin/`` in a folder above this checkout;
one that isn't there is skipped, loudly. audioinstruments' ``lib``
(``$AUDIOINSTRUMENTS_DIR``, else a checkout beside this one) and hmilink
(``$HMILINK_PATH``, else an omnipython checkout beside this one) go on each
interpreter's path. The kit checks need audiodsp installed or built in;
without it they skip, and so do the plants only they catch.
``BACKLINE_REQUIRE=1`` makes a skipped kit or panel check a failure; the
SoundFont kit still skips without a bank, since none ships with the tests.

The floor view's check needs LVGL and svgio (on CPython, omnipython-lvgl,
omnipython-desktop, resvg-py and Pillow), and skips without them.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
CONTRACT = str(TESTS / "backline_contract.py")
FLOOR = str(TESTS / "backline_floor_contract.py")
sys.path.insert(0, str(TESTS))

from test_engine import _find, audio_checkout  # noqa: E402

PLANTS = ("no-hold", "no-double", "switch-now", "no-return", "no-wrap", "outro-forever", "fill-ignores-main",
          "late-notes", "drop-pad", "no-choke", "deaf-panel", "song-without-outro")
NEEDS_AUDIO = ("drop-pad", "no-choke", "deaf-panel")
FLOOR_PLANTS = ("no-beat", "full-redraw", "deaf-lamp", "overflow", "stale-part", "dark-lamp")
REQUIRE = os.environ.get("BACKLINE_REQUIRE") == "1"


def hmilink_path():
    explicit = os.environ.get("HMILINK_PATH")
    if explicit:
        return explicit
    for parent in TESTS.parents:
        candidate = parent / "omnipython" / "packages" / "hmilink"
        if (candidate / "hmilink").is_dir():
            return str(candidate)
    return None


def paths():
    found = []
    ai = audio_checkout("audioinstruments")
    if ai:
        found.append(os.path.join(ai, "lib"))
    hm = hmilink_path()
    if hm:
        found.append(hm)
    return found


def _cmd(kind, script=CONTRACT):
    if kind == "cpython":
        env = dict(os.environ)
        extra = paths() + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
        env["PYTHONPATH"] = os.pathsep.join(extra)
        return [sys.executable, script], env
    exe = _find("OMNIPYTHON_MICROPYTHON", "micropython")
    if exe is None:
        return None, None
    env = dict(os.environ)
    env["MICROPYPATH"] = ":".join([".frozen"] + paths())
    return [exe, "-X", "heapsize=64M", script], env


def _run(cmd, env, *args):
    with tempfile.TemporaryDirectory() as tmp:
        return subprocess.run(cmd + list(args) + ["--tmp", tmp], env=env, capture_output=True, text=True,
                              timeout=300)


class Contract(unittest.TestCase):
    def _contract(self, kind):
        cmd, env = _cmd(kind)
        if cmd is None:
            message = "no %s: the contract did NOT run on it" % kind
            sys.stderr.write("\n*** " + message + " ***\n")
            self.skipTest(message)
        result = _run(cmd, env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(" 0 failed", result.stdout)
        if REQUIRE:
            skipped = [line for line in result.stdout.splitlines()
                       if line.startswith("skip ") and not line.startswith("skip the SoundFont kit")]
            self.assertEqual(skipped, [], result.stdout)
        return result

    def test_cpython(self):
        self._contract("cpython")

    def test_micropython(self):
        self.assertIn("on micropython", self._contract("micropython").stdout)


class PlantedFaults(unittest.TestCase):
    """A check that can't fail proves nothing: each plant must fail its check."""

    def _plants(self, kind):
        cmd, env = _cmd(kind)
        if cmd is None:
            self.skipTest("no %s" % kind)
        clean = _run(cmd, env).stdout
        for plant in PLANTS:
            with self.subTest(plant=plant):
                if plant in NEEDS_AUDIO and "\nskip " in "\n" + clean:
                    continue
                result = _run(cmd, env, "--plant=" + plant)
                self.assertIn("PLANTED " + plant, result.stdout, result.stdout + result.stderr)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("FAIL ", result.stdout, result.stdout + result.stderr)

    def test_cpython(self):
        self._plants("cpython")

    def test_micropython(self):
        self._plants("micropython")


def _cpython_lacks():
    """Why the floor view can't be drawn on this Python, or None."""
    for name in ("lvgl", "svgio"):
        try:
            __import__(name)
        except ImportError as e:
            return "%s: %s" % (name, e)
    return None


class FloorView(unittest.TestCase):
    """The floor view drawn at three sizes, beats lighting the ring; each
    floor plant must fail it."""

    def setUp(self):
        why = _cpython_lacks()
        if why:
            if REQUIRE:
                self.fail("the floor view needs LVGL and svgio: " + why)
            self.skipTest("no LVGL and svgio here: " + why)

    def test_floor(self):
        cmd, env = _cmd("cpython", FLOOR)
        result = _run(cmd, env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(" 0 failed", result.stdout)

    def test_floor_micropython(self):
        cmd, env = _cmd("micropython", FLOOR)
        if cmd is None:
            self.skipTest("no micropython")
        result = _run(cmd, env)
        if "no module named 'lvgl'" in result.stdout + result.stderr or \
                "no module named 'svgio'" in result.stdout + result.stderr:
            if REQUIRE:
                self.fail("this micropython has no LVGL or svgio")
            self.skipTest("this micropython has no LVGL or svgio")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(" 0 failed", result.stdout)

    def test_floor_plants(self):
        cmd, env = _cmd("cpython", FLOOR)
        for plant in FLOOR_PLANTS:
            with self.subTest(plant=plant):
                result = _run(cmd, env, "--plant=" + plant)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("FAIL ", result.stdout, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
