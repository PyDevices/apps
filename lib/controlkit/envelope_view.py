# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""A rate and level envelope drawn as a curve, with the edited stage lit and a playhead.

Each stage moves to its level at its rate: a higher rate draws a shorter
segment, and a higher level a taller one. The curve starts at the last
stage's level, which is where an envelope of this kind rests between notes.
With ``sustain=i`` the level of stage *i* holds, drawn as a dashed line,
until the stages after it run.

- ``set_values(rates, levels)`` redraws the whole curve, and ``set_rate()``
  and ``set_level()`` move one stage;
- ``set_selected(i)`` lights the stage being edited, and ``None`` lights none;
- ``set_position(stage, fraction)`` shows a playhead part of the way through
  a stage, and ``set_position(None)`` hides it.

The view only displays. It takes no touches and no focus, so the encoders
or sliders beside it do the editing.
"""

import lvgl as lv

from ._draw import box, fill, label, plain, polyline, route
from ._safe import safe

_LEGEND_H = 16
_PAD = 6
#: The part of a stage's slot that even the fastest rate still draws.
_SHORTEST = 0.15
#: How wide the held part is, in stage slots.
_HOLD = 0.6


class EnvelopeView:
    """An envelope of *stages* rates and levels at (*x*, *y*) in *parent*, *width* x *height*.

    Rates and levels run 0 to *maximum*. *sustain* is the stage whose level
    holds, or None for an envelope that never waits. *rates* and *levels*
    are the values to open on; without them every rate is half and the
    curve is flat at zero.
    """

    def __init__(self, parent, x, y, width, height, theme, stages=4, sustain=None, maximum=127, legend="",
                 rates=None, levels=None):
        if stages < 1:
            raise ValueError("an envelope needs at least one stage")
        if sustain is not None and not 0 <= sustain < stages:
            raise ValueError("sustain stage %d is not one of %d stages" % (sustain, stages))
        self.theme = theme
        self.stages = stages
        self.sustain = sustain
        self.maximum = maximum
        self.selected = None
        self.position = None
        self.rates = [maximum // 2] * stages
        self.levels = [0] * stages

        cell = plain(lv.obj(parent))
        cell.set_pos(x, y)
        cell.set_size(width, height)
        self.obj = cell
        legend_h = _LEGEND_H if legend else 0
        if legend:
            text = label(cell, legend.upper(), theme["legend"], None, 1)
            text.set_width(width)
            text.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
            text.set_pos(0, 0)

        window = box(cell, 0, legend_h, width, height - legend_h)
        fill(window, theme["display_bg"])
        window.set_style_radius(3, 0)
        window.set_style_border_width(1, 0)
        window.set_style_border_color(lv.color_hex(theme["display_bezel"]), 0)
        self._window = window
        pad = min(_PAD, max(1, min(width, height - legend_h) // 8))
        self._left = pad
        self._top = legend_h + pad
        self._plot_w = max(2, width - 2 * pad)
        self._plot_h = max(2, height - legend_h - 2 * pad)
        self._thick = 3 if min(self._plot_w, self._plot_h) >= 60 else 2
        dot = self._thick + 3

        floor = box(cell, self._left, self._top + self._plot_h - 1, self._plot_w, 1)
        fill(floor, theme["dot_off"])
        self._drops = []
        self._lines = []
        self._dots = []
        self._points = []
        self._kept = {}
        for _ in range(stages):
            drop = box(cell, 0, 0, 1, 1)
            fill(drop, theme["dot_off"])
            self._drops.append(drop)
        self._hold = self._line(cell)
        self._hold.set_style_line_dash_width(4, 0)
        self._hold.set_style_line_dash_gap(3, 0)
        for _ in range(stages):
            self._lines.append(self._line(cell))
        for _ in range(stages + 1):
            mark = box(cell, 0, 0, dot, dot)
            mark.set_style_radius(lv.RADIUS_CIRCLE, 0)
            self._dots.append(mark)
        self._dot = dot

        self._cursor = box(cell, 0, self._top, 1, self._plot_h)
        fill(self._cursor, theme["amber"])
        self._head = box(cell, 0, 0, dot + 2, dot + 2)
        fill(self._head, theme["amber"])
        self._head.set_style_radius(lv.RADIUS_CIRCLE, 0)
        self._cursor.add_flag(lv.obj.FLAG.HIDDEN)
        self._head.add_flag(lv.obj.FLAG.HIDDEN)

        # LVGL holds this callback, and so the view and its lines' points,
        # for as long as the object lives, even if the host keeps neither.
        cell.add_event_cb(safe(self._on_delete), lv.EVENT.DELETE, None)

        if rates is not None or levels is not None:
            self.set_values(self.rates if rates is None else rates, self.levels if levels is None else levels)
        else:
            self._draw()

    def _on_delete(self, _event):
        self._kept = {}

    def _line(self, cell):
        line, _ = polyline(cell, [(0, 0), (0, 0)], self.theme["dot_on"], self._thick - 1)
        line.set_style_line_rounded(True, 0)
        return line

    # ---- what the host calls -------------------------------------------------

    def set_values(self, rates, levels):
        """Draw the envelope with these *rates* and *levels*, one of each per stage."""
        if len(rates) != self.stages or len(levels) != self.stages:
            raise ValueError("an envelope of %d stages needs %d rates and %d levels" % ((self.stages,) * 3))
        self.rates = [self._clamp(value) for value in rates]
        self.levels = [self._clamp(value) for value in levels]
        self._draw()

    def set_rate(self, stage, value):
        """Give *stage* the rate *value*."""
        self._check(stage)
        self.rates[stage] = self._clamp(value)
        self._draw()

    def set_level(self, stage, value):
        """Give *stage* the level *value*."""
        self._check(stage)
        self.levels[stage] = self._clamp(value)
        self._draw()

    def set_selected(self, stage):
        """Light *stage* as the one being edited, or none with None."""
        if stage is not None:
            self._check(stage)
        if stage == self.selected:
            return
        self.selected = stage
        self._colour()

    def set_position(self, stage, fraction=0.0):
        """Show the playhead *fraction* (0.0 to 1.0) of the way through *stage*.

        On the sustain stage a fraction from 1.0 to 2.0 carries on along the
        held level. ``set_position(None)`` hides the playhead.
        """
        if stage is None:
            self.position = None
        else:
            self._check(stage)
            most = 2.0 if stage == self.sustain else 1.0
            self.position = (stage, 0.0 if fraction < 0 else (most if fraction > most else float(fraction)))
        self._place()

    def points(self):
        """Where the curve turns, as (x, y) in this control: its start, then the end of each stage."""
        return list(self._points)

    def playhead(self):
        """Where the playhead is, as (x, y) in this control, or None when it is hidden."""
        if self.position is None:
            return None
        stage, fraction = self.position
        x0, y0 = self._starts[stage]
        x1, y1 = self._points[stage + 1]
        if fraction > 1.0:
            return x1 + (fraction - 1.0) * self._hold_w, y1
        return x0 + fraction * (x1 - x0), y0 + fraction * (y1 - y0)

    # ---- drawing -------------------------------------------------------------

    def _check(self, stage):
        if not 0 <= stage < self.stages:
            raise IndexError("stage %d is not one of %d" % (stage, self.stages))

    def _clamp(self, value):
        return 0 if value < 0 else (self.maximum if value > self.maximum else int(value))

    def _y(self, level):
        return self._top + (self._plot_h - 1) * (1.0 - level / self.maximum)

    def _draw(self):
        slots = self.stages + (_HOLD if self.sustain is not None else 0)
        slot = self._plot_w / slots
        self._hold_w = slot * _HOLD
        x = float(self._left)
        y = self._y(self.levels[-1])
        self._points = [(x, y)]
        # Where each stage begins: the end of the one before, or of its hold.
        self._starts = []
        for stage in range(self.stages):
            self._starts.append((x, y))
            x1 = x + slot * (_SHORTEST + (1.0 - _SHORTEST) * (1.0 - self.rates[stage] / self.maximum))
            y1 = self._y(self.levels[stage])
            self._set(stage, self._lines[stage], x, y, x1, y1)
            self._points.append((x1, y1))
            x, y = x1, y1
            if stage == self.sustain:
                self._set(-1, self._hold, x, y, x + self._hold_w, y)
                x += self._hold_w
        if self.sustain is None:
            self._hold.add_flag(lv.obj.FLAG.HIDDEN)
        half = self._dot // 2
        bottom = self._top + self._plot_h - 1
        for i, (px, py) in enumerate(self._points):
            self._dots[i].set_pos(int(px + 0.5) - half, int(py + 0.5) - half)
            if i:
                drop = self._drops[i - 1]
                drop.set_pos(int(px + 0.5), int(py + 0.5))
                drop.set_size(1, max(1, bottom - int(py + 0.5)))
        self._colour()
        self._place()

    def _set(self, key, line, x0, y0, x1, y1):
        # The line points into this buffer, so it stays here while the line lives.
        self._kept[key] = route(line, [(x0, y0), (x1, y1)])

    def _colour(self):
        theme = self.theme
        for stage in range(self.stages):
            lit = stage == self.selected
            line = self._lines[stage]
            line.set_style_line_color(lv.color_hex(theme["pointer"] if lit else theme["dot_on"]), 0)
            line.set_style_line_width(self._thick if lit else self._thick - 1, 0)
        for i, mark in enumerate(self._dots):
            lit = self.selected is not None and i == self.selected + 1
            fill(mark, theme["pointer"] if lit else theme["dot_on"])

    def _place(self):
        spot = self.playhead()
        if spot is None:
            self._cursor.add_flag(lv.obj.FLAG.HIDDEN)
            self._head.add_flag(lv.obj.FLAG.HIDDEN)
            return
        x, y = int(spot[0] + 0.5), int(spot[1] + 0.5)
        half = (self._dot + 2) // 2
        self._cursor.set_pos(x, self._top)
        self._head.set_pos(x - half, y - half)
        self._cursor.remove_flag(lv.obj.FLAG.HIDDEN)
        self._head.remove_flag(lv.obj.FLAG.HIDDEN)
