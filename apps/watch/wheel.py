# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Watch's wheel: every app on an arc, the one in the middle large.

A column of discs, one an app in its colour with its icon, scrolls up and
down and snaps an app to the middle. As it scrolls, each disc slides along
an arc that follows a round screen's edge and fades the further it is from
the middle; the middle one grows, with its name and tab beside it. A tap on
the middle app opens it, a tap on another brings it to the middle. Keys do
the same: up and down (or left and right) turn the wheel, Enter opens.
"""

import math

import lvgl as lv
from icons import lvgl as lvicons

from touchkit import ui

ICON = 32  # the middle disc's icon; the others draw it smaller


def arc(r, dy):
    """How far in from the edge a disc *dy* pixels from the middle sits, on
    a circle of radius *r*."""
    dy = min(r, dy)
    return r - int(math.sqrt(r * r - dy * dy))


class Wheel:
    """The wheel on *parent*, *w* by *h*. *apps* is ``[(name, title,
    category, icon, colour), ...]`` in order; *on_open* is called with the
    name of the app to open. *at* is the app that starts in the middle."""

    def __init__(self, parent, w, h, apps, on_open, at=0):
        self.apps = apps
        self.on_open = on_open
        self.selected = -1
        self.on_select = None  # called with the index of the app that comes to the middle
        slot = max(40, h // 4)
        self.slot = slot
        self.big = slot - 4
        self.small = slot * 3 // 5
        self.r = h // 2  # the arc's radius: the screen's own on a round one
        self.col = w * 3 // 10  # the discs' centre line, left of the middle
        cont = lv.obj(parent)
        cont.remove_style_all()
        cont.set_size(w, h)
        cont.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        cont.set_style_pad_top((h - slot) // 2, 0)
        cont.set_style_pad_bottom((h - slot) // 2, 0)
        cont.set_scroll_dir(lv.DIR.VER)
        cont.set_scroll_snap_y(lv.SCROLL_SNAP.CENTER)
        cont.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
        cont.add_event_cb(lambda e: self._arrange(), lv.EVENT.SCROLL, None)
        cont.add_event_cb(lambda e: self._arrange(), lv.EVENT.SCROLL_END, None)
        cont.add_event_cb(self._key, lv.EVENT.KEY, None)
        self.cont = cont
        self.items = []
        self.discs = []
        self.icons = []
        for i, (name, title, category, icon, color) in enumerate(apps):
            item = lv.obj(cont)
            item.remove_style_all()
            item.set_size(w, slot)
            item.remove_flag(lv.obj.FLAG.SCROLLABLE)
            item.add_flag(lv.obj.FLAG.CLICKABLE)
            item.add_flag(lv.obj.FLAG.GESTURE_BUBBLE)
            disc = lv.obj(item)
            disc.remove_style_all()
            disc.remove_flag(lv.obj.FLAG.CLICKABLE)
            disc.set_style_radius(lv.RADIUS_CIRCLE, 0)
            disc.set_style_bg_color(lv.color_hex(color), 0)
            disc.set_style_bg_opa(lv.OPA.COVER, 0)
            img = lvicons.image(disc, icon, ICON, ui.WHITE)
            img.center()
            item.add_event_cb((lambda i: lambda e: self._tapped(i))(i), lv.EVENT.CLICKED, None)
            self.items.append(item)
            self.discs.append(disc)
            self.icons.append(img)
        # The middle app's tab and name, right of its disc.
        x = self.col + self.big // 2 + 10
        self.tab = ui.label(parent, "", ui.tiny, ui.MUTED)
        self.name = ui.label(parent, "", ui.font, ui.WHITE)
        for lbl in (self.tab, self.name):
            lbl.set_width(max(40, w - x - 12))
            lbl.set_long_mode(lv.label.LONG_MODE.DOTS)
            lbl.remove_flag(lv.obj.FLAG.CLICKABLE)
        self.name.set_height(2 * ui.font.line_height)
        self.tab.set_pos(x, h // 2 - ui.font.line_height // 2 - ui.tiny.line_height - 2)
        self.name.set_pos(x, h // 2 - ui.font.line_height // 2)
        cont.update_layout()
        if apps:
            self.show(at, False)
        self._arrange()

    def middle(self):
        """The index of the app nearest the middle, or -1 with none."""
        a = lv.area_t()
        self.cont.get_coords(a)
        cy = (a.y1 + a.y2) // 2
        best, best_d = -1, 1 << 30
        for i, item in enumerate(self.items):
            item.get_coords(a)
            d = abs((a.y1 + a.y2) // 2 - cy)
            if d < best_d:
                best, best_d = i, d
        return best

    def _arrange(self):
        a = lv.area_t()
        self.cont.get_coords(a)
        cy = (a.y1 + a.y2) // 2
        r = self.r
        best = self.middle()
        for i, item in enumerate(self.items):
            item.get_coords(a)
            dy = min(r, abs((a.y1 + a.y2) // 2 - cy))
            x = arc(r, dy)
            d = self.big if i == best else self.small
            disc = self.discs[i]
            disc.set_size(d, d)
            disc.set_pos(self.col - d // 2 + x, (self.slot - d) // 2)
            self.icons[i].set_scale(256 if i == best else 256 * (self.small * 3 // 5) // ICON)
            disc.set_style_opa(255 - 200 * dy // r, 0)
        if best != self.selected:
            self.selected = best
            if best >= 0:
                name, title, category, icon, color = self.apps[best]
                self.name.set_text(title)
                self.tab.set_text(category)
            if self.on_select is not None:
                self.on_select(best)

    def show(self, i, anim=True):
        """Bring app *i* (from 0) to the middle."""
        if not self.items:
            return
        i = max(0, min(i, len(self.items) - 1))
        self.items[i].scroll_to_view(bool(anim))
        self._arrange()

    def _tapped(self, i):
        if i == self.selected:
            self.on_open(self.apps[i][0])
        else:
            self.show(i)

    def _key(self, e):
        key = e.get_key()
        if key in (lv.KEY.UP, lv.KEY.LEFT, lv.KEY.PREV):
            self.show(self.selected - 1)
        elif key in (lv.KEY.DOWN, lv.KEY.RIGHT, lv.KEY.NEXT):
            self.show(self.selected + 1)
        elif key == lv.KEY.ENTER and self.selected >= 0:
            self.on_open(self.apps[self.selected][0])
