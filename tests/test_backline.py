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

The floor and desk views' checks need LVGL, svgio and icons (on CPython,
omnipython-lvgl, omnipython-desktop, resvg-py and Pillow), and skip without
them; the desk's also needs audiodsp. The browser desk page's module must
match its source (``tools/backline/desk_page.py --check``).
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
DESK = str(TESTS / "backline_desk_contract.py")
CAST = str(TESTS / "backline_cast_contract.py")
ASK = str(TESTS / "backline_ask_contract.py")
MEMORY = str(TESTS / "backline_memory_contract.py")
PAGE = str(TESTS.parent / "tools" / "backline" / "desk_page.py")
sys.path.insert(0, str(TESTS))

from test_engine import _find, audio_checkout  # noqa: E402

PLANTS = ("no-hold", "no-double", "switch-now", "no-return", "no-wrap", "outro-forever", "fill-ignores-main",
          "late-notes", "drop-pad", "no-choke", "deaf-panel", "song-without-outro", "four-steps", "deaf-mix",
          "form-out-of-order", "tap-sticks", "edit-resets-form", "edit-not-heard", "learn-on-release",
          "cc-no-release", "pc-as-pedal", "any-channel", "tempo-no-reset", "deaf-pedals", "no-repeat", "no-ramp",
          "ramp-jumps", "fill-moves-form", "migrate-forgets", "switch-bounces", "switch-inverted",
          "switch-swapped")
NEEDS_AUDIO = ("drop-pad", "no-choke", "deaf-panel", "edit-resets-form", "edit-not-heard", "deaf-pedals")
FLOOR_PLANTS = ("no-beat", "full-redraw", "deaf-lamp", "overflow", "stale-part", "dark-lamp", "four-beats", "truncate",
                "dead-switch", "no-pulse", "mute-bar", "bar-while-stopped", "no-fallback", "screen-font", "wide-tempo")
DESK_PLANTS = ("overflow", "wide-grid", "deaf-cell", "stale-grid", "still-strip", "all-rows", "deaf-fader",
               "long-names", "tight-mixer", "no-joiners", "deaf-learn", "stale-pedals", "deaf-ask", "blind-preview",
               "wide-sheet", "deaf-silence")
ASK_PLANTS = ("no-retry", "lax", "no-fallback", "no-borrow", "copy-told", "grid-shift", "lost-plan", "quiet-failure",
              "keep-nowhere", "whole-reply", "old-song-shown", "ble-refused", "lower-style", "form-bars")
ASK_NEEDS_BOX = ("quiet-failure", "keep-nowhere", "old-song-shown")
CAST_PLANTS = ("no-show", "steal-default", "deaf-desk", "flood", "lost-kind", "no-close")
MEMORY_PLANTS = ("keep-floor", "keep-face", "alpha-panel", "whole-panel", "all-digits", "stale-return")
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


class AskForAGroove(unittest.TestCase):
    """``backline_ask_contract.py`` against its stand-in server on each
    interpreter, then once per planted fault."""

    def _ask(self, kind, *extra):
        cmd, env = _cmd(kind, ASK)
        if cmd is None:
            message = "no %s: the ask contract did NOT run on it" % kind
            sys.stderr.write("\n*** " + message + " ***\n")
            self.skipTest(message)
        return _run(cmd, env, *extra)

    def _clean(self, kind):
        result = self._ask(kind)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(" 0 failed", result.stdout)
        if REQUIRE:
            self.assertNotIn("\nskip ", "\n" + result.stdout, result.stdout)
        return result

    def test_cpython(self):
        self._clean("cpython")

    def test_micropython(self):
        self.assertIn("on micropython", self._clean("micropython").stdout)

    def test_plants(self):
        clean = self._ask("cpython").stdout
        for plant in ASK_PLANTS:
            with self.subTest(plant=plant):
                if plant in ASK_NEEDS_BOX and "\nskip " in "\n" + clean:
                    continue
                result = self._ask("cpython", "--plant=" + plant)
                self.assertIn("PLANTED " + plant, result.stdout, result.stdout + result.stderr)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("FAIL ", result.stdout, result.stdout + result.stderr)


