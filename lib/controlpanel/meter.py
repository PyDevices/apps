# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""An LED segment meter: a column (or row) of lit segments for a level.

The bottom segments run green, the top ones amber and red, as on a hardware
output meter. ``set_level(0.0 to 1.0)`` lights as many segments as the level
covers; it only repaints the segments that change, so a meter updated every
tick costs a few small rectangles.
"""

import lvgl as lv

from ._draw import box, fill, label, plain

_LEGEND_H = 16
_GAP = 2
#: Where the green zone ends and the amber one begins, and the red one starts,
#: as fractions of the full scale.
_AMBER = 0.7
_RED = 0.9


class LedMeter:
    """A meter at (*x*, *y*) in *parent*, *width* x *height*, with *segments* lit in turn."""

    def __init__(self, parent, x, y, width, height, theme, segments=16, vertical=True, legend=""):
        self.theme = theme
        self.vertical = vertical
        self.count = segments
        self.level = 0.0
        self._lit = 0
        self._legend_h = _LEGEND_H if legend else 0

        cell = plain(lv.obj(parent))
        cell.set_pos(x, y)
        cell.set_size(width, height)
        self.obj = cell

        if legend:
            text = label(cell, legend.upper(), theme["legend"], None, 1)
            text.set_width(width)
            text.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
            text.set_pos(0, 0)

        self._segments = []
        bar_h = height - self._legend_h
        bar_w = width
        for i in range(segments):
            if vertical:
                seg_len = (bar_h - _GAP * (segments - 1)) / segments
                seg_y = self._legend_h + bar_h - (i + 1) * seg_len - i * _GAP
                seg = box(cell, 0, int(seg_y), bar_w, int(seg_len))
            else:
                seg_len = (bar_w - _GAP * (segments - 1)) / segments
                seg = box(cell, int(i * (seg_len + _GAP)), self._legend_h, int(seg_len), bar_h)
            seg.set_style_radius(2, 0)
            fill(seg, self._off())
            self._segments.append((seg, self._zone((i + 1) / segments)))

    def set_level(self, level):
        """Light the segments that *level* (0.0 to 1.0) covers."""
        level = 0.0 if level < 0 else (1.0 if level > 1 else float(level))
        self.level = level
        lit = int(level * self.count + 0.5)
        if lit == self._lit:
            return
        low, high = (self._lit, lit) if lit > self._lit else (lit, self._lit)
        for i in range(low, high):
            seg, zone = self._segments[i]
            fill(seg, self._colour(zone) if i < lit else self._off())
        self._lit = lit

    def _zone(self, fraction):
        if fraction > _RED:
            return "red"
        if fraction > _AMBER:
            return "amber"
        return "green"

    def _colour(self, zone):
        theme = self.theme
        return {"green": theme["status_ok"], "amber": theme["amber"], "red": theme["status_bad"]}[zone]

    def _off(self):
        return self.theme["display_bezel"]
