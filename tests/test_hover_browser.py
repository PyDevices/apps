# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Hover styles in the direct MicroPython WebAssembly build, under Chromium.

Runs LVGL on a canvas with the shared hover theme applied, moves the real
mouse over one of two buttons with no button down, and checks that only that
button's pixels change and that they change back when the mouse leaves.

Needs Playwright with Chromium and a wasm build with LVGL: ``bin/micropython.mjs``
in the workspace, or the folder named by ``OMNIPYTHON_WASM_DIR``. Without them
the skip is loud, and ``OMNIPYTHON_REQUIRE_BROWSER=1`` turns it into a failure.
"""

import functools
import http.server
import os
import sys
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PAGE = """<!doctype html><meta charset="utf-8"><body style="margin:0;background:#000">
<canvas id="display_canvas" width="320" height="480" tabindex="0"></canvas>
<script type="module">
const { loadMicroPython } = await import("/wasm/micropython.mjs");
const mp = await loadMicroPython({ stdout: (l) => console.log(l), linebuffer: true, heapsize: 24 * 1024 * 1024 });
mp.FS.mkdirTree("/t/appkit");
mp.FS.writeFile("/t/appkit/hover.py", await (await fetch("/hover.py")).text());
await mp.runPythonAsync(await (await fetch("/app.py")).text());
window.ready = true;
</script>"""

APP = """
import sys
sys.path.insert(0, "/t")
import display_driver
import lvgl as lv
from board_config import display_drv
from appkit import hover

hover.apply()
scr = lv.screen_active()
scr.set_style_bg_color(lv.color_hex(0x0B0E14), 0)
left = lv.button(scr)
left.set_size(120, 60)
left.align(lv.ALIGN.CENTER, -70, 0)
right = lv.button(scr)
right.set_size(120, 60)
right.align(lv.ALIGN.CENTER, 70, 0)
"""


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = dict(
        http.server.SimpleHTTPRequestHandler.extensions_map,
        **{".mjs": "text/javascript", ".wasm": "application/wasm"},
    )
    wasm_dir = None

    def translate_path(self, path):
        path = path.split("?", 1)[0]
        if path.startswith("/wasm/"):
            return str(self.wasm_dir / path[len("/wasm/"):])
        if path == "/hover.py":
            return str(ROOT / "lib" / "appkit" / "hover.py")
        return super().translate_path(path)

    def do_GET(self):
        pages = {"/": (PAGE, "text/html"), "/app.py": (APP, "text/plain")}
        if self.path not in pages:
            return super().do_GET()
        text, ctype = pages[self.path]
        body = text.encode()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def _wasm_dir():
    env = os.environ.get("OMNIPYTHON_WASM_DIR")
    if env:
        return Path(env)
    for parent in ROOT.parents:
        if (parent / "bin" / "micropython.mjs").exists():
            return parent / "bin"
    return None


def _missing():
    try:
        import PIL  # noqa: F401
        import playwright.sync_api  # noqa: F401
    except ImportError as e:
        return "%s is not installed" % e.name
    folder = _wasm_dir()
    if folder is None or not (folder / "micropython.mjs").exists():
        return "no wasm build (bin/micropython.mjs or OMNIPYTHON_WASM_DIR)"
    return None


class HoverInTheBrowser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        reason = _missing()
        if reason:
            message = "the browser hover gate did NOT run: " + reason
            if os.environ.get("OMNIPYTHON_REQUIRE_BROWSER") == "1":
                raise AssertionError(message)
            sys.stderr.write("\n*** " + message + " ***\n")
            raise unittest.SkipTest(message)
        from playwright.sync_api import sync_playwright

        Handler.wasm_dir = _wasm_dir()
        cls.server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0), functools.partial(Handler, directory=str(ROOT))
        )
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.pw = sync_playwright().start()
        try:
            cls.browser = cls.pw.chromium.launch()
        except Exception as e:
            cls.pw.stop()
            cls.server.shutdown()
            raise unittest.SkipTest("no Chromium for Playwright: {}".format(e))

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.shutdown()

    def test_the_button_under_the_mouse_changes_and_changes_back(self):
        import io

        from PIL import Image, ImageChops

        page = self.browser.new_page(viewport={"width": 340, "height": 500})
        try:
            page.goto("http://127.0.0.1:%d/" % self.server.server_port)
            page.wait_for_function("window.ready === true", timeout=120000)
            page.wait_for_timeout(1500)

            def shot():
                return Image.open(io.BytesIO(page.screenshot())).convert("RGB")

            idle = shot()
            page.mouse.move(90, 240)  # over the left button, no button down
            page.wait_for_timeout(700)
            over = shot()
            page.mouse.move(300, 20)  # off both buttons
            page.wait_for_timeout(700)
            away = shot()

            box = ImageChops.difference(idle, over).getbbox()
            self.assertIsNotNone(box, "nothing changed under the mouse")
            left, top, right, bottom = box
            self.assertTrue(20 <= left and right <= 160 and 200 <= top and bottom <= 280, box)
            self.assertIsNone(ImageChops.difference(idle, away).getbbox(), "the hover stayed")
        finally:
            page.close()


if __name__ == "__main__":
    unittest.main()
