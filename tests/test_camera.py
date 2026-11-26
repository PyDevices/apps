# SPDX-FileCopyrightText: 2026 PyDevices
#
# SPDX-License-Identifier: MIT
"""Eye Camera's decisions, which need no screen or board: how far the
240x240 layout is enlarged, which controls a board gets, which picture source
it uses, what part of a small camera's frame a video takes, and what a
browser page's camera and detector give the app, against stand-ins for both.

    python -m unittest tests.test_camera
"""

import importlib.util
import os
import sys
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "apps", "eyecam")


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


class ModeTest(unittest.TestCase):
    OV5647 = [("a", 800, 1280), ("b", 800, 640), ("c", 800, 800), ("d", 1920, 1080), ("e", 1280, 960)]

    def test_the_smallest_landscape_mode_that_fills_the_preview(self):
        self.assertEqual(sources.pick_mode(self.OV5647, (800, 1280, 0)), (800, 640))

    def test_the_mode_already_open_is_kept(self):
        self.assertIsNone(sources.pick_mode(self.OV5647, (800, 640, 0)))

    def test_no_landscape_mode_keeps_what_there_is(self):
        self.assertIsNone(sources.pick_mode([("a", 480, 800)], (480, 800, 0)))

    def test_the_eyes_one_mode_is_left_alone(self):
        self.assertIsNone(sources.pick_mode([("a", 1920, 1080)], (1920, 1080, 0)))


