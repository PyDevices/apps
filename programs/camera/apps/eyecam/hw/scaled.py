# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""A 240x240 LVGL display that the PPA enlarges onto a bigger panel.

LVGL's own transform of a whole page costs 250 ms a frame at 2x on a P4, so
the pages are drawn at 240x240 on a display of their own, and each area LVGL
finishes is scaled by a whole number straight into the panel's framebuffer,
centred, by the PPA. The panel's own display keeps its screen (and whatever
the launcher's shell draws over it) outside the enlarged picture.
"""

import lvgl as lv
import ppa
import time
import uctypes

BASE = 240
HOME_ZONE = 110  # panel pixels: a press held in the top-left corner goes Home
HOME_HOLD_MS = 800


class ScaledDisplay:
    """*panel* is the board's displaydev driver; *scale* the whole-number
    enlargement; *lock* the lock every PPA user takes (or None);
    *on_home* is called when a press is held in the top-left corner (the
    launcher's own Home button is under the enlarged picture on a panel the
    picture fills)."""

    def __init__(self, panel, scale, lock=None, on_home=None):
        self.panel = panel
        self.on_home = on_home
        self._raw_pos = (0, 0)
        self._home_t = None
        self.scale = scale
        self.lock = lock
        fb = panel.framebuffers()
        self.fb = fb[0]
        self.W, self.H = int(panel.width), int(panel.height)
        self.ox = (self.W - BASE * scale) // 2
        self.oy = (self.H - BASE * scale) // 2
        raw = bytearray(BASE * BASE * 2 + 64)
        self._raw = raw
        off = (-uctypes.addressof(raw)) % 64
        self.buf = memoryview(raw)[off:off + BASE * BASE * 2]
        self.main = lv.display_get_default()
        self.disp = lv.display_create(BASE, BASE)
        self.disp.set_color_format(lv.COLOR_FORMAT.RGB565)
        self.disp.set_buffers(self.buf, None, len(self.buf), lv.DISPLAY_RENDER_MODE.DIRECT)
        self.disp.set_flush_cb(self._flush)
        # The panel's own display keeps whatever it was showing (the launcher's
        # page) round the picture; a black screen of its own is quieter.
        self._behind = self.main.get_screen_active() if self.main is not None else None
        self._black = None
        if self.main is not None:
            self._black = lv.obj(None)
            self._black.set_style_bg_color(lv.color_hex(0x000000), 0)
            self._black.set_style_bg_opa(255, 0)
            lv.screen_load(self._black)
        self.disp.set_default()
        self._down = False
        self._pos = (0, 0)
        self.indev = lv.indev_create()
        self.indev.set_type(lv.INDEV_TYPE.POINTER)
        self.indev.set_display(self.disp)
        self.indev.set_read_cb(self._read)

    def _flush(self, disp, area, px):
        x, y = area.x1, area.y1
        w, h = area.x2 - x + 1, area.y2 - y + 1
        s = self.scale
        dx, dy, dw, dh = self.ox + x * s, self.oy + y * s, w * s, h * s
        try:
            if self.lock is not None:
                self.lock.acquire()
            try:
                ppa.srm(self.buf, BASE, BASE, self.fb, self.W, self.H, src_rect=(x, y, w, h),
                        x=dx, y=dy, w=dw, h=dh, hardware=True)
            finally:
                if self.lock is not None:
                    self.lock.release()
            # No cache sync: the PPA writes the framebuffer by DMA, and the
            # panel's flush_rect on the area costs 16 ms a frame at 2x.
        finally:
            disp.flush_ready()

    # Touch arrives as the app's pointer events, in the panel's pixels.
    def pointer(self, e, *_):  # LVGL's read path adds (indev, data)
        import events

        if e.type == events.MOUSEBUTTONDOWN and e.button == 1:
            self._down = True
            self._home_t = time.ticks_ms() if e.pos[0] < HOME_ZONE and e.pos[1] < HOME_ZONE else None
        elif e.type == events.MOUSEBUTTONUP and e.button == 1:
            self._down = False
            self._home_t = None
        elif e.type != events.MOUSEMOTION:
            return
        elif self._home_t is not None and (e.pos[0] >= HOME_ZONE or e.pos[1] >= HOME_ZONE):
            self._home_t = None  # slid out of the corner: not a Home press
        x, y = e.pos
        x, y = (x - self.ox) // self.scale, (y - self.oy) // self.scale
        self._pos = (max(0, min(BASE - 1, x)), max(0, min(BASE - 1, y)))

    def _read(self, indev, data):
        t = self._home_t
        if t is not None and self.on_home is not None and time.ticks_diff(time.ticks_ms(), t) >= HOME_HOLD_MS:
            self._home_t = None
            self._down = False  # the press is spent: the app sees it lift
            self.on_home()
        data.point = lv.point_t({"x": self._pos[0], "y": self._pos[1]})
        data.state = lv.INDEV_STATE.PRESSED if self._down else lv.INDEV_STATE.RELEASED

    def close(self):
        """Give the panel's display back as the default now, and drop this
        one a moment later: the app's own screens are still being deleted."""
        import multimer

        if self.main is not None:
            self.main.set_default()
            if self._behind is not None:
                try:
                    lv.screen_load(self._behind)
                except Exception:
                    pass
        black = self._black
        disp, indev = self.disp, self.indev
        self.disp = self.indev = self.buf = self.fb = self._black = None

        def drop(_t):
            for obj in (indev, black, disp):
                try:
                    obj.delete()
                except Exception:
                    pass

        multimer.after(100, drop)
