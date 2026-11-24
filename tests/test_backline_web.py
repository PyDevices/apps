# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Backline's web page in headless Chromium, with this process as the board.

    python -m unittest tests.test_backline_web

The page (``programs/backline-web``) runs in MicroPython's WebAssembly build.
As the box, it plays a song through Web Audio and serves its desk over
WebSerial and Web Bluetooth; the board on the far end is Backline's own desk
view (``backline.desk_main.Remote``, LVGL on a display in memory) in this
process, behind the stand-in ports omnipython's hmilink web gate uses
(``tests/hmilink_web/mock_ports.js``). As the desk, it joins a box in this
process over the same stand-ins and over a real WebSocket. Each case checks
both ways: the desk follows the song's part and bar, and a pedal pressed on
the desk reaches the box. The box case also records what the page played
through Web Audio and finds the drum hits in it at the notes the engine
played. That needs a computer with time to spare: when other work keeps the
browser from rendering in real time, the sound runs out and the check fails,
saying how often.

A fault planted in the page (``?plant=``) must fail its case.

Needs Playwright with Chromium, an OmniPython checkout
(``$OMNIPYTHON_DIR``, or one beside or above this checkout) and MicroPython's
WebAssembly build (``$BACKLINE_WASM``, or a ``bin`` above this checkout), and
on this Python LVGL, svgio, icons (with ttfio), audiodsp and
audioinstruments. Without them the skip is loud, and
``BACKLINE_REQUIRE_BROWSER=1`` makes it a failure. ``$BACKLINE_SHOTS`` names a
folder for screenshots of the page and the board's desk while a song plays,
and the recording.

The desk's Bluetooth link on a board (``desk_main.opener("ble:...")``) is
also run here over ``bledev.fake``, with no browser.
"""

import array
import base64
import functools
import http.server
import importlib.util
import json
import os
import socket
import sys
import threading
import time
import unittest
import wave
from pathlib import Path

TESTS = Path(__file__).resolve().parent
REPO = TESTS.parent
PAGE_TOOL = REPO / "programs" / "backline-web" / "tools" / "page.py"
SHOTS = os.environ.get("BACKLINE_SHOTS")
REQUIRE = os.environ.get("BACKLINE_REQUIRE_BROWSER") == "1"
RATE = 48000

#: Faults the page can carry, and the case each must fail.
PLANTS = {
    "silent": "box",          # nothing reaches Web Audio
    "deaf-pedal": "box",      # the box ignores pedals
    "frozen-floor": "box",    # the page's floor view stops following
    "no-desks": "box",        # a port the page opens never joins the box
    "deaf-desk": "desk",      # the desk page's pedals never leave it
    "frozen-desk": "desk",    # the desk page stops following its box
}


def _load_page_tool():
    spec = importlib.util.spec_from_file_location("backline_page_tool", PAGE_TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


page_tool = _load_page_tool()


def _setup():
    """Put the pieces on the path; returns why the cases can't run, or None."""
    try:
        omni = page_tool.find_omnipython(None)
    except SystemExit as e:
        hmilink = os.environ.get("HMILINK_PATH")
        if not hmilink:
            return str(e)
        omni = None                       # hmilink alone: enough for the checks with no browser
        for path in (REPO / "apps", REPO / "lib", Path(hmilink), TESTS):
            if str(path) not in sys.path:
                sys.path.insert(0, str(path))
        _setup.omni = None
        return None
    for path in (REPO / "apps", REPO / "lib", omni / "lib", TESTS):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    for path in (omni / "packages" / "icons", omni / "lib", omni / "utils"):
        if str(path) not in sys.path:
            sys.path.append(str(path))      # after what's installed: only what's missing comes from here
    _setup.omni = omni
    return None


def _missing():
    reason = _setup()
    if reason:
        return reason
    if _setup.omni is None:
        return "no OmniPython checkout with hmilink's web gate ($OMNIPYTHON_DIR)"
    try:
        page_tool.find_wasm(None)
    except SystemExit as e:
        return str(e)
    for name in ("playwright.sync_api", "lvgl", "svgio", "icons", "audiocore", "audioinstruments"):
        try:
            __import__(name)
        except ImportError as e:
            return "%s: %s" % (name, e)
    try:
        import icons

        icons.mask("add", 24)
    except Exception as e:  # noqa: BLE001 - ttfio is missing or can't draw
        return "icons can't draw here: %s" % e
    return None


def _skip(reason):
    message = "Backline's web page checks did NOT run: " + reason
    if REQUIRE:
        raise AssertionError(message)
    sys.stderr.write("\n*** " + message + " ***\n")
    raise unittest.SkipTest(message)


