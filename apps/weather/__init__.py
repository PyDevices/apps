# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Weather: conditions and five days ahead, laid out to fit a round screen.

It was drawn for a 480-pixel round screen, and on a smaller one everything
shrinks with it (`sizing`), so the same layout fits a 240-pixel watch face.

Until you choose a place it shows the city the board's IP address is in,
marked with a location pin. Swipe up for the five days and down to come back.
Hold your finger on the screen to choose a ZIP code or change the units.
"""

import lvgl as lv
from appkit.shell import is_round
from deskkit import forecast, localtime

from . import icons, sizing
from .zippad import ZipPad

_BG_DAY = 0x123A5E
_BG_NIGHT = 0x0A1020
_WHITE = 0xFFFFFF
_SOFT = 0xB9C6D4
_RAIN = 0x57B6FF
_ICON = 130
_SMALL_ICON = 44
_BIG_TEMP_SCALE = 512  # the largest compiled font, doubled, at full size
# The temperature's font: 40 px, or the largest a firmware without it has.
_TEMP = getattr(lv, "font_montserrat_40", None) or getattr(lv, "font_montserrat_32", lv.font_montserrat_24)


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
        self.k = sizing.scale(self.w, self.h)
        self.round = is_round()
        self.notice = _label(self.root, sizing.font(24 * self.k, 16), _SOFT)
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
        place = forecast.current()
        data = forecast.latest
        if self.pad is not None:
            return
        if place is None:
            if localtime.finding():
                self.notice.remove_flag(lv.obj.FLAG.HIDDEN)
                self.notice.set_text("Finding where you are")
                return
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
        # A column centred on the screen, where a round one is widest: the
        # place, the icon, the temperature, its words, the day's range.
        k = self.k
        panel = self.now = self._panel(background)
        name = _label(panel, sizing.font(16 * k))
        name.set_style_text_color(lv.color_hex(_SOFT), 0)
        if place.get("from_ip"):
            name.set_text(lv.SYMBOL.GPS + " " + place["name"])
        else:
            name.set_text(place["name"])

        icon_size = int(_ICON * k)
        icon = icons.make(panel, data["code"], data["is_day"], icon_size, background)

        temp = _label(panel, _TEMP)
        temp.set_text("%d°" % forecast.degrees(data["temp"]))
        temp_scale = int(_BIG_TEMP_SCALE * k)
        temp.set_style_transform_scale(temp_scale, 0)
        temp.update_layout()
        temp.set_style_transform_pivot_x(temp.get_width() // 2, 0)
        temp.set_style_transform_pivot_y(temp.get_height() // 2, 0)

        words = _label(panel, sizing.font(24 * k, 16))
        words.set_text(icons.name(data["code"], data["is_day"]))

        range_ = _label(panel, sizing.font(16 * k), _SOFT)
        range_.set_text(
            "H %d°  L %d°  Feels %d°"
            % (
                forecast.degrees(data["hi"]),
                forecast.degrees(data["lo"]),
                forecast.degrees(data["feels"]),
            )
        )
        column = [(name, 0), (icon, 0), (temp, temp_scale), (words, 0), (range_, 0)]
        if forecast.last_error is not None:
            old = _label(panel, sizing.font(14 * k), _SOFT)
            old.set_text("as of %s" % data["as_of"])
            column.append((old, 0))
        self._stack(column, int(24 * k))

    def _stack(self, column, gap):
        """Put each ``(obj, transform_scale)`` under the last, *gap* apart,
        the whole column centred on the screen. On a round screen the gap
        shrinks until every line is inside the circle."""
        sizes = []
        for obj, scale in column:
            obj.update_layout()
            w, h = obj.get_width(), obj.get_height()
            if scale:
                # Drawn scaled about its middle; only the glyphs' cap height
                # shows, so the line's empty top and bottom aren't counted.
                w, h = w * scale // 256, h * scale // 256 * 3 // 4
            sizes.append((w, h))
        while True:
            y = (self.h - sum(h for _, h in sizes) - gap * (len(column) - 1)) // 2
            tops = []
            fits = True
            for w, h in sizes:
                tops.append(y)
                if w > 2 * sizing.half_width(self.w, self.h, self.round, y, y + h, 2):
                    fits = False
                y += h + gap
            if fits or gap <= 2:
                break
            gap -= 2
        for (obj, _scale), (_w, h), top in zip(column, sizes, tops):
            obj.align(lv.ALIGN.TOP_MID, 0, top + (h - obj.get_height()) // 2)

    def _build_days(self, data, background):
        k = self.k
        panel = self.days = self._panel(background)
        big = sizing.font(24 * k, 16)
        small = sizing.font(14 * k)
        rows = len(data["days"])
        pair = big.get_line_height() + small.get_line_height()
        row_h = self.h * 15 // 100
        if self.round:
            row_h = min(row_h, self.h * 72 // 100 // rows)
        row_h = max(row_h, pair)
        top = (self.h - row_h * rows) // 2
        # Every row's ends line up, inside the circle at the first and last rows.
        half = sizing.half_width(self.w, self.h, self.round, top, top + row_h * rows)
        half = min(half, self.h * 6 // 10)
        icon_size = max(20, int(_SMALL_ICON * k))
        for i, (day, code, hi, lo, rain) in enumerate(data["days"]):
            y = top + i * row_h
            cy = y + row_h // 2 - self.h // 2
            name = _label(panel, big)
            name.set_text("Today" if i == 0 else day)
            name.align(lv.ALIGN.LEFT_MID, self.w // 2 - half, cy)

            icon = icons.make(panel, code, True, icon_size, background)
            icon.align(lv.ALIGN.CENTER, -half // 6, cy)

            temps = _label(panel, big)
            temps.set_text("%d° / %d°" % (forecast.degrees(hi), forecast.degrees(lo)))
            chance = _label(panel, small, _RAIN)
            chance.set_text("%d%% rain" % rain)
            temps.align(lv.ALIGN.RIGHT_MID, -(self.w // 2 - half), cy - pair // 2 + big.get_line_height() // 2)
            chance.align(lv.ALIGN.RIGHT_MID, -(self.w // 2 - half), cy + pair // 2 - small.get_line_height() // 2)

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
        lv.indev_active().wait_release()  # or a slow swipe would also count as a hold
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
