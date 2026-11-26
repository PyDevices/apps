# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Sizes for Weather's screens, from the 480-pixel round screen it was drawn for.

Every size is the one it has there, times `scale`; a font is the largest
the firmware has that is no taller, and never smaller than the least one
that still reads. On a round screen `half_width` says how much of a row
lies inside the circle.
"""

import lvgl as lv

DRAWN_FOR = 480  # the screen the sizes below are given for
_SIZES = (48, 40, 36, 32, 28, 24, 22, 20, 18, 16, 14, 12)


def scale(width, height):
    """How much smaller this screen is than the one Weather was drawn for:
    1.0 on a 480-pixel screen and larger ones, 0.5 on a 240-pixel one."""
    return min(1.0, min(width, height) / DRAWN_FOR)


def font(px, least=14):
    """The largest Montserrat font no taller than *px*, and no smaller than
    *least* when the firmware has one that size or larger."""
    px = max(px, least)
    for size in _SIZES:
        if size <= px:
            f = getattr(lv, "font_montserrat_%d" % size, None)
            if f is not None:
                return f
    for size in reversed(_SIZES):
        f = getattr(lv, "font_montserrat_%d" % size, None)
        if f is not None:
            return f
    return lv.font_get_default()


def half_width(width, height, round_, top, bottom, margin=6):
    """Half the width a row from *top* to *bottom* (pixels from the top) can
    use: inside the circle on a round screen, less *margin* on each side."""
    if not round_:
        return width // 2 - margin
    r = width / 2
    dy = max(abs(top - height / 2), abs(bottom - height / 2))
    if dy >= r:
        return 0
    return int((r * r - dy * dy) ** 0.5) - margin


def below_home(scope, gap=4, centred=True):
    """How far down the Shell's Home button reaches, plus *gap*, when it
    floats over the top of the app's screen; 0 when it doesn't. Weather's
    words start below it, so the button never sits on them. For *centred*
    words, a button in a corner is no matter."""
    shell = getattr(getattr(scope, "launcher", None), "shell", None)
    button = getattr(shell, "home_button", None)
    if button is None or button.has_flag(lv.obj.FLAG.HIDDEN):
        return 0
    button.update_layout()
    area = lv.area_t()
    button.get_coords(area)
    width, height = scope.size
    # A button in a corner clears the words, which are centred; one that
    # reaches towards the middle, as on a round screen, doesn't.
    if area.y1 > height // 4:
        return 0
    if centred and (area.x2 < width // 4 or area.x1 > width * 3 // 4):
        return 0
    return area.y2 + 1 + gap
