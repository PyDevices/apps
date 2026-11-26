# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Camera and Detect show the camera's picture on any panel.

A board whose display is on a bus (the ESP32-P4X-EYE's SPI ST7789) has no
framebuffer, and a panel with one (an RGB or DSI panel) takes each frame
straight into it. Both apps run here on a 240 x 240 display with no window,
against a stand-in camera that paints every frame red, and the red has to
reach the screen. Needs LVGL and pygraphics for CPython; without them the
tests skip, loudly, and ``CAMERA_PREVIEW_REQUIRE=1`` makes that a failure.

    python -m unittest tests.test_camera_preview
"""

import os
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(ROOT, "tests")

try:
    import lvgl as lv
    import pygraphics  # noqa: F401  (Detect draws its boxes with it)
except ImportError as e:
    lv = None
    MISSING = str(e)
else:
    MISSING = ""

SIZE = 240
RED = 0xF800
SKIP = lv is None and not os.environ.get("CAMERA_PREVIEW_REQUIRE")


class FakeCamera:
    """Every frame is red, scaled into the block it is asked for."""

    def __init__(self):
        self.frames = 0

    def size(self):
        return (1920, 1080, 1920 * 1080 * 2)

    def sensor(self):
        return ("FAKE",)

    def capture_scaled(self, dst, pic_w, pic_h, *, x=0, y=0, w=0, h=0, timeout=1000, **kw):
        w = w or pic_w - x
        h = h or pic_h - y
        px = RED.to_bytes(2, "little") * w
        for row in range(y, y + h):
            o = (row * pic_w + x) * 2
            dst[o : o + w * 2] = px
        self.frames += 1
        return (w, h)

    def capture_jpeg(self, quality=80, timeout=1000):
        return None

    def exposure(self, v):
        pass

    def reg(self, a, v):
        pass

    def deinit(self):
        pass


class BusDisplay:
    """A panel on a bus: no framebuffer."""

    width = height = SIZE

    def framebuffers(self):
        return None


class PanelDisplay:
    """A panel with a framebuffer of its own, presented by `flush_rect`."""

    width = height = SIZE

    def __init__(self):
        self.fb = bytearray(SIZE * SIZE * 2)
        self.flushed = []

    def framebuffers(self):
        return (self.fb, None, len(self.fb), SIZE * 2)

    def flush_rect(self, x, y, w, h):
        self.flushed.append((x, y, w, h))


class Scope:
    name = "camera"
    header = None
    status = None
    launcher = None

    def __init__(self, root):
        self.root = root
        self.size = (SIZE, SIZE)
        self.rect = (0, 0, SIZE, SIZE)
        self.loop = None
        self._stores = {}

    def store(self, name):
        return self._stores.setdefault(name, {})

    def on_close(self, fn):
        pass

    def every(self, ms, fn):
        pass

    def foreground(self, fn):
        self.loop = fn


class Yolo:
    def __init__(self, path, score=0.15):
        pass

    def detect(self, img):
        return [(10, 10, 40, 30, 0.9, 0)]

    def deinit(self):
        pass


@unittest.skipIf(SKIP, "LVGL or pygraphics missing: %s" % MISSING)
class PreviewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for p in (TESTS, ROOT, os.path.join(ROOT, "lib")):
            sys.path.insert(0, p)  # lib/ first: tests/appkit would hide the real one
        import _headless

        cls.headless = _headless
        cls.frame = _headless.display(SIZE, SIZE)

    def run_app(self, name, display, extra=None):
        """Open app *name* on *display*, run three frames and draw the screen."""
        cam = FakeCamera()
        net = types.SimpleNamespace(ip=lambda: None, hostname=lambda: None)
        mods = {
            "board_config": types.SimpleNamespace(display_drv=display),
            "board_peripherals": types.SimpleNamespace(camera=lambda **kw: cam),
            "touchkit.net": net,
        }
        mods.update(extra or {})
        saved = {k: sys.modules.get(k) for k in mods}
        sys.modules.update(mods)
        try:
            import touchkit
            from touchkit import cam as tcam

            touchkit.net = net
            tcam.mount_sd = lambda readonly=True: None
            tcam.unmount_sd = lambda card: None
            sys.modules.pop("apps." + name, None)
            app = __import__("apps." + name, None, None, ["main"])
            if name == "detect":
                app._model = lambda scope: "/models/yolo11n_coco.espdl"
            screen = lv.obj(None)
            lv.screen_load(screen)
            scope = Scope(screen)
            app.main(scope)
            self.assertIsNotNone(scope.loop, "%s stopped before its preview started" % name)
            for _ in range(3):
                scope.loop()
            self.headless.refresh()
            return cam
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v

    def red_on_screen(self):
        px = RED.to_bytes(2, "little")
        f = self.frame
        return sum(1 for i in range(0, len(f), 2) if f[i : i + 2] == px)

    def test_camera_on_a_panel_with_no_framebuffer_shows_the_picture(self):
        cam = self.run_app("camera", BusDisplay())
        self.assertEqual(cam.frames, 3)
        # The picture takes the width of a 240 x 240 screen: 200 x 100 at least.
        self.assertGreater(self.red_on_screen(), 200 * 100)

    def test_camera_on_a_framebuffer_panel_writes_the_panel_and_presents_it(self):
        d = PanelDisplay()
        self.run_app("camera", d)
        self.assertEqual(len(d.flushed), 3)
        x, y, w, h = d.flushed[0]
        o = ((y + h // 2) * SIZE + x + w // 2) * 2
        self.assertEqual(bytes(d.fb[o : o + 2]), RED.to_bytes(2, "little"))

    def detect_modules(self):
        image = types.SimpleNamespace(RGB565=1, Image=lambda w, h, fmt, buffer=None: buffer)
        return {"espdl": types.SimpleNamespace(YOLO11=Yolo), "image": image}

    def test_detect_on_a_panel_with_no_framebuffer_shows_the_picture(self):
        cam = self.run_app("detect", BusDisplay(), self.detect_modules())
        self.assertEqual(cam.frames, 3)
        self.assertGreater(self.red_on_screen(), 200 * 100)

    def test_detect_on_a_framebuffer_panel_copies_the_frame_in_and_presents_it(self):
        d = PanelDisplay()
        self.run_app("detect", d, self.detect_modules())
        self.assertEqual(len(d.flushed), 3)
        x, y, w, h = d.flushed[0]
        o = ((y + h - 2) * SIZE + x + w - 2) * 2  # clear of the stand-in's box
        self.assertEqual(bytes(d.fb[o : o + 2]), RED.to_bytes(2, "little"))

    def test_no_camera_in_a_browser_points_at_the_browser_and_connections(self):
        from unittest import mock

        from touchkit import cam as tcam

        with mock.patch.object(sys, "platform", "webassembly"):
            text = tcam.no_camera_text(OSError("the browser found no camera"), "Video Camera")
        self.assertIn("the browser found no camera", text)
        self.assertIn("Connections", text)
        self.assertNotIn("CSI", text)


if __name__ == "__main__":
    unittest.main()
