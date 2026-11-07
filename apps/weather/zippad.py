# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""A keypad for a ZIP code, sized so every key sits inside a round screen."""

import lvgl as lv
from deskkit import forecast

# The ZIP code's digits: 40 px, or the largest a firmware without it has.
_DIGITS = getattr(lv, "font_montserrat_40", None) or getattr(lv, "font_montserrat_32", lv.font_montserrat_24)

_LENGTH = 5
_BG = 0x0A1020
_KEY = 0x24344A
_GO = 0x2F7D4F
_WHITE = 0xFFFFFF
_SOFT = 0xB9C6D4
_BAD = 0xFF8A7A
_GRID = (("1", "2", "3"), ("4", "5", "6"), ("7", "8", "9"), ("del", "0", "ok"))


class ZipPad:
    """Ask for a ZIP code, look it up, and call *done* with the place saved.

    Args:
        scope (AppScope): The app it belongs to.
        width (int): The screen's width.
        height (int): The screen's height.
        done (callable): Called with no arguments once there's a place, or when
            you back out of changing one you already have.
    """

    def __init__(self, scope, width, height, done):
        self.scope = scope
        self.done = done
        self.digits = ""
        self.busy = False

        self.panel = panel = lv.obj(scope.root)
        panel.remove_flag(lv.obj.FLAG.SCROLLABLE)
        panel.set_size(width, height)
        panel.set_style_pad_all(0, 0)
        panel.set_style_border_width(0, 0)
        panel.set_style_radius(0, 0)
        panel.set_style_bg_color(lv.color_hex(_BG), 0)

        key_w = width * 20 // 100
        key_h = height * 13 // 100
        gap = height * 2 // 100
        grid_top = height * 29 // 100

        self.title = lv.label(panel)
        self.title.set_style_text_font(lv.font_montserrat_16, 0)
        self.title.set_style_text_color(lv.color_hex(_SOFT), 0)
        self.title.align(lv.ALIGN.TOP_MID, 0, height * 8 // 100)

        self.shown = lv.label(panel)
        self.shown.set_style_text_font(_DIGITS, 0)
        self.shown.set_style_text_color(lv.color_hex(_WHITE), 0)
        self.shown.align(lv.ALIGN.TOP_MID, 0, height * 13 // 100)

        place = forecast.place()
        if place is not None:
            self.units = lv.button(panel)
            self.units.set_size(width * 16 // 100, height * 8 // 100)
            self.units.align(lv.ALIGN.TOP_RIGHT, -width * 14 // 100, height * 14 // 100)
            self.units.set_style_bg_color(lv.color_hex(_KEY), 0)
            self.units.add_event_cb(self._toggle_units, lv.EVENT.CLICKED, None)
            self.units_label = lv.label(self.units)
            self.units_label.set_style_text_font(lv.font_montserrat_24, 0)
            self.units_label.set_text("°" + place.get("units", "F"))
            self.units_label.center()

        for row, keys in enumerate(_GRID):
            for col, key in enumerate(keys):
                b = lv.button(panel)
                b.set_size(key_w, key_h)
                b.set_pos(
                    (width - 3 * key_w - 2 * gap) // 2 + col * (key_w + gap),
                    grid_top + row * (key_h + gap),
                )
                color = _GO if key == "ok" else _KEY
                b.set_style_bg_color(lv.color_hex(color), 0)
                label = lv.label(b)
                label.set_style_text_font(lv.font_montserrat_24, 0)
                if key == "del":
                    label.set_text(lv.SYMBOL.BACKSPACE)
                elif key == "ok":
                    label.set_text(lv.SYMBOL.OK)
                else:
                    label.set_text(key)
                label.center()
                b.add_event_cb(self._maker(key), lv.EVENT.CLICKED, None)
        self._refresh("Enter your ZIP code")

    def delete(self):
        self.panel.delete()

    def _maker(self, key):
        return lambda _event: self._press(key)

    def _refresh(self, title=None, color=_SOFT):
        if title is not None:
            self.title.set_text(title)
            self.title.set_style_text_color(lv.color_hex(color), 0)
        self.shown.set_text(self.digits + "-" * (_LENGTH - len(self.digits)))

    def _press(self, key):
        if self.busy:
            return
        if key == "del":
            if self.digits:
                self.digits = self.digits[:-1]
                self._refresh("Enter your ZIP code")
            elif forecast.place() is not None:
                self.done()  # nothing typed and a place to go back to
        elif key == "ok":
            if len(self.digits) == _LENGTH:
                self.busy = True
                self._refresh("Looking it up")
                self.scope.worker.submit(lambda: forecast.choose(self.digits), self._found, key="zip")
        elif len(self.digits) < _LENGTH:
            self.digits += key
            self._refresh()

    def _found(self, _place, error):
        self.busy = False
        if error is None:
            self.done()
            return
        if isinstance(error, ValueError):
            self._refresh("No place has that ZIP code", _BAD)
        else:
            self._refresh("Can't reach the service. Try again.", _BAD)
        self.digits = ""
        self._refresh()

    def _toggle_units(self, _event):
        units = "C" if forecast.place().get("units", "F") == "F" else "F"
        forecast.set_units(units)
        self.units_label.set_text("°" + units)
