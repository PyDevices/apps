# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""A grid of illuminated pads, each lit in any colour, as a step or session grid.

``set_color(index, rgb)`` lights pad *index* (row-major: row * cols + column)
and ``None`` puts it out. A press calls ``on_press(grid, index)``. Only the
pads that change are repainted.

For pads that play, ``on_down(grid, index)`` is called the moment a finger
lands and ``on_up(grid, index)`` when it lifts or slides off, so a note can
start and end with the touch. ``set_label(index, text)`` prints a legend on
a pad, and ``pad(index)`` is the pad's own object, to read where it is.
"""

import lvgl as lv

from ._draw import box, fill, label, plain
from ._safe import safe


class PadGrid:
    """A grid of *cols* x *rows* pads in *width* x *height* at (*x*, *y*) in *parent*."""

    def __init__(self, parent, x, y, width, height, theme, cols=8, rows=2, gap=4, on_press=None,
                 on_down=None, on_up=None):
        self.theme = theme
        self.cols = cols
        self.rows = rows
        self.on_press = on_press
        self.on_down = on_down
        self.on_up = on_up
        self._labels = {}
        self.colors = [None] * (cols * rows)

        cell = plain(lv.obj(parent))
        cell.set_pos(x, y)
        cell.set_size(width, height)
        self.obj = cell

        pad_w = (width - gap * (cols - 1)) // cols
        pad_h = (height - gap * (rows - 1)) // rows
        self._pads = []
        for row in range(rows):
            for col in range(cols):
                pad = box(cell, col * (pad_w + gap), row * (pad_h + gap), pad_w, pad_h)
                pad.add_flag(lv.obj.FLAG.CLICKABLE)
                pad.set_style_radius(3, 0)
                pad.set_style_border_width(1, 0)
                pad.set_style_border_color(lv.color_hex(theme["pad_edge"]), 0)
                pad.set_style_translate_y(1, lv.STATE.PRESSED)
                index = len(self._pads)
                pad.add_event_cb(safe(self._handler(index)), lv.EVENT.CLICKED, None)
                if on_down is not None or on_up is not None:
                    pad.remove_flag(lv.obj.FLAG.GESTURE_BUBBLE)  # a slide is a held pad, not a swipe
                    pad.add_event_cb(safe(self._edge(index, True)), lv.EVENT.PRESSED, None)
                    pad.add_event_cb(safe(self._edge(index, False)), lv.EVENT.RELEASED, None)
                    pad.add_event_cb(safe(self._edge(index, False)), lv.EVENT.PRESS_LOST, None)
                self._pads.append(pad)
                self._paint(index)

    def set_color(self, index, rgb):
        """Light pad *index* in *rgb*, or put it out with None."""
        if not 0 <= index < len(self._pads):
            raise IndexError("pad %d is not in a %dx%d grid" % (index, self.cols, self.rows))
        if self.colors[index] == rgb:
            return
        self.colors[index] = rgb
        self._paint(index)

    def set_label(self, index, text, rgb=None):
        """Print *text* in the middle of pad *index*, in *rgb* (the theme's pad text by default)."""
        lbl = self._labels.get(index)
        if lbl is None:
            lbl = label(self._pads[index], text, rgb if rgb is not None else self.theme["pad_text"], None, 0)
            lbl.center()
            self._labels[index] = lbl
        else:
            lbl.set_text(text)
            if rgb is not None:
                lbl.set_style_text_color(lv.color_hex(rgb), 0)
        return lbl

    def pad(self, index):
        """Pad *index*'s LVGL object."""
        return self._pads[index]

    def _paint(self, index):
        rgb = self.colors[index]
        pad = self._pads[index]
        if rgb is None:
            fill(pad, self.theme["pad"], self.theme["pad_bottom"])
            pad.set_style_shadow_width(0, 0)
        else:
            fill(pad, rgb)
            pad.set_style_shadow_width(6, 0)
            pad.set_style_shadow_color(lv.color_hex(rgb), 0)
            pad.set_style_shadow_opa(160, 0)

    def _handler(self, index):
        def handle(_event):
            if self.on_press is not None:
                self.on_press(self, index)

        return handle

    def _edge(self, index, down):
        def handle(_event):
            cb = self.on_down if down else self.on_up
            if cb is not None:
                cb(self, index)

        return handle
