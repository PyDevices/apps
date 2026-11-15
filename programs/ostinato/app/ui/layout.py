# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Where each region of the window goes.

Every size here comes from the window size through one scale factor, and
each layout is a table of region rectangles. A layout for another size of
window is another table, not another set of screens. A table can also name
``touch``, the least size of a control in device pixels (a phone's), and
``pages``, regions that share one rectangle and are shown one at a time.
"""

BASE_W, BASE_H = 1920, 1080

# Below this scale the compact table takes over. Text stops shrinking at 12
# pixels, which a 14 pixel design size reaches here, so from this point down
# the words need a larger share of the window than the scale gives them.
COMPACT_BELOW = 0.85

# A window whose short side is under this many CSS pixels is a phone's (a
# tablet's is 600 or more). It gets the phone table.
PHONE_BELOW = 500

# The least a control a finger presses may measure, in CSS pixels.
TOUCH = 44


def scale_for(w, h):
    return max(0.6, min(w / BASE_W, h / BASE_H))


def desktop(w, h):
    s = scale_for(w, h)
    top = int(72 * s)
    left = int(300 * s)
    right = int(400 * s)
    keys = int(150 * s)
    status = int(30 * s)
    mid_h = h - top - keys - status
    return {
        "scale": s,
        "top": (0, 0, w, top),
        "tracks": (0, top, left, mid_h),
        "editor": (left, top, w - left - right, mid_h),
        "inspector": (w - right, top, right, mid_h),
        "keys": (0, top + mid_h, w, keys),
        "status": (0, h - status, w, status),
    }


def compact(w, h):
    """A window around 1280x720.

    The track list and the inspector are a quarter wider than the scale alone
    would make them, so instrument and knob names fit. The track list also runs
    down beside the keyboard, which gives each track's row the height its pan
    knob needs.
    """
    s = scale_for(w, h)
    top = int(72 * s)
    left = int(375 * s)
    right = int(465 * s)
    keys = int(150 * s)
    status = int(30 * s)
    mid_h = h - top - keys - status
    return {
        "scale": s,
        "top": (0, 0, w, top),
        "tracks": (0, top, left, mid_h + keys),
        "editor": (left, top, w - left - right, mid_h),
        "inspector": (w - right, top, right, mid_h),
        "keys": (left, top + mid_h, w - left, keys),
        "status": (0, h - status, w, status),
    }


def phone(w, h, dpr=1):
    """A phone, on its side (around 844x390 CSS pixels) or upright.

    There's room for one region at a time, so the track list, the editor,
    the inspector and the keyboard are pages of the same rectangle, and a
    row of tabs under it picks the one shown. A page scrolls when what it
    holds is taller than the screen. Design sizes are CSS pixels here, and
    every control a finger presses is at least ``touch`` pixels across.

    Upright, the tabs take the whole width and the status line sits over
    them; on its side the status line is beside the tabs.
    """
    s = float(dpr)
    top = int(64 * s)
    bar = int(52 * s)
    if h > w:
        status = int(26 * s)
        page = (0, top, w, h - top - status - bar)
        tabs = (0, h - bar, w, bar)
        status_rect = (0, h - bar - status, w, status)
    else:
        tabs_w = min(w // 2, int(400 * s))
        page = (0, top, w, h - top - bar)
        tabs = (0, h - bar, tabs_w, bar)
        status_rect = (tabs_w, h - bar, w - tabs_w, bar)
    return {
        "scale": s,
        "touch": int(TOUCH * s),
        "pages": ("editor", "tracks", "inspector", "keys"),
        "top": (0, 0, w, top),
        "tracks": page,
        "editor": page,
        "inspector": page,
        "keys": page,
        "tabs": tabs,
        "status": status_rect,
    }


def is_phone(w, h, dpr=1):
    return min(w, h) < PHONE_BELOW * dpr


def pick(w, h, dpr=1):
    """The layout for this window of ``w`` x ``h`` device pixels, ``dpr`` of them to a CSS pixel.

    A phone gets the phone table; a window below 85% of 1920x1080 the compact one; else the desktop one.
    """
    if is_phone(w, h, dpr):
        return phone(w, h, dpr)
    if scale_for(w, h) < COMPACT_BELOW:
        return compact(w, h)
    return desktop(w, h)
