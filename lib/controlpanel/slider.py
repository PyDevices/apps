# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""A fader: a groove, a cap that slides along it, and an optional lamp.

Vertical by default, with the lamp above the groove; horizontal puts the lamp
past its right end. Values run 0 to 127, as every control here does.

- drag the cap along the groove; the value follows the pointer, to the pixel;
- the wheel and the arrow keys step it one at a time, Home and End go to the ends;
- ``set_value()`` shows a value without calling ``on_change``, so a host that
  moves the slider never hears its own echo back.

The slider's ``obj`` takes focus like an encoder, so add it to a group to
turn it from a wheel. ``set_led(rgb)`` lights the lamp, and ``None`` darkens
it; a slider built without ``led=True`` has no lamp and ignores the call.
"""

import lvgl as lv

from ._draw import Lamp, box, fill, label, plain
from ._safe import safe

MAX = 127
_LEGEND_H = 16
_LAMP_R = 4
_LAMP_SPACE = 14


class Slider:
    """A fader at (*x*, *y*) in *parent*, *width* x *height*, edited 0 to 127."""

    def __init__(self, parent, x, y, width, height, theme, legend="", vertical=True, value=0, led=False, on_change=None):
        self.theme = theme
        self.vertical = vertical
        self.value = 0
        self.on_change = on_change
        self._drag = None
        self.legend_h = _LEGEND_H if legend else 0

        cell = plain(lv.obj(parent), clickable=True)
        cell.set_pos(x, y)
        cell.set_size(width, height)
        self.obj = cell
        self.width = width
        self.height = height

        if legend:
            text = label(cell, legend.upper(), theme["legend"], None, 1)
            text.set_width(width)
            text.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
            text.set_pos(0, 0)
            self.legend = text

        lamp_space = _LAMP_SPACE if led else 0
        if vertical:
            self.cap_w = min(width - 6, 34)
            self.cap_h = 12
            cx = width // 2
            top = self.legend_h + lamp_space + self.cap_h // 2 + 2
            bottom = height - self.cap_h // 2 - 2
            self._span = (top, bottom)
            self._cx = cx
            self._groove(cell, box(cell, cx - max(2, width // 16), top, max(4, width // 8), bottom - top))
            if led:
                self.lamp = Lamp(cell, cx, self.legend_h + _LAMP_R + 2, _LAMP_R, theme)
        else:
            self.cap_w = 12
            self.cap_h = min(height - self.legend_h - 6, 34)
            cy = self.legend_h + (height - self.legend_h) // 2
            left = self.cap_w // 2 + 2
            right = width - self.cap_w // 2 - 2 - lamp_space
            self._span = (left, right)
            self._cy = cy
            self._groove(cell, box(cell, left, cy - max(2, self.cap_h // 6), right - left, max(4, self.cap_h // 3)))
            if led:
                self.lamp = Lamp(cell, width - _LAMP_R - 2, cy, _LAMP_R, theme)
        if not led:
            self.lamp = None

        self.cap = box(cell, 0, 0, self.cap_w, self.cap_h)
        fill(self.cap, theme["knob_cap_light"], theme["knob_cap"])
        self.cap.set_style_radius(3, 0)
        self.cap.set_style_border_width(1, 0)
        self.cap.set_style_border_color(lv.color_hex(theme["pad_edge"]), 0)
        line = box(self.cap, 2, self.cap_h // 2 - 1, self.cap_w - 4, 2) if vertical else box(self.cap, self.cap_w // 2 - 1, 2, 2, self.cap_h - 4)
        fill(line, theme["pointer"])

        cell.add_event_cb(safe(self._on_pressed), lv.EVENT.PRESSED, None)
        cell.add_event_cb(safe(self._on_pressing), lv.EVENT.PRESSING, None)
        cell.add_event_cb(safe(self._on_released), lv.EVENT.RELEASED, None)
        cell.add_event_cb(safe(self._on_released), lv.EVENT.PRESS_LOST, None)
        cell.add_event_cb(safe(self._on_key), lv.EVENT.KEY, None)
        cell.add_event_cb(safe(self._on_focus), lv.EVENT.FOCUSED, None)
        cell.add_event_cb(safe(self._on_defocus), lv.EVENT.DEFOCUSED, None)
        self._show(max(0, min(MAX, int(value))))

    def _groove(self, cell, groove):
        fill(groove, self.theme["display_bezel"], self.theme["pad_edge"])
        groove.set_style_radius(2, 0)

    # ---- what the host calls -------------------------------------------------

    def set_value(self, value):
        """Show *value* (0 to 127) without calling ``on_change``."""
        self._show(0 if value < 0 else (MAX if value > MAX else int(value)))

    def set_led(self, rgb):
        """Light the lamp in *rgb*, or darken it with None. No-op without a lamp."""
        if self.lamp is not None:
            self.lamp.set(rgb)

    # ---- drawing -------------------------------------------------------------

    def _show(self, value):
        self.value = value
        start, end = self._span
        t = value / MAX
        if self.vertical:
            y = end - t * (end - start)
            self.cap.set_pos(self._cx - self.cap_w // 2, int(y - self.cap_h / 2))
        else:
            x = start + t * (end - start)
            self.cap.set_pos(int(x - self.cap_w / 2), self._cy - self.cap_h // 2)

    def _change(self, value):
        value = 0 if value < 0 else (MAX if value > MAX else int(value))
        if value == self.value:
            return
        self._show(value)
        if self.on_change is not None:
            self.on_change(self, value)

    # ---- input ---------------------------------------------------------------

    def _point(self):
        indev = lv.indev_active()
        if indev is None:
            return None
        p = lv.point_t()
        indev.get_point(p)
        return p.x, p.y

    def _on_pressed(self, _event):
        point = self._point()
        if point is not None:
            self._drag = (point[0], point[1], self.value)

    def _on_released(self, _event):
        self._drag = None

    def _on_pressing(self, _event):
        point = self._point()
        if point is None:
            return
        if self._drag is None:
            # The first report of a press anchors the drag where the pointer is.
            self._drag = (point[0], point[1], self.value)
        x0, y0, start = self._drag
        low, high = self._span
        travel = max(1, high - low)
        if self.vertical:
            moved = (y0 - point[1]) * MAX / travel
        else:
            moved = (point[0] - x0) * MAX / travel
        self._change(start + int(moved))

    def _on_key(self, event):
        key = event.get_key()
        if key in (lv.KEY.RIGHT, lv.KEY.UP):
            self._change(self.value + 1)
        elif key in (lv.KEY.LEFT, lv.KEY.DOWN):
            self._change(self.value - 1)
        elif key == lv.KEY.HOME:
            self._change(0)
        elif key == lv.KEY.END:
            self._change(MAX)

    def _on_focus(self, _event):
        if self.legend_h:
            self.legend.set_style_text_color(lv.color_hex(self.theme["legend_lit"]), 0)

    def _on_defocus(self, _event):
        if self.legend_h:
            self.legend.set_style_text_color(lv.color_hex(self.theme["legend"]), 0)
