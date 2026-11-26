# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""The main menu: seven icons on a wheel, a port of the factory's
``lv_scroll_create`` and its two scroll callbacks.

A round-clipped column scrolls vertically and snaps to its centre. On each
scroll every item slides left along an arc of radius 7/10 of the height and
goes back to the base size; the one nearest the centre grows 2.3 times and
its icon to zoom 144, shifted 80 px left. When a scroll ends the name label
moves to that item's own offset.
"""

import math

import lvgl as lv

from . import assets

NAMES = ("CAMERA", "INTERVAL CAM", "VIDEO MODE", "AI DETECT", "ALBUM", "USB DISK", "SETTINGS")
ICONS = ("camera_big", "interval_big", "video_big", "ai_detect", "album_big", "usb_big", "settings_big")
BASE_ZOOM = 60
BTN_ZOOM = 2.3
IMG_ZOOM = 2.4
IMG_OFFSET = -80
LABEL_AT = {
    "CAMERA": (-9, 50),
    "INTERVAL CAM": (-12, 45),
    "VIDEO MODE": (-9, 45),
    "ALBUM": (-9, 55),
    "USB DISK": (-7, 60),
    "SETTINGS": (-9, 60),
}  # AI DETECT keeps wherever the label was


class Wheel:
    def __init__(self, canvas):
        cont = lv.obj(canvas)
        cont.set_size(240, 240)
        cont.align(lv.ALIGN.CENTER, -65, 0)
        cont.set_style_pad_row(10, 0)
        cont.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        cont.set_style_radius(lv.RADIUS_CIRCLE, 0)
        cont.set_style_clip_corner(True, 0)
        cont.set_scroll_dir(lv.DIR.VER)
        cont.set_scroll_snap_y(lv.SCROLL_SNAP.CENTER)
        cont.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
        cont.add_event_cb(self._on_scroll, lv.EVENT.SCROLL, None)
        cont.add_event_cb(self._on_scroll_end, lv.EVENT.SCROLL_END, None)
        cont.set_style_bg_opa(0, 0)
        cont.set_style_border_opa(0, 0)
        self.cont = cont
        self.scrolling = False

        info = lv.label(canvas)
        info.set_style_text_font(assets.montserrat(16), 0)
        info.set_style_text_color(lv.color_hex(0x000000), 0)
        info.align(lv.ALIGN.CENTER, 3, 50)
        info.set_text("")
        self.info = info

        self.items = []
        self.icons = []
        for icon in ICONS:
            b = lv.obj(cont)  # the factory's lv_btn, styled clear; a plain obj stays out of the key group
            b.set_style_bg_opa(0, 0)
            b.set_style_border_opa(0, 0)
            b.set_style_border_width(0, 0)
            b.set_style_shadow_width(0, 0)
            b.remove_flag(lv.obj.FLAG.SCROLLABLE)
            b.set_width(lv.pct(100))
            b.set_height(30)
            im = lv.image(b)
            im.set_src(assets.image(icon))
            im.align(lv.ALIGN.CENTER, 0, 0)
            im.set_scale(BASE_ZOOM)
            im.add_flag(lv.obj.FLAG.FLOATING)
            self.items.append(b)
            self.icons.append(im)
        cont.update_layout()
        self.btn_w = self.items[-1].get_width()
        self.btn_h = self.items[-1].get_height()
        self.selected = 0

        cont.send_event(lv.EVENT.SCROLL, None)
        self.items[0].scroll_to_view(False)
        info.set_text(NAMES[0])
        self.scrolling = False

    def _closest(self):
        a = lv.area_t()
        self.cont.get_coords(a)
        cy = a.y1 + (a.y2 - a.y1 + 1) // 2
        best, best_d, dys = 0, 1 << 30, []
        for i, b in enumerate(self.items):
            b.get_coords(a)
            d = abs(a.y1 + (a.y2 - a.y1 + 1) // 2 - cy)
            dys.append(d)
            if d < best_d:
                best, best_d = i, d
        return best, dys

    def _grow(self, i):
        self.items[i].set_size(int(self.btn_w * BTN_ZOOM), int(self.btn_h * BTN_ZOOM))
        im = self.icons[i]
        im.set_scale(int(BASE_ZOOM * IMG_ZOOM))
        im.set_pos(IMG_OFFSET, 0)

    def _reset(self, i):
        self.items[i].set_size(self.btn_w, self.btn_h)
        im = self.icons[i]
        im.set_scale(BASE_ZOOM)
        im.align(lv.ALIGN.CENTER, 0, 0)

    def _on_scroll(self, e):
        self.scrolling = True
        r = self.cont.get_height() * 7 // 10
        best, dys = self._closest()
        for i, b in enumerate(self.items):
            dy = dys[i]
            x = r if dy >= r else int(math.sqrt(r * r - dy * dy)) - r
            b.set_style_translate_x(x, 0)
            mapped = 255 if x >= r else (0 if x <= 0 else 255 * x // r)  # lv_map(x, 0, r, 0, 255)
            b.set_style_opa(255 - mapped, 0)
            self._reset(i)
        self._grow(best)

    def _on_scroll_end(self, e):
        best, _ = self._closest()
        self.selected = best
        name = NAMES[best]
        self.info.set_text(name)
        if self.on_main():
            self.info.remove_flag(lv.obj.FLAG.HIDDEN)
        if name in LABEL_AT:
            self.info.align(lv.ALIGN.CENTER, *LABEL_AT[name])
        for i in range(len(self.items)):
            self._reset(i)
        self._grow(best)
        self.items[best].scroll_to_view(True)
        self.scrolling = False

    def on_main(self):
        return True  # replaced by the controller

    def step(self, dy):
        """Up (+40) or down (-40), as the factory's buttons scroll it."""
        self.cont.scroll_by(0, dy, True)
        self.cont.send_event(lv.EVENT.SCROLL, None)
        self.info.add_flag(lv.obj.FLAG.HIDDEN)

    def chosen(self):
        return NAMES[self.selected]