# -- the board's end of a page port -------------------------------------------


class HostEnd:
    """A stream for `hmilink.stream.link` whose far end is the page's port."""

    def __init__(self):
        self.inbox = b""
        self.outbox = b""
        self.heard = False

    def read(self, n):
        data, self.inbox = self.inbox[:n], self.inbox[n:]
        return data or None

    def write(self, data):
        self.outbox += data
        return len(data)

    def feed(self, data):
        if data:
            self.heard = True
            self.inbox += bytes(data)

    def take(self):
        out, self.outbox = self.outbox, b""
        return list(out)


class DeskHost:
    """A board running Backline's desk view, joined to the page's box."""

    SIZE = (800, 480)

    def __init__(self):
        import hmilink
        import lvgl as lv
        from hmilink import stream

        import _headless
        from backline import desk_main

        if not hasattr(DeskHost, "frame"):
            DeskHost.frame = _headless.display(*self.SIZE)
        self.end = HostEnd()
        screen = lv.obj(None)
        lv.screen_load(screen)
        self.remote = desk_main.Remote(screen, self.SIZE, "page", None,
                                       lambda _h, _p: hmilink.Panel(stream.link(self.end)), "the page")
        self.drawn = time.monotonic()

    @property
    def desk(self):
        return self.remote.desk

    def poll(self):
        import _headless

        self.remote.step()
        now = time.monotonic()
        if now - self.drawn >= 0.03:
            _headless.advance(int((now - self.drawn) * 1000))
            self.drawn = now

    def xfer(self, _name, data):
        self.end.feed(data)
        self.poll()
        return self.end.take()

    def save(self, path):
        import _headless

        _headless.refresh()
        _save_rgb565(path, DeskHost.frame, *self.SIZE)


class BoxHost:
    """A board running Backline's box, at the pace of the wall clock, its
    desk link a page port (``"serial"`` or ``"bluetooth"``) or a WebSocket
    on its desk port (``"ws"``)."""

    def __init__(self, kind):
        import audiocore
        import hmilink
        from hmilink import local, tcp

        from backline import box as boxmod

        self.audiocore = audiocore
        self.kind = kind
        self.frames = 0
        self.start = time.monotonic()
        self.box = boxmod.Box(lambda: self.frames, song="rock", kit="rhythm909",
                              now_ms=lambda: int((time.monotonic() - self.start) * 1000))
        self.mine = hmilink.Panel(local.connect(self.box.device.add(local.serve())))
        self.end = HostEnd()
        self.attached = False
        self.port = None
        if kind == "ws":
            s = socket.socket()
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
            s.close()
            self.box.device.add(tcp.serve(self.port, bind="127.0.0.1"))

    def poll(self):
        from hmilink import stream

        if not self.attached and self.kind != "ws" and (self.kind == "serial" or self.end.heard):
            # A board on hmilink.ble sends nothing until the central speaks.
            self.box.device.add(stream.link(self.end))
            self.attached = True
        due = int((time.monotonic() - self.start) * RATE)
        if due - self.frames > RATE // 2:
            self.frames = due - RATE // 50       # fell behind: skip ahead, as a board's output would
        while self.frames < due:
            self.box.service()
            _r, buf = self.audiocore.get_buffer(self.box.bus.output)
            self.frames += len(buf) // 4
        self.box.poll()
        self.mine.poll()

    def xfer(self, _name, data):
        self.end.feed(data)
        self.poll()
        return self.end.take()

    def close(self):
        self.box.close()


# -- what the checks read --------------------------------------------------------


