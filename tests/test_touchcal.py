# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The Touch app: what it finds wrong with a touch mapping, from five taps.

    python -m unittest tests.test_touchcal

The analysis is checked here against touch controllers that read the targets
through known transforms. The app itself runs in `touchcal_contract.py`, in a
fresh interpreter with LVGL for CPython, tapped through a stand-in touch
device at three screen sizes; without LVGL that part skips, unless
``TOUCHCAL_REQUIRE=1`` says it must run.
"""

import importlib.util
import os
import subprocess
import sys
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TESTS)

# The analysis on its own: the package's __init__ needs LVGL.
_spec = importlib.util.spec_from_file_location("touchcal_fit", os.path.join(ROOT, "apps", "touchcal", "fit.py"))
fit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fit)

SWAP_XY, REVERSE_X, REVERSE_Y = fit.SWAP_XY, fit.REVERSE_X, fit.REVERSE_Y


def _targets(w, h):
    mx, my = w // 10, h // 10
    return [(mx, my), (w - 1 - mx, my), (w - 1 - mx, h - 1 - my), (mx, h - 1 - my), (w // 2, h // 2)]


def _taps(w, h, controller, mask):
    """Taps on each target, read by ``controller(x, y)`` and mapped through ``mask``."""
    out = []
    for t in _targets(w, h):
        raw = controller(*t)
        out.append({"target": t, "raw": raw, "mapped": fit.apply_mask(raw, mask, w, h)})
    return out


class AnalyseTest(unittest.TestCase):
    W, H = 480, 320

    def analyse(self, controller, mask, rotation=0, table=(0, 0, 0, 0)):
        return fit.analyse(_taps(self.W, self.H, controller, mask), self.W, self.H, mask, rotation, table)

    def test_identity_is_right(self):
        a = self.analyse(lambda x, y: (x, y), 0)
        self.assertTrue(a["ok"])
        self.assertEqual(a["worst"], 0)
        self.assertEqual(a["fix"]["mask"], 0)
        self.assertIsNone(a["fix"]["calibration"])
        self.assertIn("Every tap landed on its target", a["words"][0])

    def test_mirror_x(self):
        a = self.analyse(lambda x, y: (self.W - 1 - x, y), 0)
        self.assertFalse(a["ok"])
        self.assertEqual(a["seen"]["mask"], REVERSE_X)
        self.assertEqual(a["fix"]["mask"], REVERSE_X)
        self.assertEqual(a["fix"]["table"], [REVERSE_X, 0, 0, 0])
        self.assertIsNone(a["fix"]["calibration"])
        self.assertTrue(a["words"][0].startswith("Left and right are swapped"))
        self.assertIn("should be REVERSE_X, not 0", a["words"][-1])

    def test_mirror_y(self):
        a = self.analyse(lambda x, y: (x, self.H - 1 - y), 0)
        self.assertEqual(a["seen"]["mask"], REVERSE_Y)
        self.assertEqual(a["fix"]["mask"], REVERSE_Y)

    def test_swap(self):
        a = self.analyse(lambda x, y: (y, x), 0)
        self.assertFalse(a["ok"])
        self.assertEqual(a["fix"]["mask"], SWAP_XY)
        self.assertIn("x and y are swapped", a["words"][0])

    def test_swap_already_in_the_table_is_right(self):
        a = self.analyse(lambda x, y: (y, x), SWAP_XY)
        self.assertTrue(a["ok"])
        self.assertEqual(a["fix"]["mask"], SWAP_XY)

    def test_a_turn_names_the_entry_for_the_rotation_in_use(self):
        # The controller is a quarter turn round from the screen at rotation 90.
        controller = lambda x, y: (y, self.W - 1 - x)
        good = fit.fit([controller(*t) for t in _targets(self.W, self.H)], _targets(self.W, self.H))["mask"]
        a = self.analyse(controller, 0, rotation=90, table=(0, 0, 0, 0))
        self.assertIn("turned 90 degrees", a["words"][0])
        self.assertEqual(a["fix"]["mask"], good)
        self.assertEqual(a["fix"]["table"], [0, good, 0, 0])
        taps = _taps(self.W, self.H, controller, good)
        self.assertTrue(fit.analyse(taps, self.W, self.H, good, 90)["ok"])

    def test_half_turn(self):
        a = self.analyse(lambda x, y: (self.W - 1 - x, self.H - 1 - y), 0)
        self.assertIn("180 degrees", a["words"][0])
        self.assertEqual(a["fix"]["mask"], REVERSE_X | REVERSE_Y)

    def test_a_scale_error_gives_the_calibration(self):
        # x covers only 60% of the width: the calibration's range is too wide.
        a = self.analyse(lambda x, y: (round(x * 0.6), y), 0)
        self.assertFalse(a["ok"])
        self.assertTrue(any("60% of the screen's width" in w for w in a["words"]), a["words"])
        cal = a["fix"]["calibration"]
        self.assertEqual(set(cal), {"x"})
        self.assertEqual(cal["x"]["raw_axis"], "x")
        self.assertEqual(cal["x"]["should"], (0, self.W - 1))
        lo, hi = cal["x"]["reads"]
        self.assertLessEqual(abs(lo - 0), 1)
        self.assertLessEqual(abs(hi - round((self.W - 1) * 0.6)), 1)

    def test_an_offset(self):
        a = self.analyse(lambda x, y: (x, y + 40), 0)
        self.assertTrue(any("40 px too far down" in w for w in a["words"]), a["words"])
        self.assertEqual(a["fix"]["mask"], 0)
        self.assertEqual(a["fix"]["calibration"]["y"]["reads"], (40, self.H - 1 + 40))

    def test_calibration_of_a_swapped_and_reversed_axis(self):
        # A GT911 that reports 800 wide on a 480-wide axis, swapped and reversed.
        w, h = 480, 800
        controller = lambda x, y: (y, round((w - 1 - x) * 800 / 480))
        taps = _taps(w, h, controller, 0)
        a = fit.analyse(taps, w, h, 0, 0, (0, 0, 0, 0))
        self.assertEqual(a["fix"]["mask"], SWAP_XY | REVERSE_X)
        cal = a["fix"]["calibration"]
        self.assertEqual(cal["x"]["raw_axis"], "y")
        self.assertEqual(cal["x"]["should"], (w - 1, 0))
        self.assertEqual(cal["x"]["reads"], (798, 0))

    def test_without_raw_points_it_still_says_what_it_sees(self):
        taps = _taps(self.W, self.H, lambda x, y: (self.W - 1 - x, y), 0)
        for t in taps:
            t["raw"] = None
        a = fit.analyse(taps, self.W, self.H)
        self.assertIsNone(a["fix"])
        self.assertTrue(a["words"][0].startswith("Left and right"))

    def test_taps_that_all_read_the_same(self):
        a = self.analyse(lambda x, y: (100, 100), 0)
        self.assertFalse(a["ok"])
        self.assertIsNone(a["seen"])
        self.assertIn("isn't reporting", a["words"][-1])


class ScreenTest(unittest.TestCase):
    def test_five_targets_one_at_a_time(self):
        required = os.getenv("TOUCHCAL_REQUIRE") == "1"
        try:
            import lvgl  # noqa: F401
        except ImportError:
            if required:
                raise
            self.skipTest("LVGL for CPython isn't installed")
        # The smallest screen the app is for, a common SPI panel and the bench's 800 x 480.
        for screen in ("240x320", "480x320", "800x480"):
            with self.subTest(screen=screen):
                env = dict(os.environ, TOUCHCAL_SCREEN=screen)
                r = subprocess.run(
                    [sys.executable, os.path.join(TESTS, "touchcal_contract.py")],
                    capture_output=True, text=True, timeout=120, env=env,
                )
                if r.returncode == 2 and not required:
                    self.skipTest(r.stdout.strip())
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
