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
