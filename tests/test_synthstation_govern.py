# SPDX-FileCopyrightText: 2026 PyDevices
#
# SPDX-License-Identifier: MIT
"""Synth Station's voice cap, read for read, from what a DEV-KIT measured.

    python -m unittest tests.test_synthstation_govern
"""

import os
import sys
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "apps"))
BLOCK_US = 2666
IDLE_US = 1005


def _govern():
    with mock.patch.dict(sys.modules, {"lvgl": types.ModuleType("lvgl")}):
        from synthstation.station import Station
    return Station._govern


class _Rig:
    """Enough of a Station and its instrument for ``_govern`` to run on."""

    def __init__(self, voices, most=16):
        self.pool = types.SimpleNamespace(sounding=lambda: self.sounding)
        self.sounding = 0
        self.inst = types.SimpleNamespace(voices=voices, voice_pool=self.pool)
        self.station = types.SimpleNamespace(
            output=types.SimpleNamespace(pull_us=lambda: self.cost, block_us=lambda: BLOCK_US),
            _most_voices=most,
            _settle=0,
            _idle_us=IDLE_US,
            _played=0,
            _fitted=0,
            _raised=False,
            _read=None,
            _refused=None,
        )
        self.govern = _govern()

    def read(self, sounding, cost):
        """One governor pass, then the settling passes it asked for."""
        self.sounding = sounding
        self.cost = cost
        self.govern(self.station, self.inst)
        while self.station._settle:
            self.govern(self.station, self.inst)
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


if __name__ == "__main__":
    unittest.main()
