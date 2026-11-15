# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Where each region of the window goes.

Every size here comes from the window size through one scale factor, and
each layout is a table of region rectangles. A layout for another size of
window is another table, not another set of screens.
"""

BASE_W, BASE_H = 1920, 1080

# Below this scale the compact table takes over. Text stops shrinking at 12
# pixels, which a 14 pixel design size reaches here, so from this point down
# the words need a larger share of the window than the scale gives them.
COMPACT_BELOW = 0.85


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


def pick(w, h):
    """The layout for this window: the compact table below 85% of 1920x1080, else the desktop one."""
    if scale_for(w, h) < COMPACT_BELOW:
        return compact(w, h)
    return desktop(w, h)