def _save_rgb565(path, frame, w, h):
    from PIL import Image

    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        row = 2 * y * w
        for x in range(w):
            v = frame[row + 2 * x] | (frame[row + 2 * x + 1] << 8)
            px[x, y] = (((v >> 11) & 31) * 255 // 31, ((v >> 5) & 63) * 255 // 63, (v & 31) * 255 // 31)
    img.save(path)


def onsets(pcm, rate):
    """The times, in seconds, where a drum hit starts in ``pcm`` (16-bit mono)."""
    hop = rate // 200
    if not hop or len(pcm) < 3 * hop:
        return []
    env = [max(abs(v) for v in pcm[i:i + hop]) for i in range(0, len(pcm) - hop, hop)]
    if not env:
        return []
    peak = max(env)
    found = []
    for i in range(2, len(env)):
        rise = env[i] - min(env[i - 1], env[i - 2])
        if rise > 0.12 * peak and (not found or i * hop / rate - found[-1] > 0.045):
            found.append(i * hop / rate)
    return found


def hits(notes, rate=RATE, merge=0.015):
    """The times the engine's notes (``[frame, pitch, velocity]``) sound, in
    seconds, notes closer than ``merge`` taken as one hit."""
    times = sorted(n[0] / rate for n in notes if n[2] > 0)
    out = []
    for t in times:
        if not out or t - out[-1] > merge:
            out.append(t)
    return out


def matched(heard, played, within=0.02):
    """The share of ``played`` hits with an onset in ``heard`` within
    ``within`` seconds, once the two are lined up at their best offset."""
    if not heard or not played:
        return 0.0, 0.0
    best = (0.0, 0.0)
    for k in range(min(6, len(heard))):
        offset = heard[k] - played[0]
        n = 0
        j = 0
        for t in played:
            t += offset
            while j < len(heard) and heard[j] < t - within:
                j += 1
            if j < len(heard) and abs(heard[j] - t) <= within:
                n += 1
        share = n / len(played)
        if share > best[0]:
            best = (share, offset)
    return best


# -- the browser -----------------------------------------------------------------


class _Browser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        reason = _missing()
        if reason:
            _skip(reason)
        from playwright.sync_api import sync_playwright

        site = page_tool.Site(_setup.omni, page_tool.find_wasm(None))
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), page_tool.handler(site))
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d/" % cls.server.server_address[1]
        mocks = _setup.omni / "tests" / "hmilink_web" / "mock_ports.js"
        cls.scripts = ["window.gateLog = (line) => console.log(line);", mocks.read_text(),
                       (TESTS / "backline_web" / "capture.js").read_text()]
        cls.pw = sync_playwright().start()
        try:
            # No sound server: Chromium plays to its own silent output,
            # which keeps time steadily and keeps the drums off the speakers.
            env = dict(os.environ, PULSE_SERVER="unix:/nonexistent", ALSA_CONFIG_PATH="/nonexistent")
            cls.browser = cls.pw.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"], env=env)
        except Exception as e:  # noqa: BLE001 - said in the skip
            cls.pw.stop()
            cls.server.shutdown()
            _skip("no Chromium for Playwright: %s" % e)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.shutdown()
        cls.server.server_close()

    def open(self, host, role, query=""):
        page = self.browser.new_page(viewport={"width": 1100, "height": 900})
        page.expose_function("hostXfer", host.xfer)
        for script in self.scripts:
            page.add_init_script(script=script)
        page.goto("%s?role=%s&%s" % (self.base, role, query))
        page.wait_for_function("globalThis.backlineState !== null || "
                               "document.getElementById('status').classList.contains('bad')", timeout=120000)
        self.assertNotIn("Couldn't start", page.inner_text("#status"))
        return page

    def until(self, page, host, want, seconds, what):
        """Run page and host until ``want(state)`` holds; fail saying ``what``."""
        deadline = time.monotonic() + seconds
        state = None
        while time.monotonic() < deadline:
            page.wait_for_timeout(20)    # the stand-in ports call the host while this waits
            host.poll()
            state = page.evaluate("globalThis.backlineState")
            status = page.locator("#status")
            if "Stopped:" in status.inner_text():
                self.fail("the page stopped: %s" % status.inner_text())
            if state and want(state):
                return state
        self.fail("%s, within %d s; the page said %r" % (what, seconds, state))

    @staticmethod
    def shot(page, name):
        if SHOTS:
            os.makedirs(SHOTS, exist_ok=True)
            page.screenshot(path=os.path.join(SHOTS, name))


