# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Cast: a screen of its own on a display across the room, and the panel as its remote.

Pick a receiver and press Cast. The board draws a 1280 x 720 LVGL screen in
memory, a second LVGL display that only the receiver shows, and streams it
over Miracast, about a frame behind, so the remote feels direct: to a Roku
through its Screen mirroring, or to a Windows PC with its Wireless Display
app open. Or it serves the screen as HLS for VLC or any HLS player (ten
seconds behind; fine to watch, slow to drive). The panel shows the remote:
the d-pad and OK move round the cast screen, Back returns to its home.

On the cast screen: a clock, the photos the Camera app took, the camera
live, and what the board is. The list fills as receivers are found (see
``receivers``). A Roku needs Screen mirroring on (Settings > System >
Screen mirroring), and the first cast may ask on the receiver to allow it.

It needs gallery's cast example in ``/lib/examples/cast`` and
``/lib/examples/roku_hls``. ``config.json`` in its data folder:
``{"name": "Kitchen panel"}`` is the name the receiver shows, and
``{"prefer": "Bedroom"}`` picks the receiver whose name holds that text
when there's no last one to go back to. The receivers cast to before are
kept in ``receivers.json`` there.
"""

import sys
import time

import lvgl as lv
from multimer import ticks_add, ticks_diff, ticks_ms

from devkit import cam, ecp, net, settings, ui
from devkit.clock import sleep_ms

CAST_W, CAST_H = 1280, 720
FPS = 20
BITRATE = 2_000_000
DEFAULTS = {"name": "DEV-KIT", "prefer": None}
HLS = {"name": "VLC or any HLS player", "host": None, "kind": "hls"}
EXAMPLES = ("/lib/examples/cast", "/lib/examples/roku_hls")

TILES = (
    ("Clock", lv.SYMBOL.BELL, 0x1E6F8C),
    ("Photos", lv.SYMBOL.IMAGE, 0x8C3B1E),
    ("Camera", lv.SYMBOL.VIDEO, 0x3B6E2A),
    ("About", lv.SYMBOL.LIST, 0x6A2C8C),
)

state = None  # the open app's state, for the console


def _encoder_room():
    """(largest free block of internal RAM, what the encoder needs), in bytes.

    The P4's H.264 encoder keeps its reference rows in one block of internal
    RAM, 1,152 bytes for each 16 pixels of width (92 KB at 1280 wide), and
    nothing else will do. Internal RAM is shared with Wi-Fi and every
    thread's stack, so after enough use it can be free but in pieces.
    """
    need = 3 * 16 * 24 * (CAST_W // 16) + 128
    try:
        import esp32

        heaps = esp32.idf_heap_info(esp32.HEAP_DATA)
    except Exception:
        return need, need
    return max((h[2] for h in heaps if h[0] < 1_000_000), default=0), need


def _cast_path():
    # The cast example's modules import each other by name.
    for d in EXAMPLES:
        if d not in sys.path:
            sys.path.append(d)


# -- the cast screen -------------------------------------------------------------


class CastScreen:
    """A second LVGL display over the cast's framebuffer, and what's on it.

    LVGL draws straight into the buffer the encoder reads (DIRECT mode); each
    finished refresh tells the cast a frame changed.
    """

    def __init__(self, scope, sink, name):
        self.scope = scope
        self.sink = sink
        self.name = name
        self.disp = lv.display_create(CAST_W, CAST_H)
        self.disp.set_color_format(lv.COLOR_FORMAT.RGB565)
        buf = sink._buf
        self.disp.set_buffers(buf, None, len(buf), lv.DISPLAY_RENDER_MODE.DIRECT)
        self.disp.set_flush_cb(self._flush)
        self.page = "home"
        self.focus = 0
        self.photos = []
        self.photo_i = 0
        self.keep = {}
        self.cam = None
        # The camera's scaler writes by DMA, which wants its buffer on a
        # 64-byte boundary; a bytearray lands where it lands. So it gets a
        # view that starts on one, a picture one row shorter (the view is
        # short by those bytes) and x moved left by the pixels skipped.
        import uctypes

        off = (-uctypes.addressof(buf)) % 64
        self.cam_fb = memoryview(buf)[off:]
        self.cam_shift = off // 2
        self.cam_h = CAST_H - 1 if off else CAST_H
        self._build()

    def _flush(self, disp, area, px):
        if disp.flush_is_last():
            self.sink.show()
        disp.flush_ready()

    def _screen(self):
        prev = lv.display_get_default()
        self.disp.set_default()
        scr = lv.obj()
        prev.set_default()
        scr.set_style_bg_color(lv.color_hex(0x0B0E14), 0)
        scr.set_style_bg_opa(lv.OPA.COVER, 0)
        scr.set_style_text_color(lv.color_hex(0xFFFFFF), 0)
        scr.set_style_text_font(ui.big, 0)
        scr.remove_flag(lv.obj.FLAG.SCROLLABLE)
        return scr

    def _label(self, parent, text, font=None, color=0xFFFFFF, scale=256):
        lbl = lv.label(parent)
        lbl.set_text(text)
        lbl.set_style_text_font(font or ui.big, 0)
        lbl.set_style_text_color(lv.color_hex(color), 0)
        if scale != 256:
            lbl.set_style_transform_scale(scale, 0)
        return lbl

    def _build(self):
        # Home: a title, the clock, and a row of tiles.
        self.home = h = self._screen()
        t = self._label(h, self.name, ui.huge, 0x26A69A)
        t.set_pos(80, 60)
        self.home_clock = self._label(h, "", ui.huge, 0xB0B8C8)
        self.home_clock.align(lv.ALIGN.TOP_RIGHT, -80, 60)
        self.tiles = []
        tw, th, gap = 250, 250, 40
        x0 = (CAST_W - (len(TILES) * tw + (len(TILES) - 1) * gap)) // 2
        for i, (text, sym, color) in enumerate(TILES):
            b = lv.obj(h)
            b.remove_style_all()
            b.set_size(tw, th)
            b.set_pos(x0 + i * (tw + gap), 230)
            b.set_style_bg_color(lv.color_hex(color), 0)
            b.set_style_bg_opa(lv.OPA.COVER, 0)
            b.set_style_radius(28, 0)
            b.set_style_border_color(lv.color_hex(0xFFFFFF), 0)
            b.remove_flag(lv.obj.FLAG.SCROLLABLE)
            icon = self._label(b, sym, ui.huge)
            icon.align(lv.ALIGN.CENTER, 0, -30)
            lbl = self._label(b, text, ui.big)
            lbl.align(lv.ALIGN.CENTER, 0, 60)
            self.tiles.append(b)
        hint = self._label(h, "Use the board's screen as the remote", ui.font, 0x7A8494)
        hint.align(lv.ALIGN.BOTTOM_MID, 0, -60)
        self._show_focus()

        # Clock: big, with the date.
        self.clock = c = self._screen()
        self.clock_time = self._label(c, "", ui.huge, 0xFFFFFF, scale=768)
        self.clock_time.align(lv.ALIGN.CENTER, 0, -60)
        self.clock_date = self._label(c, "", ui.big, 0xB0B8C8)
        self.clock_date.align(lv.ALIGN.CENTER, 0, 120)

        # Photos: one at a time, left and right to move, a new one every few seconds.
        self.photo = p = self._screen()
        self.photo_img = lv.image(p)
        self.photo_img.align(lv.ALIGN.CENTER, 0, -20)
        self.photo_cap = self._label(p, "", ui.font, 0xB0B8C8)
        self.photo_cap.align(lv.ALIGN.BOTTOM_MID, 0, -24)

        # Camera: the picture goes straight into the framebuffer, beside a caption.
        self.camera = k = self._screen()
        cap = self._label(k, lv.SYMBOL.VIDEO + "\nLive", ui.big, 0x7A8494)
        cap.set_pos(24, 40)
        self.cam_note = self._label(k, "", ui.font, 0x7A8494)
        self.cam_note.set_pos(24, CAST_H - 60)

        # About.
        self.about = a = self._screen()
        self.about_text = self._label(a, "", ui.big, 0xFFFFFF)
        self.about_text.set_pos(120, 120)

        lv.screen_load(self.home)

    # -- the remote's keys ------------------------------------------------------

    def key(self, k):
        if self.page == "home":
            if k == "left":
                self.focus = (self.focus - 1) % len(TILES)
            elif k == "right":
                self.focus = (self.focus + 1) % len(TILES)
            elif k == "ok":
                self.open(TILES[self.focus][0].lower())
                return
            self._show_focus()
            return
        if k == "back":
            self.open("home")
        elif self.page == "photos" and k in ("left", "right"):
            self.next_photo(-1 if k == "left" else 1)

    def _show_focus(self):
        for i, b in enumerate(self.tiles):
            on = i == self.focus
            b.set_style_border_width(8 if on else 0, 0)
            b.set_style_transform_scale(282 if on else 256, 0)
            b.set_style_transform_pivot_x(125, 0)
            b.set_style_transform_pivot_y(125, 0)

    def open(self, page):
        if self.page == "camera":
            self._camera_off()
        self.page = page
        scr = {"home": self.home, "clock": self.clock, "photos": self.photo, "camera": self.camera, "about": self.about}[
            page
        ]
        lv.screen_load(scr)
        if page == "photos":
            self._load_photos()
        elif page == "camera":
            self._camera_on()
        elif page == "about":
            self._about()
        self.tick()

    # -- pages ------------------------------------------------------------------

    def tick(self):
        t = time.localtime()
        hh = t[3] % 12 or 12
        now = "%d:%02d" % (hh, t[4])
        if self.page == "home":
            self.home_clock.set_text(now)
        elif self.page == "clock":
            self.clock_time.set_text(now)
            days = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
            months = ("January", "February", "March", "April", "May", "June", "July",
                      "August", "September", "October", "November", "December")  # fmt: skip
            self.clock_date.set_text(
                "%s    %s, %s %d" % ("AM" if t[3] < 12 else "PM", days[t[6]], months[t[1] - 1], t[2])
            )
        elif self.page == "camera" and self.cam is not None:
            dt = ticks_diff(ticks_ms(), self.cam_t0) or 1
            self.cam_note.set_text("%.0f fps" % (self.cam_frames * 1000 / dt))
            self.cam_frames = 0
            self.cam_t0 = ticks_ms()

    def _load_photos(self):
        self.photos = [p for k, p in cam.photos(self.scope)]
        self.photo_i = 0
        self.next_photo(0)

    def next_photo(self, step):
        if not self.photos:
            self.photo_cap.set_text("No photos yet: take some with the Camera app.")
            return
        self.photo_i = (self.photo_i + step) % len(self.photos)
        path = self.photos[self.photo_i]
        try:
            with open(path, "rb") as f:
                data = f.read()
            px, w, h = ui.decode_jpeg(data, CAST_W - 80, CAST_H - 100)
        except Exception as e:
            self.photo_cap.set_text("%s: %s" % (path, e))
            return
        ui.rgb565_image(self.photo_img, px, w, h, self.keep)
        self.photo_img.align(lv.ALIGN.CENTER, 0, -20)
        self.photo_cap.set_text(
            "%s   %d of %d   " % (path.rsplit("/", 1)[1], self.photo_i + 1, len(self.photos))
            + lv.SYMBOL.LEFT
            + " "
            + lv.SYMBOL.RIGHT
        )

    def _about(self):
        name = net.hostname()
        st = self.sink.stats()
        self.about_text.set_text(
            "ESP32-P4 WIFI6 DEV-KIT\n%s %s\n\nOn the network as %s (%s)\n"
            "Streaming %d x %d at about %d frames a second"
            % (
                sys.implementation.name,
                ".".join(str(v) for v in sys.implementation.version[:3]),
                (name + ".local") if name else "?",
                net.ip() or "no Wi-Fi",
                CAST_W,
                CAST_H,
                st.get("fps", 0),
            )
        )

    def _camera_on(self):
        opts = cam.options(self.scope)
        try:
            self.cam = cam.open_camera(opts)
            cam.apply_controls(self.cam, opts)
        except Exception as e:
            self.cam = None
            self.cam_note.set_text("no camera: %s" % (e,))
            return
        cw, ch = self.cam.size()[:2]
        w = self.cam_h * cw // ch
        self.cam_box = (CAST_W - w - self.cam_shift, 0, w, self.cam_h)
        self.cam_frames = 0
        self.cam_t0 = ticks_ms()
        self.scope.foreground(self._camera_loop)

    def _camera_loop(self):
        c = self.cam
        if c is None:
            return
        x, y, w, h = self.cam_box
        try:
            if c.capture_scaled(self.cam_fb, CAST_W, self.cam_h, x=x, y=y, w=w, h=h, timeout=200) is not None:
                self.sink.show()
                self.cam_frames += 1
        except Exception as e:
            self._camera_off()
            self.cam_note.set_text("camera: %s" % (e,))
            return
        sleep_ms(5)

    def _camera_off(self):
        self.scope.foreground(None)
        c, self.cam = self.cam, None
        if c is not None:
            c.deinit()

    def close(self):
        self._camera_off()
        try:
            self.disp.delete()  # and its screens
        except Exception as e:
            print("cast: display delete:", e)


# -- the panel: the remote ----------------------------------------------------------


def main(scope):
    global state
    try:
        import castif  # noqa: F401
    except ImportError as e:
        # The sender is the board's H.264 encoder and Miracast task. Nothing
        # is scanned for here: a computer has no stream to send.
        ui.missing(
            scope,
            "missing: castif",
            "Cast needs castif, the board's H.264 encoder and Miracast sender, which this computer lacks: %s." % (e,),
        )
        return
    from . import receivers

    conf = settings.config(scope, DEFAULTS)
    folder = scope.data_dir
    root = scope.root
    W, H = scope.size
    status = ui.status(scope)
    st = state = {"targets": [], "sink": None, "screen": None, "busy": False, "looking": False}
    kept = scope.store()  # the receiver last cast to, while the board stays up
    w = scope.worker

    rx = W // 2 + 16
    rw = W - rx - 24
    dd = lv.dropdown(root)
    dd.set_width(rw)
    dd.set_pos(rx, 12)
    dd.set_options("looking for receivers...")
    go_b, go_l = ui.button(root, lv.SYMBOL.PLAY + "  Cast", lambda: toggle(), w=rw, h=72, font=ui.big, color=ui.ACCENT)
    go_b.set_pos(rx, 80)
    msg = ui.label(root, "", ui.font, ui.WHITE)
    msg.set_pos(rx, 170)
    msg.set_width(rw)
    info = ui.label(root, "", ui.small, ui.MUTED)
    info.set_pos(rx, 330)
    info.set_width(rw)

    # The d-pad, OK in the middle, Back below.
    def key(k):
        screen = st["screen"]
        if screen is None:
            msg.set_text("Cast first, then the remote drives the cast screen.")
            return
        screen.key(k)

    cx, cy = W // 4, 270

    def pad(text, k, x, y, bw=120, bh=96, color=None):
        b, _ = ui.button(root, text, lambda: key(k), w=bw, h=bh, font=ui.huge if len(text) < 3 else ui.big, color=color)
        b.set_pos(x, y)

    pad(lv.SYMBOL.UP, "up", cx - 60, cy - 216)
    pad(lv.SYMBOL.LEFT, "left", cx - 60 - 136, cy - 108)
    pad("OK", "ok", cx - 60, cy - 108, color=ui.WARN)
    pad(lv.SYMBOL.RIGHT, "right", cx - 60 + 136, cy - 108)
    pad(lv.SYMBOL.DOWN, "down", cx - 60, cy)
    pad(lv.SYMBOL.LEFT + "  Back", "back", cx - 60 - 136, cy + 120, bw=392, bh=72)

    def show_targets():
        t = st["targets"] + [HLS]
        keep = dd.get_selected() if st.get("shown") else None
        shown = st.get("shown") or []
        picked = shown[keep]["host"] if keep is not None and keep < len(shown) else kept.get("host")
        st["shown"] = t
        dd.set_options("\n".join(r["name"] for r in t))
        for i, r in enumerate(t):
            if r["host"] == picked:
                dd.set_selected(i)
                return
        prefer = conf.get("prefer")
        if prefer:
            for i, r in enumerate(t):
                if prefer in r["name"]:
                    dd.set_selected(i)
                    return

    def add(found):
        # New ones join the list; one found again by a quicker route keeps
        # its place, but takes a better name (an address gives way to a name).
        have = {r["host"]: r for r in st["targets"]}
        for r in found:
            old = have.get(r["host"])
            if old is None:
                st["targets"].append(r)
                have[r["host"]] = r
            elif old["name"].endswith(" at " + old["host"]) and not r["name"].endswith(" at " + r["host"]):
                old["name"] = r["name"]
        show_targets()

    def say_found(more):
        n = len(st["targets"])
        msg.set_text(
            "%d receiver%s found%s"
            % (n, "" if n == 1 else "s", "; still looking for computers..." if more else ". Pick one and press Cast.")
        )

    def look():
        if st["looking"]:
            return
        st["looking"] = True
        add(receivers.remembered(folder))
        msg.set_text("Looking for receivers...")
        rest = []

        def swept(value, error):
            if error is None:
                add(value)
            if rest:
                part = rest[:36]
                del rest[:36]
                w.submit(lambda: receivers.sweep(part), swept, key="sweep")
                say_found(True)
            else:
                st["looking"] = False
                say_found(False)

        def heard(value, error):
            if error is None:
                add(value)
            else:
                print("cast: mDNS:", error)
            rest.extend(receivers.subnet_hosts(skip=[r["host"] for r in st["targets"]]))
            swept([], None)

        w.submit(receivers.announced, heard, key="announced")

    def start():
        _cast_path()
        r = st["shown"][dd.get_selected()]
        kept["host"] = r["host"]
        have, need = _encoder_room()
        if have < need:
            msg.set_text(
                "The video encoder needs %d KB of the chip's internal memory in one piece, "
                "and the biggest free piece is %d KB. Restart the board, then cast." % (need // 1024, have // 1024)
            )
            return
        st["busy"] = True
        try:
            if r["kind"] == "hls":
                from hls_display import HlsDisplay

                sink = HlsDisplay(tv=None, width=CAST_W, height=CAST_H, fps=FPS, bitrate=BITRATE, log=print)
                msg.set_text("Open this in VLC (Media > Open Network Stream):\n" + sink.url)
            else:
                from cast_display import CastDisplay

                receivers.remember(folder, r)  # now: no flash writes once the stream runs
                if r["kind"] == "roku":
                    try:
                        ecp.keypress(r["host"], "PowerOn")  # wakes one in standby; one that's on ignores it
                    except OSError:
                        pass
                sink = CastDisplay(
                    r["host"], CAST_W, CAST_H, kind=r["kind"], fps=FPS, bitrate=BITRATE, name=conf["name"], log=print
                )
                msg.set_text("Casting to %s. It may ask once to allow it." % r["name"])
        except Exception as e:
            st["busy"] = False
            msg.set_text("couldn't start: %s" % (e,))
            return
        st["sink"] = sink
        st["screen"] = CastScreen(scope, sink, conf["name"])
        go_l.set_text(lv.SYMBOL.STOP + "  Stop")
        go_b.set_style_bg_color(ui.BAD, 0)
        st["busy"] = False

    def stop():
        screen, st["screen"] = st["screen"], None
        sink, st["sink"] = st["sink"], None
        if screen is not None:
            screen.close()
        if sink is not None:
            try:
                sink.close()
            except Exception as e:
                print("cast: close:", e)
        go_l.set_text(lv.SYMBOL.PLAY + "  Cast")
        go_b.set_style_bg_color(ui.ACCENT, 0)
        msg.set_text("Stopped.")
        info.set_text("")

    def toggle():
        if st["busy"]:
            return
        if st["sink"] is not None:
            stop()
        elif st.get("shown"):
            start()
        else:
            look()

    def tick(t=None):
        screen, sink = st["screen"], st["sink"]
        if screen is not None:
            screen.tick()
            if screen.page == "photos" and ticks_diff(ticks_ms(), st.get("flip", 0)) > 0:
                st["flip"] = ticks_add(ticks_ms(), 8000)
                screen.next_photo(1)
        if sink is not None:
            try:
                s = sink.stats()
                info.set_text(
                    "%.0f frames a second, %s"
                    % (
                        s.get("fps", 0),
                        ("%d sessions, %d keyframes asked for" % (s.get("sessions", 0), s.get("idr_requests", 0)))
                        if "sessions" in s
                        else "serving HLS",
                    )
                )
            except Exception:
                pass

    def close():
        if st["sink"] is not None:
            stop()

    st["toggle"], st["key"], st["pick"] = toggle, key, dd.set_selected  # for the console
    scope.on_close(close)
    scope.every(1000, tick)

    def setup(t):
        # Look for receivers once Wi-Fi is up (it may still be joining after a boot).
        if not net.up():
            msg.set_text("Waiting for Wi-Fi (set it up in System if it never comes).")
            return
        if t is not None:
            t.deinit()
        rssi = net.rssi()
        status.set_text("Wi-Fi %s dBm" % rssi if rssi else "Wi-Fi up")
        look()

    if net.up():
        setup(None)
    else:
        scope.every(500, setup)
