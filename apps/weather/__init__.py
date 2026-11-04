# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Weather: conditions and five days ahead, laid out to fit a round screen.

Swipe up for the five days and down to come back. Hold your finger on the
screen to change the ZIP code or the units.
"""

import lvgl as lv
from deskkit import forecast

from . import icons
from .zippad import ZipPad

_BG_DAY = 0x123A5E
_BG_NIGHT = 0x0A1020
_WHITE = 0xFFFFFF
_SOFT = 0xB9C6D4
_RAIN = 0x57B6FF
_ICON = 130
_SMALL_ICON = 44
_BIG_TEMP_SCALE = 512  # the largest compiled font, doubled


def _clean(obj):
    obj.remove_flag(lv.obj.FLAG.SCROLLABLE)
    obj.set_style_pad_all(0, 0)
    obj.set_style_border_width(0, 0)


def _label(parent, font, color=_WHITE):
    label = lv.label(parent)
    label.set_style_text_font(font, 0)
    label.set_style_text_color(lv.color_hex(color), 0)
    label.remove_flag(lv.obj.FLAG.CLICKABLE)
    return label


class _Screen:
    def __init__(self, scope):
        self.scope = scope
        self.root = scope.root
        self.w, self.h = scope.size
        self.pad = None
        self.showing_days = False
        _clean(self.root)
        self.root.add_event_cb(self._gesture, lv.EVENT.GESTURE, None)
        self.root.add_event_cb(self._held, lv.EVENT.LONG_PRESSED, None)
        self.now = None
        self.days = None
        self.notice = _label(self.root, lv.font_montserrat_24, _SOFT)
        self.notice.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        self.notice.set_width(self.w * 7 // 10)
        self.notice.set_long_mode(lv.label.LONG_MODE.WRAP)
        self.notice.center()

    def _panel(self, background):
        panel = lv.obj(self.root)
        _clean(panel)
        panel.set_size(self.w, self.h)
        panel.set_style_radius(0, 0)
        panel.set_style_bg_color(lv.color_hex(background), 0)
        panel.remove_flag(lv.obj.FLAG.CLICKABLE)
        return panel

    def _drop(self, attr):
        panel = getattr(self, attr)
        if panel is not None:
            panel.delete()
            setattr(self, attr, None)

    def show(self):
        """Draw what's known. Rebuilt whole: it changes twice an hour at most."""
        self._drop("now")
        self._drop("days")
        place = forecast.place()
        data = forecast.latest
        if self.pad is not None:
            return
        if place is None:
            self.ask_for_zip()
            return
        if data is None:
            self.notice.remove_flag(lv.obj.FLAG.HIDDEN)
            if forecast.last_error is None:
                self.notice.set_text("Getting the weather")
            else:
                self.notice.set_text("Can't reach the weather service. Trying again soon.")
            return
        self.notice.add_flag(lv.obj.FLAG.HIDDEN)
        background = _BG_DAY if data["is_day"] else _BG_NIGHT
        self.root.set_style_bg_color(lv.color_hex(background), 0)
        self._build_now(place, data, background)
        self._build_days(data, background)
        self._apply_page()

    def _build_now(self, place, data, background):
        panel = self.now = self._panel(background)
        name = _label(panel, lv.font_montserrat_16, _SOFT)
        name.set_text(place["name"])
        name.align(lv.ALIGN.TOP_MID, 0, self.h * 8 // 100)

        icon = icons.make(panel, data["code"], data["is_day"], _ICON, background)
        icon.align(lv.ALIGN.TOP_MID, 0, self.h * 13 // 100)

        temp = _label(panel, lv.font_montserrat_40)
        temp.set_text("%d°" % forecast.degrees(data["temp"]))
        temp.set_style_transform_scale(_BIG_TEMP_SCALE, 0)
        temp.update_layout()
        temp.set_style_transform_pivot_x(temp.get_width() // 2, 0)
        temp.set_style_transform_pivot_y(temp.get_height() // 2, 0)
        temp.align(lv.ALIGN.CENTER, 0, self.h * 8 // 100)

        words = _label(panel, lv.font_montserrat_24)
        words.set_text(icons.name(data["code"], data["is_day"]))
        words.align(lv.ALIGN.CENTER, 0, self.h * 22 // 100)

        range_ = _label(panel, lv.font_montserrat_16, _SOFT)
        range_.set_text(
            "H %d°   L %d°   Feels %d°"
            % (
                forecast.degrees(data["hi"]),
                forecast.degrees(data["lo"]),
                forecast.degrees(data["feels"]),
            )
        )
        range_.align(lv.ALIGN.CENTER, 0, self.h * 30 // 100)

        if forecast.last_error is not None:
            old = _label(panel, lv.font_montserrat_14, _SOFT)
            old.set_text("as of %s" % data["as_of"])
            old.align(lv.ALIGN.CENTER, 0, self.h * 37 // 100)

    def _build_days(self, data, background):
        panel = self.days = self._panel(background)
        row_h = self.h * 15 // 100
        top = (self.h - row_h * len(data["days"])) // 2
        for i, (day, code, hi, lo, rain) in enumerate(data["days"]):
            y = top + i * row_h
            cy = y + row_h // 2 - self.h // 2
            name = _label(panel, lv.font_montserrat_24)
            name.set_text("Today" if i == 0 else day)
            name.align(lv.ALIGN.LEFT_MID, self.w * 13 // 100, cy)

            icon = icons.make(panel, code, True, _SMALL_ICON, background)
            icon.align(lv.ALIGN.CENTER, -self.w * 8 // 100, cy)

            temps = _label(panel, lv.font_montserrat_24)
            temps.set_text("%d° / %d°" % (forecast.degrees(hi), forecast.degrees(lo)))
            temps.align(lv.ALIGN.RIGHT_MID, -self.w * 16 // 100, cy - 9)

            chance = _label(panel, lv.font_montserrat_14, _RAIN)
            chance.set_text("%d%% rain" % rain)
            chance.align(lv.ALIGN.RIGHT_MID, -self.w * 16 // 100, cy + 14)

    def _apply_page(self):
        shown, hidden = (self.days, self.now) if self.showing_days else (self.now, self.days)
        if shown is not None:
            shown.remove_flag(lv.obj.FLAG.HIDDEN)
        if hidden is not None:
            hidden.add_flag(lv.obj.FLAG.HIDDEN)

    def _gesture(self, _event):
        direction = lv.indev_active().get_gesture_dir()
        if direction == lv.DIR.TOP:
            self.showing_days = True
        elif direction == lv.DIR.BOTTOM:
            self.showing_days = False
        else:
            return
        self._apply_page()

    def _held(self, _event):
        if self.pad is None:
            self.ask_for_zip()

    def ask_for_zip(self):
        self.notice.add_flag(lv.obj.FLAG.HIDDEN)
        self._drop("now")
        self._drop("days")
        self.pad = ZipPad(self.scope, self.w, self.h, self._zip_done)

    def _zip_done(self):
        self.pad.delete()
        self.pad = None
        self.show()


def main(scope):
    screen = _Screen(scope)
    forecast.place()  # loads it, and with it the timezone
    screen.show()
    forecast.keep_fresh(scope, screen.show)