class BrowserIsTheBox(_Browser):
    """Phase (a): the page plays the song, and a board is its desk."""

    @staticmethod
    def tap(page, host):
        """A tap of pedal A on the board's desk: down and up in one message
        batch, so a page slow to read its port can't make it a hold."""
        host.desk.pedal(0, True)
        host.desk.pedal(0, False)
        host.poll()

    def check_box(self, join="#join-bt", plant="", seconds=25, sound=True):
        host = DeskHost()
        page = self.open(host, "box", "song=rock&kit=rhythm909&record=1&plant=" + plant)
        try:
            page.click(join)              # also the click the browser wants before it plays sound
            desk = host.desk
            self.until(page, host, lambda s: s["desks"] == 1 and desk.panel is not None and desk.panel.ready,
                       seconds, "the board's desk joined the page's box")
            self.assertEqual((desk.panel.doc or {}).get("name"), "Straight Rock")
            # Pedal A on the board's desk: a tap starts the song on the page.
            self.tap(page, host)
            self.until(page, host, lambda s: s["playing"] and s["part"] == "Main 1" and s["floor_part"] == "MAIN 1",
                       seconds, "the desk's pedal started the song on the page, into Main 1")
            self.until(page, host, lambda s: (desk.tele or {}).get("part") == "Main 1",
                       seconds, "the board's desk followed the page into Main 1")
            wheres = set()
            for _ in range(60):
                self.until(page, host, lambda s: True, 1, "")
                wheres.add(desk.shown.get("where"))
            self.assertGreaterEqual(len(wheres), 3, "the board's desk followed the bar and beat: %r" % wheres)
            floor_bars = set()
            for _ in range(8):               # a bar is two seconds at the song's tempo
                floor_bars.add(self.until(page, host, lambda s: True, 1, "")["floor_bar"])
                page.wait_for_timeout(700)
            self.assertGreaterEqual(len(floor_bars), 2, "the page's floor followed the bar: %r" % floor_bars)
            self.shot(page, "page-is-the-box.png")
            if SHOTS:
                host.save(os.path.join(SHOTS, "board-desk-of-the-page.png"))
            # A tap for a fill, from the board, heard on the page and back.
            self.tap(page, host)
            self.until(page, host, lambda s: s["part"] == "Fill 1" and (desk.tele or {}).get("part") == "Fill 1",
                       seconds, "a fill asked for on the board's desk played on the page, and the desk showed it")
            self.until(page, host, lambda s: s["part"] == "Main 1", seconds, "the fill went back to Main 1")
            if sound:
                self.check_sound(page)
        finally:
            page.close()

    def check_sound(self, page):
        got = page.evaluate("backlineCapture()")
        self.assertGreater(got["rate"], 0, "the page made no sound at all")
        pcm = array.array("h", base64.b64decode(got["pcm"]))
        notes = json.loads(page.evaluate("backlineNotes()"))
        heard = onsets(pcm, got["rate"])
        played = hits(notes)
        share, offset = matched(heard, played)
        if SHOTS:
            with wave.open(os.path.join(SHOTS, "page-is-the-box.wav"), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(got["rate"])
                w.writeframes(pcm.tobytes())
            with open(os.path.join(SHOTS, "page-is-the-box-notes.json"), "w") as f:
                json.dump({"notes": notes, "rate": RATE, "heard": heard, "offset": offset, "share": share}, f)
        self.assertGreater(len(played), 20, "the engine played the song")
        self.assertGreater(len(heard), 20, "Web Audio played drum hits: %d onsets" % len(heard))
        late = page.evaluate("globalThis.backlineState.late")
        self.assertGreaterEqual(share, 0.85, "%.0f%% of the engine's hits heard where it played them; the sound "
                                "ran out %d times (a machine too busy to keep the page in time does this)"
                                % (100 * share, late))

    def test_desk_on_bluetooth(self):
        self.check_box("#join-bt")

    def test_desk_on_usb(self):
        self.check_box("#join-usb", sound=False)


class BrowserIsTheDesk(_Browser):
    """Phase (b): a board plays the song, and the page is its desk."""

    def check_desk(self, kind, plant="", seconds=25):
        host = BoxHost(kind)
        page = self.open(host, "desk", "plant=" + plant)
        try:
            if kind == "ws":
                page.fill("#ws-host", "127.0.0.1:%d" % host.port)
                page.click("#join-ws")
            else:
                page.click("#join-bt" if kind == "bluetooth" else "#join-usb")
            self.until(page, host, lambda s: s["ready"] and s["song"] == "Straight Rock", seconds,
                       "the page joined the box")
            page.locator("#screen").focus()
            page.keyboard.down(" ")
            page.wait_for_timeout(60)
            page.keyboard.up(" ")
            self.until(page, host, lambda s: host.box.engine.transport["playing"] and s["part"] == "Main 1"
                       and s["desk_part"] == "Main 1", seconds,
                       "the page's pedal started the box, and its desk followed into Main 1")
            wheres = set()
            for _ in range(4):
                wheres.add(self.until(page, host, lambda s: True, 1, "")["desk_where"])
                page.wait_for_timeout(500)
            self.assertGreaterEqual(len(wheres), 3, "the page's desk followed the bar and beat: %r" % wheres)
            self.shot(page, "page-is-the-desk-%s.png" % kind)
            host.mine.set("/tempo", 100)
            self.until(page, host, lambda s: s["tempo"] == 100, seconds, "a tempo set on the box reached the page")
        finally:
            page.close()
            host.close()

    def test_on_bluetooth(self):
        self.check_desk("bluetooth")

    def test_on_usb(self):
        self.check_desk("serial")

    def test_over_websocket(self):
        self.check_desk("ws")


class PlantedFaults(_Browser):
    """A check that can't fail proves nothing: each plant must fail its case."""

    def test_each_plant_fails(self):
        box = BrowserIsTheBox("test_desk_on_bluetooth")
        desk = BrowserIsTheDesk("test_on_bluetooth")
        for c in (box, desk):
            c.browser, c.base, c.scripts = self.browser, self.base, self.scripts
        for plant, case in PLANTS.items():
            with self.subTest(plant=plant):
                with self.assertRaises(AssertionError):
                    if case == "box":
                        box.check_box("#join-bt", plant=plant, seconds=8)
                    else:
                        desk.check_desk("bluetooth", plant=plant, seconds=8)


# -- the board's side of the desk link, with no browser --------------------------


class DeskLinks(unittest.TestCase):
    def setUp(self):
        reason = _setup()
        if reason:
            _skip(reason)

    def test_specs(self):
        from backline import remote

        self.assertEqual(remote.desk_link("ble:Stage"), ("ble", "Stage"))
        self.assertEqual(remote.desk_link("ble:"), ("ble", remote.BLE_NAME))
        self.assertEqual(remote.desk_link("usb"), ("usb", None))
        self.assertEqual(remote.desk_link("192.0.2.7:9400"), ("tcp", ("192.0.2.7", 9400)))
        self.assertEqual(remote.desk_link("box"), ("tcp", ("box", remote.PORT)))

    def test_ble_name(self):
        import tempfile

        from backline import remote

        self.assertIsNone(remote.ble_name({}))
        self.assertEqual(remote.ble_name({"ble": "Stage"}), "Stage")
        self.assertIsNone(remote.ble_name({"ble": ""}))
        with tempfile.TemporaryDirectory() as folder:
            with open(folder + "/settings.json", "w") as f:
                json.dump({"ble": "Backline"}, f)
            self.assertEqual(remote.ble_name({}, folder), "Backline")
            self.assertIsNone(remote.ble_name({"ble": ""}, folder), "the app's own setting wins")

    def test_desk_on_bluetooth_over_fake_air(self):
        """A board's desk advertises; a box connects to it, as a browser does."""
        for name in ("lvgl", "svgio", "icons", "audiocore", "audioinstruments", "bledev.fake", "hmilink.ble"):
            try:
                __import__(name)
            except ImportError as e:
                _skip("%s: %s" % (name, e))
        import hmilink
        import lvgl as lv
        from bledev.fake import Air, FakeBLE
        from hmilink import ble

        import _headless
        from backline import box as boxmod
        from backline import desk_main

        if not hasattr(DeskHost, "frame"):
            DeskHost.frame = _headless.display(*DeskHost.SIZE)
        air = Air()
        board = FakeBLE(air=air)
        laptop = FakeBLE(air=air, peripheral=False)
        where, connect = desk_main.opener("ble:Backline", adapter=board)
        self.assertEqual(where, "Bluetooth, as Backline")
        screen = lv.obj(None)
        remote = desk_main.Remote(screen, DeskHost.SIZE, "ble:Backline", None, connect, where)
        self.assertIn("WAITING FOR THE BOX", remote.desk.next.get_text())
        frames = [0]
        box = boxmod.Box(lambda: frames[0], song="rock", kit="rhythm909")
        try:
            box.device.add(ble.connect("Backline", adapter=laptop))
            for _ in range(400):
                box.poll()
                remote.step()
                if remote.desk.panel.ready and not remote.waiting:
                    break
                time.sleep(0.005)
            for _ in range(200):                # the next telemetry redraws the line
                box.poll()
                remote.step()
                if "WAITING" not in remote.desk.next.get_text():
                    break
                time.sleep(0.005)
            self.assertTrue(remote.desk.panel.ready, "the board's desk has the box's song")
            self.assertEqual(remote.desk.panel.doc["name"], "Straight Rock")
            self.assertNotIn("WAITING", remote.desk.next.get_text())
            remote.desk.pedal(0, True)
            for _ in range(200):
                box.poll()
                remote.step()
                if box.engine.pedals[0].state != "up":
                    break
                time.sleep(0.005)
            self.assertNotEqual(box.engine.pedals[0].state, "up", "the desk's pedal reached the box")
        finally:
            remote.close()
            box.close()


if __name__ == "__main__":
    unittest.main()
