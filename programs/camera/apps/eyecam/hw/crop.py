# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""The part of a camera frame a video takes."""


def video_crop(sw, sh, out_h, resolution, magnify):
    """The factory's cut for this zoom and size, as ``(x, y, w, h)`` in source
    pixels of an *sw* x *sh* frame.

    At 1080P it is the whole frame less the rows the encoder's multiple of 16
    drops (*out_h* is the encoder's height). At 720P and 480P it is the
    centre 1280x960. Each is divided by the zoom. A frame smaller than the
    factory's sensor (a USB camera's) gives the same cut of what it has, so
    the rectangle never leaves the frame.
    """
    if resolution == "1080P":
        bw, bh = sw, min(sh, out_h)
    else:
        bw, bh = min(1280, sw), min(960, sh)
    m = max(1, magnify)
    cw, ch = bw // m, bh // m
    return (sw - cw) // 2, (sh - ch) // 2, cw, ch


# The PPA scales in sixteenths: a square cut of 3840 / n pixels fills the 240
# square exactly, and any other size leaves the corner unpainted.
_EXACT = tuple(3840 // n for n in range(1, 256) if 3840 % n == 0)


def preview_side(w, h, magnify):
    """The side, in source pixels, of the centre square the preview shows at
    this zoom: the factory's 8/9 of the short side (960 of the Eye's 1080)
    when the PPA can scale it exactly, otherwise the nearest size it can."""
    want = (min(w, h) * 8 // 9) // max(1, min(4, magnify))
    room = min(w, h) // max(1, min(4, magnify))
    fits = [s for s in _EXACT if s <= room]
    return min(fits, key=lambda s: abs(s - want)) if fits else want
