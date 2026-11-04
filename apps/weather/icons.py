# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Weather icons built from LVGL objects, so they scale to any size with no image files."""

import lvgl as lv

_SUN = 0xFFC533
_MOON = 0xDCE6F2
_CLOUD = 0xD5DEE8
_DARK_CLOUD = 0x8896A6
_RAIN = 0x57B6FF
_SNOW = 0xFFFFFF
_BOLT = 0xFFE14D

CLEAR, PARTLY, CLOUDY, FOG, DRIZZLE, RAIN, SNOW, STORM = range(8)

NAMES = {
    CLEAR: "Clear",
    PARTLY: "Partly cloudy",
    CLOUDY: "Cloudy",
    FOG: "Fog",
    DRIZZLE: "Drizzle",
    RAIN: "Rain",
    SNOW: "Snow",
    STORM: "Thunderstorm",
}


def kind(code):
    """Return the icon kind for a WMO weather code, the codes Open-Meteo sends."""
    if code <= 1:
        return CLEAR
    if code == 2:
        return PARTLY
    if code == 3:
        return CLOUDY
    if code in (45, 48):
        return FOG
    if 51 <= code <= 57:
        return DRIZZLE
    if 61 <= code <= 67 or 80 <= code <= 82:
        return RAIN
    if 71 <= code <= 77 or code in (85, 86):
        return SNOW
    if code >= 95:
        return STORM
    return CLOUDY


def name(code, is_day):
    """Return the words for a WMO weather code."""
    which = kind(code)
    if which == CLEAR and is_day:
        return "Sunny"
    return NAMES[which]


def _disc(parent, x, y, d, color):
    o = lv.obj(parent)
    o.remove_flag(lv.obj.FLAG.CLICKABLE)
    o.remove_flag(lv.obj.FLAG.SCROLLABLE)
    o.set_style_pad_all(0, 0)
    o.set_style_border_width(0, 0)
    o.set_style_bg_color(lv.color_hex(color), 0)
    o.set_style_radius(lv.RADIUS_CIRCLE, 0)
    o.set_pos(x, y)
    o.set_size(d, d)
    return o


def _bar(parent, x, y, w, h, color):
    o = _disc(parent, x, y, w, color)
    o.set_size(w, h)
    return o


def _sun(parent, x, y, d):
    _disc(parent, x, y, d, _SUN)


def _moon(parent, x, y, d, background):
    _disc(parent, x, y, d, _MOON)
    _disc(parent, x + d * 3 // 10, y - d // 10, d * 8 // 10, background)


def _cloud(parent, x, y, w, color=_CLOUD):
    u = w // 10
    _bar(parent, x, y + 3 * u, w, 3 * u, color)
    _disc(parent, x + u, y + u, 4 * u, color)
    _disc(parent, x + 4 * u, y, 5 * u, color)


def _streaks(parent, x, y, w, n, color, long):
    step = w // n
    for i in range(n):
        _bar(parent, x + step // 4 + i * step, y, max(2, w // 16), long, color)


def _bolt(parent, x, y, u):
    bolt = lv.line(parent)
    bolt.set_points(
        [
            {"x": x + u, "y": y},
            {"x": x - u // 2, "y": y + u * 2},
            {"x": x + u // 2, "y": y + u * 2},
            {"x": x - u, "y": y + u * 4},
        ],
        4,
    )
    bolt.set_style_line_width(max(2, u // 2), 0)
    bolt.set_style_line_color(lv.color_hex(_BOLT), 0)
    bolt.set_style_line_rounded(True, 0)


def make(parent, code, is_day, size, background):
    """Draw the icon for *code* in a new transparent box; return the box.

    Args:
        parent (lv.obj): What to draw it on.
        code (int): The WMO weather code.
        is_day (bool): False swaps the sun for the moon.
        size (int): The box's width and height in pixels.
        background (int): The colour behind it, which cuts the moon's crescent.
    """
    box = lv.obj(parent)
    box.remove_flag(lv.obj.FLAG.CLICKABLE)
    box.remove_flag(lv.obj.FLAG.SCROLLABLE)
    box.set_style_pad_all(0, 0)
    box.set_style_border_width(0, 0)
    box.set_style_bg_opa(lv.OPA.TRANSP, 0)
    box.set_size(size, size)

    which = kind(code)
    u = size // 10
    if which == CLEAR:
        if is_day:
            _sun(box, u * 2, u * 2, u * 6)
        else:
            _moon(box, u * 2, u * 2, u * 6, background)
    elif which == PARTLY:
        if is_day:
            _sun(box, u * 4, u, u * 5)
        else:
            _moon(box, u * 4, u, u * 5, background)
        _cloud(box, 0, u * 3, u * 8)
    elif which == CLOUDY:
        _cloud(box, u, u * 2, u * 8)
    elif which == FOG:
        for i in range(4):
            _bar(box, u * (1 + i % 2), u * (2 + i * 2), u * 7, u, _CLOUD)
    elif which == DRIZZLE:
        _cloud(box, u, u, u * 8)
        _streaks(box, u * 2, u * 7, u * 6, 3, _RAIN, u)
    elif which == RAIN:
        _cloud(box, u, u, u * 8, _DARK_CLOUD)
        _streaks(box, u * 2, u * 6, u * 6, 3, _RAIN, u * 3)
    elif which == SNOW:
        _cloud(box, u, u, u * 8)
        for x, y in ((2, 7), (4, 8), (6, 7)):
            _disc(box, u * x, u * y, u, _SNOW)
    else:
        _cloud(box, u, u, u * 8, _DARK_CLOUD)
        _bolt(box, u * 5, u * 6, u)
    return box
