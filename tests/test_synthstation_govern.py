# SPDX-FileCopyrightText: 2026 PyDevices
#
# SPDX-License-Identifier: MIT
"""Synth Station's voice cap, read for read, from what a DEV-KIT measured.

Then the cap shared by several instruments against a stand-in load
(``synthstation_shared_cap_check.py``), and the readings it works from on a
board that plays through ``audio_out`` (``synthstation_output_check.py``),
each on CPython and unix MicroPython.

    python -m unittest tests.test_synthstation_govern
"""

import os
import subprocess
import sys
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "apps"))
BLOCK_US = 2666
IDLE_US = 1005


def _station():
    with mock.patch.dict(sys.modules, {"lvgl": types.ModuleType("lvgl")}):
        from synthstation.station import Station
    return Station


class _Rig:
    """Enough of a Station and its one instrument for ``_govern`` to run on."""

    def __init__(self, voices, most=16):
        self.pool = types.SimpleNamespace(sounding=lambda: self.sounding)
        self.sounding = 0
        self.inst = types.SimpleNamespace(voices=voices, voice_pool=self.pool)
        part = types.SimpleNamespace(adapter=types.SimpleNamespace(instrument=self.inst), most=most)
        station = _station()
        self.station = station.__new__(station)
        self.station.__dict__.update(
            output=types.SimpleNamespace(pull_us=lambda: self.cost, block_us=lambda: BLOCK_US),
            _playing=(part,),
            _settle=0,
            _cap=None,
            _idle_us=IDLE_US,
            _played=0,
            _fitted=0,
            _raised=False,
            _read=None,
            _refused=None,
        )

    def read(self, sounding, cost):
        """One governor pass, then the settling passes it asked for."""
        self.sounding = sounding
        self.cost = cost
        self.station._govern()
        while self.station._settle:
            self.station._govern()
        return self.inst.voices


class VoiceCapTest(unittest.TestCase):
    def test_a_raised_cap_stays_up_over_the_chord_that_cant_use_it(self):
        # tonewheel3 holding two keys: its cost wanders between these reads.
        rig = _Rig(voices=2)
        self.assertEqual(rig.read(2, 1770), 3)
        self.assertEqual(rig.read(2, 2118), 3)
        self.assertEqual(rig.read(2, 1770), 3)

    def test_a_raised_cap_comes_down_when_the_blocks_go_over_budget(self):
        rig = _Rig(voices=2)
        self.assertEqual(rig.read(2, 1770), 3)
        self.assertEqual(rig.read(3, 2800), 2)

    def test_a_count_that_went_over_budget_waits_for_the_keys_to_come_up(self):
        # Ten keys down: three voices read over, two read well under, and each
        # try at three steals a note.
        rig = _Rig(voices=2)
        self.assertEqual(rig.read(2, 1800), 3)
        self.assertEqual(rig.read(3, 2700), 2)
        for _ in range(4):
            self.assertEqual(rig.read(2, 1800), 2)
        rig.read(0, IDLE_US)
        self.assertEqual(rig.read(2, 1800), 3)

    def test_the_first_voice_still_sets_the_cap_before_a_chord(self):
        rig = _Rig(voices=16)
        self.assertEqual(rig.read(1, 1292), 4)


class _OnEachInterpreter:
    """A check script run on CPython and on unix MicroPython."""

    check = None

    def _run(self, cmd, env):
        check = os.path.join(ROOT, "tests", self.check)
        r = subprocess.run(cmd + [check], env=env, capture_output=True, text=True, timeout=120)
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        self.assertIn("RESULT OK", r.stdout, out)

    def test_cpython(self):
        env = dict(os.environ)
        env["PYTHONPATH"] = os.path.join(ROOT, "apps")
        self._run([sys.executable], env)

    def test_micropython(self):
        sys.path.insert(0, os.path.join(ROOT, "tests"))
        from test_engine import _find

        exe = _find("OMNIPYTHON_MICROPYTHON", "micropython")
        if exe is None:
            message = "no micropython: %s did NOT run on it" % self.check
            sys.stderr.write("\n*** %s ***\n" % message)
            self.skipTest(message)
        env = dict(os.environ)
        env["MICROPYPATH"] = os.path.join(ROOT, "apps")
        self._run([exe], env)


class AudioOutReadingsTest(_OnEachInterpreter, unittest.TestCase):
    """The cost and underrun readings through ``audio_out``."""

    check = "synthstation_output_check.py"


class SharedCapTest(_OnEachInterpreter, unittest.TestCase):
    """One cap for every instrument playing, against a stand-in load."""

    check = "synthstation_shared_cap_check.py"


if __name__ == "__main__":
    unittest.main()
