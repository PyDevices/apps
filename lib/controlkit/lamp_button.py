# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""A labelled push button with a coloured lamp in its corner.

It looks like the panel's header buttons: a legend above, a rubber cap below,
and a lamp that lights in the colour the host gives it.

- momentary (the default): each press calls ``on_press(button, True)``;
- toggle (``toggle=True``): each press flips ``button.on`` and calls
  ``on_press(button, on)``. ``set_on()`` changes the state without a call.

The lamp shows its colour while the button is on, or always for a momentary
button. ``set_lamp(rgb)`` sets the colour, and ``None`` darkens the lamp.
"""

import lvgl as lv

from ._draw import Lamp, box, fill, label, plain
from ._safe import safe

_LEGEND_H = 16
_LAMP_R = 3


class LampButton:
    """A button at (*x*, *y*) in *parent*, *width* x *height* of cap."""

    def __init__(self, parent, x, y, width, height, theme, legend="", toggle=False, lamp=None, on_press=None):
        self.theme = theme
        self.toggle = toggle
        self.on = False
        self.on_press = on_press
        self._lamp_rgb = lamp if lamp is not None else theme["amber"]
        legend_h = _LEGEND_H if legend else 0

        cell = plain(lv.obj(parent))
        cell.set_pos(x, y)
        cell.set_size(width, height + legend_h)
        self.obj = cell

        if legend:
            text = label(cell, legend.upper(), theme["header_legend"], None, 0)
            text.set_width(width)
            text.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
            text.set_pos(0, 0)

        cap = box(cell, 0, legend_h, width, height)
        cap.add_flag(lv.obj.FLAG.CLICKABLE)
        fill(cap, theme["button"], theme["button_bottom"])
        cap.set_style_radius(4, 0)
        cap.set_style_border_width(1, 0)
        cap.set_style_border_color(lv.color_hex(theme["pad_edge"]), 0)
        cap.set_style_shadow_width(4, 0)
        cap.set_style_shadow_offset_y(2, 0)
        cap.set_style_shadow_opa(170, 0)
        cap.set_style_shadow_color(lv.color_hex(0), 0)
        cap.set_style_translate_y(1, lv.STATE.PRESSED)
        cap.set_style_shadow_offset_y(0, lv.STATE.PRESSED)
        cap.add_event_cb(safe(self._on_clicked), lv.EVENT.CLICKED, None)
        self.cap = cap

        self.lamp = Lamp(cell, width - _LAMP_R - 4, legend_h + _LAMP_R + 4, _LAMP_R, theme)
        self._show()

    # ---- what the host calls -------------------------------------------------

    def set_lamp(self, rgb):
        """Set the lamp's colour; None darkens it. A toggle's lamp shows only while it is on."""
        self._lamp_rgb = rgb
        self._show()

    def set_on(self, on):
        """Set the toggle state without calling ``on_press``."""
        self.on = bool(on)
        self._show()

    # ---- drawing and input ---------------------------------------------------

    def _show(self):
        lit = self.on if self.toggle else True
        self.lamp.set(self._lamp_rgb if lit else None)

    def _on_clicked(self, _event):
        if self.toggle:
            self.on = not self.on
            self._show()
            value = self.on
        else:
            value = True
        if self.on_press is not None:
            self.on_press(self, value)
