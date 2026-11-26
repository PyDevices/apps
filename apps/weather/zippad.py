# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""A keypad for a ZIP code, sized so every key sits inside a round screen."""

import lvgl as lv
from appkit.shell import is_round
from deskkit import forecast

from . import sizing

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

        k = sizing.scale(width, height)
        side = min(width, height)
        key_w = side * 20 // 100
        key_h = side * 11 // 100
        gap = max(4, side * 2 // 100)
        key_font = sizing.font(24 * k, 16)
        title_font = sizing.font(16 * k)
        digits_font = sizing.font(40 * k, 24)

        # Title, digits, then the keys: a column centred on the screen, so a
        # round one's edge clears the top and bottom rows.
        title_h = title_font.get_line_height()
        digits_h = digits_font.get_line_height()
        column = title_h + gap + digits_h + gap + 4 * key_h + 3 * gap
        top = (height - column) // 2
        digits_top = top + title_h + gap
        grid_top = digits_top + digits_h + gap

        self.title = lv.label(panel)
        self.title.set_style_text_font(title_font, 0)
        self.title.set_style_text_color(lv.color_hex(_SOFT), 0)
        self.title.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        self.title.set_long_mode(lv.label.LONG_MODE.WRAP)
        # A message too long for the row wraps upwards, inside the circle.
        self.title.set_width(2 * sizing.half_width(width, height, is_round(), top, top + title_h, 4))
        self.title_bottom = top + title_h
        self.width = width

        self.shown = lv.label(panel)
        self.shown.set_style_text_font(digits_font, 0)
        self.shown.set_style_text_color(lv.color_hex(_WHITE), 0)
        self.shown.align(lv.ALIGN.TOP_MID, 0, digits_top)

        place = forecast.current()
        if place is not None:
            self.units = lv.button(panel)
            units_w = key_w * 8 // 10
            self.units.set_size(units_w, min(key_h, digits_h))
            # Right of the digits, clear of five of them.
            self.units.set_pos(width // 2 + side * 21 // 100, digits_top + (digits_h - min(key_h, digits_h)) // 2)
            self.units.set_style_bg_color(lv.color_hex(_KEY), 0)
            self.units.set_style_pad_all(0, 0)
            self.units.add_event_cb(self._toggle_units, lv.EVENT.CLICKED, None)
            self.units_label = lv.label(self.units)
            self.units_label.set_style_text_font(key_font, 0)
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
                b.set_style_pad_all(0, 0)
                label = lv.label(b)
                label.set_style_text_font(key_font, 0)
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
            self.title.update_layout()
            self.title.set_pos((self.width - self.title.get_width()) // 2, self.title_bottom - self.title.get_height())
        self.shown.set_text(self.digits + "-" * (_LENGTH - len(self.digits)))

    def _press(self, key):
        if self.busy:
            return
        if key == "del":
            if self.digits:
                self.digits = self.digits[:-1]
                self._refresh("Enter your ZIP code")
            elif forecast.current() is not None:
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
        units = "C" if forecast.current().get("units", "F") == "F" else "F"
        forecast.set_units(units)
        self.units_label.set_text("°" + units)