def _cpython_lacks():
    """Why the floor view can't be drawn on this Python, or None."""
    for name in ("lvgl", "svgio", "icons"):
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
        said = result.stdout + result.stderr
        if any("no module named '%s'" % m in said for m in ("lvgl", "svgio", "icons")):
            if REQUIRE:
                self.fail("this micropython has no LVGL, svgio or icons")
            self.skipTest("this micropython has no LVGL, svgio or icons")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(" 0 failed", result.stdout)

    def test_floor_plants(self):
        cmd, env = _cmd("cpython", FLOOR)
        for plant in FLOOR_PLANTS:
            with self.subTest(plant=plant):
                result = _run(cmd, env, "--plant=" + plant)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("FAIL ", result.stdout, result.stdout + result.stderr)


class DeskView(unittest.TestCase):
    """Two desks on one box at 800x480 and 1280x720, one local and one over
    TCP, staying in step through edits while the song plays; each desk plant
    must fail it."""

    def setUp(self):
        why = _cpython_lacks()
        if why is None:
            try:
                import audiocore  # noqa: F401
            except ImportError as e:
                why = "audiocore: %s" % e
        if why:
            if REQUIRE:
                self.fail("the desk view needs LVGL, svgio, icons and audiodsp: " + why)
            self.skipTest("no LVGL, svgio, icons or audiodsp here: " + why)

    def test_desk(self):
        cmd, env = _cmd("cpython", DESK)
        result = _run(cmd, env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(" 0 failed", result.stdout)

    def test_desk_plants(self):
        cmd, env = _cmd("cpython", DESK)
        for plant in DESK_PLANTS:
            with self.subTest(plant=plant):
                result = _run(cmd, env, "--plant=" + plant)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("FAIL ", result.stdout, result.stdout + result.stderr)

    def test_cast(self):
        """The desk at 1280x720 on a display of its own, its frames handed
        to a stand-in for a cast while the song plays."""
        cmd, env = _cmd("cpython", CAST)
        result = _run(cmd, env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(" 0 failed", result.stdout)

    def test_cast_plants(self):
        cmd, env = _cmd("cpython", CAST)
        for plant in CAST_PLANTS:
            with self.subTest(plant=plant):
                result = _run(cmd, env, "--plant=" + plant)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("FAIL ", result.stdout, result.stdout + result.stderr)


class ViewMemory(unittest.TestCase):
    """What the floor and desk views hold on a box's own screen at 800x480
    and 720x720, going back and forth; on MicroPython, the heap they take
    too. Each memory plant must fail it."""

    def setUp(self):
        DeskView.setUp(self)

    def test_memory(self):
        cmd, env = _cmd("cpython", MEMORY)
        result = _run(cmd, env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(" 0 failed", result.stdout)

    def test_memory_micropython(self):
        cmd, env = _cmd("micropython", MEMORY)
        if cmd is None:
            self.skipTest("no micropython")
        result = _run(cmd, env)
        said = result.stdout + result.stderr
        if any("no module named '%s'" % m in said for m in ("lvgl", "svgio", "icons", "audiocore")):
            if REQUIRE:
                self.fail("this micropython has no LVGL, svgio, icons or audiodsp")
            self.skipTest("this micropython has no LVGL, svgio, icons or audiodsp")
        self.assertEqual(result.returncode, 0, said)
        self.assertIn(" 0 failed", result.stdout)
        self.assertNotIn("\nskip ", "\n" + result.stdout, result.stdout)

    def test_memory_plants(self):
        cmd, env = _cmd("cpython", MEMORY)
        for plant in MEMORY_PLANTS:
            with self.subTest(plant=plant):
                result = _run(cmd, env, "--plant=" + plant)
                self.assertIn("PLANTED " + plant, result.stdout, result.stdout + result.stderr)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("FAIL ", result.stdout, result.stdout + result.stderr)


class DeskPage(unittest.TestCase):
    def test_page_module_is_current(self):
        result = subprocess.run([sys.executable, PAGE, "--check"], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
