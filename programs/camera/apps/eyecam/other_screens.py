# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""The Album and USB screens."""

import lvgl as lv
import ppa

from . import assets
from .widgets import CENTER, FOCUSED, bar, hide, image, label, panel, pin_to_panel, rgb565_dsc, show, visible

try:
    import jpegio
except ImportError:
    jpegio = None

# The square the album crops from the middle of a photo, by photo width.
ALBUM_CROP = {1920: 960, 1280: 640, 640: 480}
OD_MIN_SCORE = 0.30


class AlbumScreen:
    def __init__(self, screen, storage, detector):
        self.screen = screen
        self.storage = storage
        self.detector = detector
        self.od = True
        self.paths = []
        self.index = 0
        self.buf = bytearray(240 * 240 * 2)  # starts black, as the factory's canvas buffer does
        self.photo = lv.image(screen)
        self._dsc = rgb565_dsc(self.buf, 240, 240)
        self.photo.set_src(self._dsc)
        self.photo.align(CENTER, 0, 0)

        self.boxes = lv.obj(screen)
        self.boxes.remove_style_all()
        self.boxes.set_size(240, 240)
        self.boxes.remove_flag(lv.obj.FLAG.SCROLLABLE)

        self.counter = lv.label(screen)
        self.counter.set_style_text_font(assets.font("semi24"), 0)
        self.counter.set_style_text_color(lv.color_hex(0xFFFFFF), 0)
        self.counter.set_style_bg_color(lv.color_hex(0x000000), 0)
        self.counter.set_style_bg_opa(127, 0)
        self.counter.set_style_radius(5, 0)
        self.counter.set_style_pad_all(5, 0)
        self.counter.align(lv.ALIGN.TOP_RIGHT, -10, 10)
        self.counter.add_flag(lv.obj.FLAG.HIDDEN)

        self.empty = lv.obj(screen)
        self.empty.remove_style_all()
        self.empty.set_size(240, 240)
        self.empty.set_style_bg_color(lv.color_hex(0xFFFFFF), 0)
        self.empty.set_style_bg_opa(255, 0)
        nd = lv.label(self.empty)
        nd.set_text("No data found")
        nd.set_width(200)
        nd.set_style_text_font(assets.font("semi24"), 0)
        nd.set_style_text_color(lv.color_hex(0x000000), 0)
        nd.set_pos(30, 108)
        self.empty.add_flag(lv.obj.FLAG.HIDDEN)

        self.hints = (
            (image(screen, "button_menu", 100, -47, hidden=False), 100, -47),
            (image(screen, "up_button", 100, 0, hidden=False), 100, 0),
            (image(screen, "button_down", 100, 55, hidden=False), 100, 55),
        )

        d = panel(screen, 181, 185, -13, 4, opa=100)
        d.set_style_bg_color(lv.color_hex(0xC9C9C9), FOCUSED)
        d.set_style_bg_opa(120, FOCUSED)
        label(d, "Delete?", 2, -43, "bold28")
        self.yes = self._button(d, -1, "YES", 0xFF0202)
        self.no = self._button(d, 42, "NO", 0x000000)
        self.dialog = d

        w = panel(screen, 212, 212, -15, 0)
        label(w, "Warning", -4, -70, "bold28", 0xFF0000)
        bar(w, 197, -1, -36)
        label(w, "No SDCard detected\n\n  Insert SDCard to \n          continue", 3, 39, "semi22")
        self.sd_warning = w


    def pin_hints(self, turn):
        """The key hints stay beside the switches when the panel turns."""
        pin_to_panel(self.hints, turn)
    def _button(self, parent, y, text, color):
        b = lv.button(parent)
        b.set_size(140, 30)
        b.align(CENTER, -2, y)
        b.set_style_bg_color(lv.color_hex(0xFFFFFF), 0)
        b.set_style_bg_opa(0, 0)
        b.set_style_bg_color(lv.color_hex(0xFFFFFF), FOCUSED)
        b.set_style_bg_opa(150, FOCUSED)
        lb = lv.label(b)
        lb.set_text(text)
        lb.align(CENTER, 0, 2)
        lb.set_style_text_color(lv.color_hex(color), 0)
        return b

    # -- the factory's app_album ------------------------------------------

    def refresh(self):
        """Read the card again and show the newest photo."""
        self.paths = self.storage.photos()
        self.index = 0
        self.show_current()

    def show_current(self):
        self.boxes.clean()
        if not self.paths:
            hide(self.counter)
            if self.storage.mounted():
                show(self.empty)
            else:
                hide(self.empty)
            return
        hide(self.empty)
        while self.paths:
            if self._load(self.paths[self.index]):
                break
            del self.paths[self.index]  # unreadable: the factory skips it too
            if self.index >= len(self.paths):
                self.index = 0
        if not self.paths:
            self.show_current()
            return
        self.counter.set_text("%d/%d" % (self.index + 1, len(self.paths)))
        show(self.counter)
        if self.od:
            for x0, y0, x1, y1, name, score in self.detector.objects(self.buf, 240, 240):
                if score > OD_MIN_SCORE:
                    self._box(x0, y0, x1, y1, name)
        self.photo.invalidate()

    def _load(self, path):
        if jpegio is None:
            return False
        try:
            dec = jpegio.JpegDecoder()
            w, h = dec.open(path)
            side = ALBUM_CROP.get(w)
            if side is None:
                return False
            sw, sh, side = w >> 1, h >> 1, side >> 1
            tmp = bytearray(sw * sh * 2)
            dec.decode(tmp, 1)
            ppa.srm(tmp, sw, sh, self.buf, 240, 240, src_rect=((sw - side) // 2, (sh - side) // 2, side, side))
            return True
        except (OSError, ValueError, RuntimeError):
            return False

    def _box(self, x0, y0, x1, y1, name):
        b = lv.obj(self.boxes)
        b.remove_style_all()
        b.set_pos(x0, y0)
        b.set_size(x1 - x0, y1 - y0)
        b.set_style_border_color(lv.color_hex(0xFF0000), 0)
        b.set_style_border_width(5, 0)
        b.set_style_border_opa(255, 0)
        lb = lv.label(self.boxes)
        lb.set_text(name)
        lb.set_style_text_color(lv.color_hex(0xFFFF00), 0)
        lb.set_pos(x0 + 5, y0 + 15)

    def prev(self):
        if self.paths:
            self.index = (self.index + len(self.paths) - 1) % len(self.paths)
            self.show_current()

    def next(self):
        if self.paths:
            self.index = (self.index + 1) % len(self.paths)
            self.show_current()

    def delete_current(self):
        if not self.paths:
            return
        try:
            self.storage.remove(self.paths[self.index])
        except OSError:
            pass
        del self.paths[self.index]
        if self.index >= len(self.paths):
            self.index = 0
        self.show_current()

    def toggle_choice(self):
        """The factory's ``ui_extra_focus_on_picture_delete``."""
        if self.yes.has_state(lv.STATE.FOCUSED):
            self.no.add_state(lv.STATE.FOCUSED)
            self.yes.remove_state(lv.STATE.FOCUSED)
        else:
            self.no.remove_state(lv.STATE.FOCUSED)
            self.yes.add_state(lv.STATE.FOCUSED)

    def dialog_open(self):
        return visible(self.dialog)


class UsbScreen:
    def __init__(self, screen):
        self.screen = screen
        self.page1 = image(screen, "usb_page1", hidden=False)
        self.page2 = image(screen, "usb_page2")
        self.warning = image(screen, "usb_page_warning")
        self.no_sd = image(screen, "sdcard_no", -102, -101)
