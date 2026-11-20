# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""A row of thin bars, one per band: a small spectrum, or a set of levels.

``set_levels(levels)`` takes one value from 0.0 to 1.0 per bar. A bar jumps
up to a louder level at once and falls back at ``fall`` of the height per
call, as a meter's ballistics do, and only bars whose height changes by a
pixel or more are redrawn. Each bar is one LVGL rectangle with rounded ends,
so a row of twenty costs twenty small rectangles a frame at most.
"""

import lvgl as lv

from ._draw import box


class SpectrumBars:
    """*bands* bars across *width* x *height* at (*x*, *y*) in *parent*.

    Args:
        parent: the LVGL object to build on.
        x, y, width, height: where the bars stand, in *parent*.
        theme: a controlkit theme; the bars take its ``led_on`` colour
            unless *color* is given.
        bands: how many bars.
        gap: the space between bars in pixels; a third of a bar's pitch by
            default.
        color: the bars' colour, ``0xRRGGBB``.
        fall: how far a bar falls per call, as a fraction of the height.
        floor: the height of a silent bar in pixels, so the row still reads
            as a row; 0 hides silent bars.
    """

    def __init__(self, parent, x, y, width, height, theme, bands=16, gap=None, color=None, fall=0.08, floor=2):
        self.theme = theme
        self.bands = bands
        self.height = height
        self.fall = fall
        self.floor = floor
        self.rgb = None
        pitch = width / bands
        if gap is None:
            gap = max(1, int(pitch / 3))
        bar_w = max(1, int(pitch - gap))
        self.obj = box(parent, x, y, width, height)
        self.levels = [0.0] * bands
        self._px = [-1] * bands
        self._bars = []
        for i in range(bands):
            bar = box(self.obj, int(i * pitch), height - floor, bar_w, floor)
            bar.set_style_radius(bar_w // 2, 0)
            bar.set_style_bg_opa(lv.OPA.COVER, 0)
            self._bars.append(bar)
        self.set_color(theme["led_on"] if color is None else color)
        self.set_levels(self.levels)

    def set_color(self, rgb):
        """Draw the bars in *rgb*, ``0xRRGGBB``."""
        if rgb == self.rgb:
            return
        self.rgb = rgb
        c = lv.color_hex(rgb)
        for bar in self._bars:
            bar.set_style_bg_color(c, 0)

    def set_levels(self, levels):
        """Move each bar toward its level in *levels*, 0.0 to 1.0."""
        shown = self.levels
        fall = self.fall
        h = self.height
        floor = self.floor
        for i in range(self.bands):
            v = levels[i] if i < len(levels) else 0.0
            v = 0.0 if v < 0 else (1.0 if v > 1 else v)
            was = shown[i]
            if v < was - fall:
                v = was - fall
            shown[i] = v
            px = floor + int(v * (h - floor) + 0.5)
            if px != self._px[i]:
                self._px[i] = px
                bar = self._bars[i]
                bar.set_y(h - px)
                bar.set_height(px)

    def clear(self):
        """Drop every bar to the floor at once."""
        for i in range(self.bands):
            self.levels[i] = 0.0
        self.set_levels(self.levels)
