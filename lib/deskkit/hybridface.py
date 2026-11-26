# SPDX-FileCopyrightText: 2026 PyDevices / Brad Barnett
#
# SPDX-License-Identifier: MIT
"""A hybrid watch face in LVGL: analog hands over a deep blue dial, with the
time and date in digits in a window under the hands.

Roman numerals at the quarters, a ring of minute ticks, and chartreuse
seconds. It fits any square it's given; it was drawn for 240 by 240.

Example::

    face = HybridWatch(lv.screen_active(), 240, time.localtime)
    face.update_time()   # once a second, from a timer
"""

import lvgl as lv

_DAYS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
_MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")

BACKGROUND = 0x0B2A4A
CASE = 0x1D4166
CASE_EDGE = 0x3B6390
RING = 0x12355A
DIAL = 0x0A2440
DIAL_EDGE = 0x2A4F76
WINDOW = 0x082039
INK = 0xE8F0F8
DIM_INK = 0xB4C8DC
TICK = 0x86A0BB
ACCENT = 0xC4DC4C  # chartreuse
SHADOW = 0x061A30


def _font(size):
    for points in (48, 40, 36, 32, 28, 24, 22, 20, 18, 16, 14, 12, 10):
        if points <= size:
            font = getattr(lv, "font_montserrat_%d" % points, None)
            if font is not None:
                return font
    return getattr(lv, "font_montserrat_14", None) or lv.font_get_default()


def _disc(parent, size, color, grad=None, edge=None, edge_w=1):
    o = lv.obj(parent)
    o.remove_style_all()
    o.remove_flag(lv.obj.FLAG.SCROLLABLE)
    o.remove_flag(lv.obj.FLAG.CLICKABLE)
    o.set_size(size, size)
    o.center()
    o.set_style_radius(lv.RADIUS_CIRCLE, 0)
    o.set_style_bg_color(lv.color_hex(color), 0)
    o.set_style_bg_opa(lv.OPA.COVER, 0)
    if grad is not None:
        o.set_style_bg_grad_color(lv.color_hex(grad), 0)
        o.set_style_bg_grad_dir(lv.GRAD_DIR.VER, 0)
    if edge is not None:
        o.set_style_border_color(lv.color_hex(edge), 0)
        o.set_style_border_width(edge_w, 0)
    return o


def _label(parent, text, color, size):
    lbl = lv.label(parent)
    lbl.set_style_text_font(_font(size), 0)
    lbl.set_style_text_color(lv.color_hex(color), 0)
    lbl.set_text(text)
    return lbl