class CropTest(unittest.TestCase):
    def test_the_eyes_crops_are_the_factorys(self):
        self.assertEqual(crop.video_crop(1920, 1080, 1072, "1080P", 1), (0, 4, 1920, 1072))
        self.assertEqual(crop.video_crop(1920, 1080, 720, "720P", 1), (320, 60, 1280, 960))
        self.assertEqual(crop.video_crop(1920, 1080, 720, "720P", 2), (640, 300, 640, 480))

    def test_the_preview_cut_is_the_eyes_and_always_a_whole_sixteenth(self):
        for m, side in ((1, 960), (2, 480), (3, 320), (4, 240)):
            self.assertEqual(crop.preview_side(1920, 1080, m), side)
        for w, h in ((800, 640), (800, 1280), (1280, 960), (640, 480)):
            for m in (1, 2, 3, 4):
                side = crop.preview_side(w, h, m)
                self.assertEqual(3840 % (3840 // side), 0)
                self.assertLessEqual(side, min(w, h))

    def test_a_small_camera_never_leaves_its_frame(self):
        for res in ("1080P", "720P", "480P"):
            for m in (1, 2, 3, 4):
                x, y, w, h = crop.video_crop(640, 480, 1072, res, m)
                self.assertGreaterEqual(x, 0)
                self.assertGreaterEqual(y, 0)
                self.assertLessEqual(x + w, 640)
                self.assertLessEqual(y + h, 480)
                self.assertGreater(w, 0)


def _load_hw():
    """``hw``, ``hw.desktop`` and ``hw.browser`` as a package, loaded over
    stand-ins for LVGL, appkit and the MicroPython modules they import, which
    are taken out of ``sys.modules`` again afterwards."""
    fakes = {name: types.ModuleType(name) for name in ("lvgl", "framebuf", "jpegio", "ppa", "appkit", "appkit.assets")}
    fakes["jpegio"].JpegEncoder = lambda **kw: None
    fakes["appkit"].assets = fakes["appkit.assets"]
    name = "eyecam_hw"
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(PKG, "hw", "__init__.py"), submodule_search_locations=[os.path.join(PKG, "hw")])
    pkg = importlib.util.module_from_spec(spec)
    with mock.patch.dict(sys.modules, fakes):
        sys.modules[name] = pkg
        spec.loader.exec_module(pkg)
        importlib.import_module(name + ".desktop")
        importlib.import_module(name + ".browser")
        ours = {k: v for k, v in sys.modules.items() if k == name or k.startswith(name + ".")}
    sys.modules.update(ours)  # the package stays importable; the stand-ins go
    return pkg, ours[name + ".browser"]


hw, browser = _load_hw()


class FakePpa:
    """Records each cut, and fills the 240x240 picture with one byte."""

    def __init__(self):
        self.calls = []

    def srm(self, src, sw, sh, dst, dw, dh, **kw):
        self.calls.append((sw, sh, dw, dh, kw))
        dst[:] = b"\x5a" * len(dst)


class FakePageCamera:
    """``displaydev.page_camera.Camera``'s calls: a 1280x720 webcam."""

    def __init__(self, w=1280, h=720):
        self.w, self.h = w, h
        self.asked = []
        self.closed = False
        self.give = True

    def size(self):
        return (self.w, self.h, self.w * self.h * 2)

    def capture_scaled(self, dst, pic_w, pic_h, *, x=0, y=0, w=0, h=0, rotate=0, mirror=False, src_rect=None, swap=False, timeout=1000):
        if src_rect is not None or rotate not in (0, 180):
            raise ValueError("a browser camera turns by 180 degrees only, and doesn't crop")
        self.asked.append((pic_w, pic_h, swap))
        if not self.give:
            return None
        assert len(dst) == pic_w * pic_h * 2
        dst[:2] = b"\x1f\x00"  # blue, little-endian
        return (pic_w, pic_h)

    def close(self):
        self.closed = True


class FakeScope:
    def __init__(self, data_dir):
        self.data_dir = data_dir
        self.adopted = []
        self.closing = []

    def adopt(self, obj):
        self.adopted.append(obj)
        return obj

    def on_close(self, fn):
        self.closing.append(fn)

    def close(self):
        for fn in self.closing:
            fn()
        for obj in self.adopted:
            obj.close()


class BrowserChoiceTest(unittest.TestCase):
    def test_a_browser_gets_the_browser_seams_not_the_test_card(self):
        picked = []
        for platform in ("webassembly", "emscripten", "linux", "esp32"):
            with mock.patch.object(sys, "platform", platform):
                picked.append((hw.in_browser(), hw.on_board()))
        self.assertEqual(picked, [(True, False), (True, False), (False, False), (False, True)])

    def test_build_in_a_browser_uses_hw_browser(self):
        with mock.patch.object(sys, "platform", "webassembly"), \
                mock.patch.object(browser, "build", return_value="browser seams") as build:
            self.assertEqual(hw.build("scope"), "browser seams")
        build.assert_called_once_with("scope")


class BrowserPreviewTest(unittest.TestCase):
    def setUp(self):
        self.ppa = FakePpa()
        patcher = mock.patch.object(browser, "ppa", self.ppa)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.cam = FakePageCamera()
        self.preview = browser.Preview(self.cam)

    def test_each_frame_comes_from_the_page_camera_whole_and_in_lvgls_byte_order(self):
        buf = self.preview.frame(1)
        self.assertEqual(len(buf), 240 * 240 * 2)
        self.assertEqual(self.cam.asked, [(960, 540, False)])  # short side 540, never swapped
        self.assertEqual(bytes(buf[:2]), b"\x5a\x5a")  # what the cut wrote

    def test_zoom_cuts_the_centre_as_a_board_does(self):
        for m in (1, 2, 3, 4):
            self.preview.frame(m)
            sw, sh, dw, dh, kw = self.ppa.calls[-1]
            side = crop.preview_side(960, 540, m)
            self.assertEqual((sw, sh, dw, dh), (960, 540, 240, 240))
            self.assertEqual(kw["src_rect"], ((960 - side) // 2, (540 - side) // 2, side, side))
        sides = [c[4]["src_rect"][2] for c in self.ppa.calls]
        self.assertEqual(sides, sorted(sides, reverse=True))
        self.assertLess(sides[-1], sides[0])

    def test_rotate_turns_the_cut(self):
        self.preview.rotate(-90)
        self.preview.frame(1)
        self.assertEqual(self.ppa.calls[-1][4]["rotate"], 270)

    def test_no_new_frame_keeps_the_last_picture(self):
        first = self.preview.frame(1)
        self.cam.give = False
        self.assertIs(self.preview.frame(2), first)
        self.assertEqual(len(self.ppa.calls), 1)

    def test_a_photo_takes_the_whole_frame_at_the_cameras_size(self):
        buf, w, h = self.preview.source()
        self.assertEqual((w, h), (1280, 720))
        self.assertEqual(len(buf), 1280 * 720 * 2)
        self.assertEqual(self.cam.asked[-1], (1280, 720, False))

    def test_a_small_camera_is_not_enlarged(self):
        preview = browser.Preview(FakePageCamera(640, 480))
        preview.frame(1)
        self.assertEqual(preview.cam.asked, [(640, 480, False)])


class FakeYolo:
    made = []

    def __init__(self, path, score=None):
        self.path, self.score = path, score
        self.closed = False
        FakeYolo.made.append(self)

    def detect(self, img):
        self.seen = img
        return [(10, 20, 30, 40, 0.9, 0), (100, 50, 120, 150, 0.8, 5), (5, 5, 10, 10, 0.4, 0), (1, 2, 3, 4, 0.5, 99)]

    def deinit(self):
        self.closed = True


def _fake_vision():
    espdl = types.ModuleType("espdl")
    espdl.YOLO11 = FakeYolo
    image = types.ModuleType("image")
    image.RGB565 = 3
    image.Image = lambda w, h, fmt, buffer=None: ("img", w, h, fmt, buffer)
    return {"espdl": espdl, "image": image}


class BrowserDetectorTest(unittest.TestCase):
    def setUp(self):
        FakeYolo.made = []
        self.buf = bytearray(240 * 240 * 2)

    def test_objects_are_named_with_their_scores(self):
        with mock.patch.dict(sys.modules, _fake_vision()):
            det = browser.Detector(find=lambda: "/models/yolo11n_coco.espdl")
            got = det.objects(self.buf, 240, 240)
        self.assertEqual(got, [
            (10, 20, 40, 60, "person", 0.9),
            (100, 50, 220, 200, "bus", 0.8),
            (5, 5, 15, 15, "person", 0.4),
            (1, 2, 4, 6, "class 99", 0.5),
        ])
        yolo = FakeYolo.made[0]
        self.assertEqual(yolo.path, "/models/yolo11n_coco.espdl")
        self.assertEqual(yolo.seen, ("img", 240, 240, 3, self.buf))
        self.assertIsNone(det.why)

    def test_people_are_the_person_boxes(self):
        with mock.patch.dict(sys.modules, _fake_vision()):
            det = browser.Detector(find=lambda: "/models/m")
            self.assertEqual(det.people(self.buf, 240, 240), [(10, 20, 40, 60, None), (5, 5, 15, 15, None)])

    def test_the_model_loads_once_on_first_use_and_goes_on_release(self):
        with mock.patch.dict(sys.modules, _fake_vision()):
            det = browser.Detector(find=lambda: "/models/m")
            self.assertEqual(FakeYolo.made, [])  # nothing until the AI page or the album asks
            det.people(self.buf, 240, 240)
            det.objects(self.buf, 240, 240)
            self.assertEqual(len(FakeYolo.made), 1)
            det.release()
            self.assertTrue(FakeYolo.made[0].closed)
            det.people(self.buf, 240, 240)
            self.assertEqual(len(FakeYolo.made), 2)

    def test_faces_find_nothing_and_say_why(self):
        with mock.patch.dict(sys.modules, _fake_vision()):
            det = browser.Detector(find=lambda: "/models/m")
            self.assertEqual(det.faces(self.buf, 240, 240), [])
            self.assertIn("face", det.why.lower())
            det.people(self.buf, 240, 240)
            self.assertIsNone(det.why)  # back in Pedestrian mode, nothing to say

    def test_a_page_without_espdl_says_so_and_finds_nothing(self):
        with mock.patch.dict(sys.modules, {"espdl": None, "image": None}), \
                mock.patch("builtins.print") as printed:
            det = browser.Detector(find=lambda: "/models/m")
            self.assertEqual(det.people(self.buf, 240, 240), [])
            self.assertEqual(det.objects(self.buf, 240, 240), [])
        self.assertIn("espdl", det.why)
        printed.assert_called_once()
        self.assertIn("espdl", printed.call_args[0][0])

    def test_a_model_that_wont_load_says_why(self):
        vision = _fake_vision()

        def refuse(path, score=None):
            raise OSError("the model didn't download")

        vision["espdl"].YOLO11 = refuse
        with mock.patch.dict(sys.modules, vision), mock.patch("builtins.print"):
            det = browser.Detector(find=lambda: "/models/m")
            self.assertEqual(det.people(self.buf, 240, 240), [])
        self.assertIn("didn't download", det.why)


class BrowserBuildTest(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.scope = FakeScope(self.tmp.name)

    def test_the_page_camera_and_detector_with_the_desktops_stand_ins(self):
        cam = FakePageCamera()
        parts = browser.build(self.scope, open_camera=lambda: cam)
        self.assertIs(parts.preview.cam, cam)
        self.assertIsInstance(parts.detector, browser.Detector)
        self.assertIs(parts.photo.preview, parts.preview)
        self.assertTrue(parts.desktop)
        self.assertTrue(parts.browser)
        self.scope.close()
        self.assertTrue(cam.closed)  # the browser stops showing the camera in use

    def test_a_camera_that_wont_open_is_an_error_not_a_test_card(self):
        def refuse():
            raise OSError("this page wasn't allowed to use the camera")

        with self.assertRaises(OSError):
            browser.build(self.scope, open_camera=refuse)


if __name__ == "__main__":
    unittest.main()
