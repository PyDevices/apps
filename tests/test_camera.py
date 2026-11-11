# SPDX-FileCopyrightText: 2026 PyDevices
#
# SPDX-License-Identifier: MIT
"""The camera program's decisions, which need no screen or board: how far the
240x240 layout is enlarged, which controls a board gets, which picture source
it uses, and what part of a small camera's frame a video takes.

    python -m unittest tests.test_camera
"""

import importlib.util
import os
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "programs", "camera", "apps", "eyecam")


def _load(name, *path):
    spec = importlib.util.spec_from_file_location("eyecam_" + name, os.path.join(PKG, *path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


layout = _load("layout", "layout.py")
controls = _load("controls", "controls.py")
sources = _load("sources", "hw", "sources.py")
crop = _load("crop", "hw", "crop.py")

KEYS = types.SimpleNamespace(
    K_m=1, K_ESCAPE=2, K_UP=3, K_DOWN=4, K_RETURN=5, K_KP_ENTER=6)


class ScaleTest(unittest.TestCase):
    def test_the_eye_is_not_scaled(self):
        self.assertEqual(layout.scale_for(240, 240), 1)

    def test_the_boards_panels(self):
        self.assertEqual(layout.scale_for(720, 720), 3)
        self.assertEqual(layout.scale_for(800, 480), 2)  # the short side decides
        self.assertEqual(layout.scale_for(1280, 800), 3)

    def test_a_panel_that_is_not_a_whole_multiple_rounds_down(self):
        self.assertEqual(layout.scale_for(479, 479), 1)
        self.assertEqual(layout.scale_for(719, 720), 2)

    def test_a_smaller_panel_is_not_shrunk(self):
        self.assertEqual(layout.scale_for(128, 160), 1)


class ControlsTest(unittest.TestCase):
    def test_the_eye_keeps_its_buttons_and_knob(self):
        hardware, touch = controls.devices_for([controls.KEYPAD, controls.ENCODER])
        self.assertTrue(hardware)
        self.assertFalse(touch)

    def test_a_touch_only_board_gets_the_tap_zones(self):
        self.assertEqual(controls.devices_for([controls.POINTER]), (False, True))

    def test_a_board_with_one_button_and_a_screen_gets_both(self):
        self.assertEqual(controls.devices_for([controls.POINTER, controls.KEYPAD]), (True, True))

    def test_a_board_with_no_input_still_gets_the_tap_zones(self):
        self.assertEqual(controls.devices_for([]), (False, True))

    def test_the_desktop_has_keys_and_a_mouse(self):
        self.assertEqual(controls.devices_for([], on_desktop=True), (True, True))

    def test_default_buttons_are_the_eyes(self):
        table = controls.button_table(KEYS, None)
        self.assertEqual(table[KEYS.K_m], "menu")
        self.assertEqual(table[KEYS.K_ESCAPE], "menu")
        self.assertEqual(table[KEYS.K_RETURN], "encoder")
        self.assertEqual(table[KEYS.K_KP_ENTER], "encoder")

    def test_a_board_names_its_own_buttons(self):
        board = types.SimpleNamespace(camera_buttons={"menu": 40, "up": (41, 42), "encoder": 43})
        table = controls.button_table(KEYS, board)
        self.assertEqual(table, {40: "menu", 41: "up", 42: "up", 43: "encoder"})

    def test_a_board_with_no_table_uses_the_default(self):
        self.assertEqual(controls.button_table(KEYS, types.SimpleNamespace()), controls.button_table(KEYS, None))

    def test_a_vertical_drag_is_a_swipe_and_a_tap_is_not(self):
        self.assertEqual(controls.swipe(2, -40), "up")
        self.assertEqual(controls.swipe(-3, 40), "down")
        self.assertIsNone(controls.swipe(0, 10))  # a tap that wobbled
        self.assertIsNone(controls.swipe(60, 40))  # mostly sideways

    def test_the_reach_scales_with_the_panel(self):
        self.assertIsNone(controls.swipe(0, 40, controls.SWIPE_REACH * 3))
        self.assertEqual(controls.swipe(0, 80, controls.SWIPE_REACH * 3), "down")

    def test_a_swipe_is_one_step_of_the_knob(self):
        self.assertEqual(controls.swipe_detents("up"), -3)
        self.assertEqual(controls.swipe_detents("down"), 3)
        self.assertEqual(controls.swipe_detents(None), 0)

    def test_the_top_hint_follows_what_the_page_draws(self):
        self.assertEqual(controls.top_button(True), "encoder")
        self.assertEqual(controls.top_button(False), "menu")


class SourceTest(unittest.TestCase):
    @staticmethod
    def openers(csi=None, uvc=None, log=None):
        log = log if log is not None else []

        def make(kind, got):
            def f():
                log.append(kind)
                if isinstance(got, Exception):
                    raise got
                return got
            return f

        return {
            sources.CSI: make(sources.CSI, csi),
            sources.UVC: make(sources.UVC, uvc),
            sources.TESTCARD: make(sources.TESTCARD, "card"),
        }

    def test_a_mipi_camera_wins_and_the_usb_host_is_never_started(self):
        log = []
        self.assertEqual(sources.first_source(self.openers("csi", "uvc", log)), "csi")
        self.assertEqual(log, [sources.CSI])

    def test_no_mipi_camera_means_the_usb_camera(self):
        self.assertEqual(sources.first_source(self.openers(None, "uvc")), "uvc")

    def test_a_camera_that_fails_steps_down(self):
        self.assertEqual(sources.first_source(self.openers(OSError("no sensor"), "uvc")), "uvc")

    def test_no_camera_at_all_is_the_test_card(self):
        self.assertEqual(sources.first_source(self.openers(None, None)), "card")
        self.assertEqual(sources.first_source(self.openers(OSError("x"), OSError("y"))), "card")

    def test_a_board_can_name_its_source(self):
        self.assertEqual(sources.first_source(self.openers("csi", "uvc"), forced=sources.UVC), "uvc")

    def test_a_named_source_that_is_missing_steps_down_the_same_way(self):
        self.assertEqual(sources.first_source(self.openers("csi", None), forced=sources.UVC), "csi")

    def test_a_name_nobody_knows_is_ignored(self):
        self.assertEqual(sources.first_source(self.openers("csi", "uvc"), forced="bogus"), "csi")


class FakeCsi:
    def size(self):
        return (1920, 1080, 0)

    def frame(self, timeout=200):
        return b"f"

    def deinit(self):
        self.gone = True


class SourceInterfaceTest(unittest.TestCase):
    def test_csi_answers_the_four_calls(self):
        cam = FakeCsi()
        src = sources.CsiSource(cam)
        self.assertEqual(src.size(), (1920, 1080))
        self.assertEqual(src.frame(), b"f")
        src.start()
        src.stop()
        src.deinit()
        self.assertTrue(cam.gone)

    def test_open_source_uses_the_board_camera(self):
        board = types.SimpleNamespace(camera=FakeCsi())
        self.assertEqual(sources.open_source(board, "unused.jpg").kind, sources.CSI)


class CropTest(unittest.TestCase):
    def test_the_eyes_crops_are_the_factorys(self):
        self.assertEqual(crop.video_crop(1920, 1080, 1072, "1080P", 1), (0, 4, 1920, 1072))
        self.assertEqual(crop.video_crop(1920, 1080, 720, "720P", 1), (320, 60, 1280, 960))
        self.assertEqual(crop.video_crop(1920, 1080, 720, "720P", 2), (640, 300, 640, 480))

    def test_a_small_camera_never_leaves_its_frame(self):
        for res in ("1080P", "720P", "480P"):
            for m in (1, 2, 3, 4):
                x, y, w, h = crop.video_crop(640, 480, 1072, res, m)
                self.assertGreaterEqual(x, 0)
                self.assertGreaterEqual(y, 0)
                self.assertLessEqual(x + w, 640)
                self.assertLessEqual(y + h, 480)
                self.assertGreater(w, 0)


if __name__ == "__main__":
    unittest.main()