class HybridWatch:
    """The face on *parent*, *size* pixels across, centred. *read_now*
    returns the time as ``time.localtime`` does; `update_time` reads it."""

    def __init__(self, parent, size, read_now):
        self.parent = parent
        self._read_now = read_now
        self._shown = None
        self._styles = []  # LVGL keeps pointers to these
        parent.set_style_bg_color(lv.color_hex(BACKGROUND), 0)
        parent.set_style_bg_opa(lv.OPA.COVER, 0)
        parent.remove_flag(lv.obj.FLAG.SCROLLABLE)
        dial = int(size * 0.90)
        r = dial // 2
        _disc(parent, size, CASE, DIAL, CASE_EDGE, max(2, int(size * 0.017)))
        ring = _disc(parent, int(size * 0.95), RING, edge=ACCENT)
        ring.set_style_border_opa(lv.OPA._60, 0)
        face = _disc(parent, dial, DIAL, RING, DIAL_EDGE)
        self.face = face

        inset = int(dial * 0.08)
        for text, where, dx, dy in (
            ("XII", lv.ALIGN.TOP_MID, 0, inset),
            ("VI", lv.ALIGN.BOTTOM_MID, 0, -inset),
            ("IX", lv.ALIGN.LEFT_MID, inset, 0),
            ("III", lv.ALIGN.RIGHT_MID, -inset, 0),
        ):
            _label(face, text, INK, 14).align(where, dx, dy)
        _label(face, "OMNIPYTHON", ACCENT, 11).align(lv.ALIGN.TOP_MID, 0, int(dial * 0.25))

        # The digital window, under the hands.
        pw, ph = int(dial * 0.46), int(dial * 0.18)
        window = lv.obj(face)
        window.remove_style_all()
        window.remove_flag(lv.obj.FLAG.SCROLLABLE)
        window.remove_flag(lv.obj.FLAG.CLICKABLE)
        window.set_size(pw, ph)
        window.align(lv.ALIGN.BOTTOM_MID, 0, -int(dial * 0.18))
        window.set_style_radius(max(4, int(ph * 0.18)), 0)
        window.set_style_bg_color(lv.color_hex(WINDOW), 0)
        window.set_style_bg_opa(lv.OPA._90, 0)
        window.set_style_border_color(lv.color_hex(DIAL_EDGE), 0)
        window.set_style_border_width(1, 0)
        self.digital_time = _label(window, "00:00:00", 0xF8FAFC, 13)
        self.digital_time.align(lv.ALIGN.TOP_MID, 0, 4)
        self.digital_date = _label(window, "", DIM_INK, 10)
        self.digital_date.align(lv.ALIGN.BOTTOM_MID, 0, -4)

        # 60 ticks over 354 degrees: 6 apart, and no 61st on top of 12.
        ticks = lv.scale(face)
        ticks.remove_style_all()
        ticks.set_size(dial, dial)
        ticks.center()
        ticks.set_mode(lv.scale.MODE.ROUND_INNER)
        ticks.set_range(0, 3540)
        ticks.set_angle_range(354)
        ticks.set_rotation(270)
        ticks.set_total_tick_count(60)
        ticks.set_major_tick_every(5)
        ticks.set_label_show(False)
        minor = self._style()
        minor.set_line_color(lv.color_hex(TICK))
        minor.set_line_width(1)
        minor.set_length(max(3, int(r * 0.05)))
        ticks.add_style(minor, lv.PART.ITEMS)
        major = self._style()
        major.set_line_color(lv.color_hex(ACCENT))
        major.set_line_width(max(2, int(dial * 0.009)))
        major.set_length(max(6, int(r * 0.09)))
        major.set_line_rounded(True)
        ticks.add_style(major, lv.PART.INDICATOR)

        # The hands turn on a scale of their own, 0 to 3600 round the dial.
        hands = lv.scale(face)
        hands.remove_style_all()
        hands.set_size(dial, dial)
        hands.center()
        hands.set_mode(lv.scale.MODE.ROUND_INNER)
        hands.set_range(0, 3600)
        hands.set_angle_range(360)
        hands.set_rotation(270)
        hands.set_total_tick_count(0)
        hands.set_label_show(False)
        self.hands = hands
        hour, minute, second = int(r * 0.58), int(r * 0.82), int(r * 0.90)
        self.layers = {
            "hour": (
                (self._line(SHADOW, max(4, int(dial * 0.025))), hour + 1),
                (self._line(INK, max(3, int(dial * 0.018))), int(hour * 0.85)),
                (self._line(ACCENT, 1), hour),
            ),
            "minute": (
                (self._line(SHADOW, max(3, int(dial * 0.018))), minute + 1),
                (self._line(0xF8FAFC, max(2, int(dial * 0.010))), int(minute * 0.88)),
                (self._line(ACCENT, 1), minute),
            ),
            "second": (
                (self._line(SHADOW, max(2, int(dial * 0.012))), second + 1),
                (self._line(ACCENT, 1), second),
            ),
        }
        hub = _disc(face, max(10, int(dial * 0.065)), ACCENT, 0x5E7012, 0xF4F9E0)
        hub.center()
        self.update_time()

    def _style(self):
        s = lv.style_t()
        s.init()
        self._styles.append(s)
        return s

    def _line(self, color, width):
        line = lv.line(self.hands)
        s = self._style()
        s.set_line_color(lv.color_hex(color))
        s.set_line_width(width)
        s.set_line_rounded(True)
        line.add_style(s, 0)
        return line

    def update_time(self):
        """Move the hands and the digits to the time *read_now* gives, when
        the second has changed."""
        t = self._read_now()
        hour, minute, second = t[3], t[4], t[5]
        if (hour, minute, second) == self._shown:
            return
        self._shown = (hour, minute, second)
        values = {
            "hour": ((hour % 12) * 300 + minute * 5 + second // 12) % 3600,
            "minute": (minute * 60 + second) % 3600,
            "second": second * 60,
        }
        for which, layers in self.layers.items():
            for line, length in layers:
                self.hands.set_line_needle_value(line, length, values[which])
        self.digital_time.set_text("%02d:%02d:%02d" % (hour, minute, second))
        self.digital_date.set_text("%s  %s %02d" % (_DAYS[t[6] % 7], _MONTHS[(t[1] - 1) % 12], t[2]))
