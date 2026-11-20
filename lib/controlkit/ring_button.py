# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""A round button drawn as a thin ring, with an icon or a short text in it.

It's unfilled: the ring and the icon are one colour over whatever is behind,
and a press fills the ring faintly in that colour. ``on_press(button)`` is
called on each tap. With ``on_hold``, holding the button calls
``on_hold(button, True)`` and letting go ``on_hold(button, False)``, and a
hold isn't also a tap: fast forward on a skip button, for instance.
``hit=`` sets the size of the area a finger can land on, so a small ring is
still easy to press on a small panel.

The icon is any LVGL image source (an ``lv.image_dsc_t``, a file name or an
``lv.SYMBOL``); it's tinted with the ring's colour, so draw it white.
"""

import lvgl as lv

from ._draw import label
from ._safe import safe

_PRESSED_OPA = 46  # of 255: the faint fill a press shows


class RingButton:
    """A ring *size* pixels across, its top left at (*x*, *y*) in *parent*.

    Args:
        parent: the LVGL object to build on.
        x, y: the top left corner, in *parent*.
        size: the ring's diameter in pixels.
        theme: a controlkit theme; the ring takes its ``legend`` colour
            unless *color* is given.
        icon: an LVGL image source drawn in white, or None.
        text: a short text for the middle, when there's no icon.
        on_press: called with the button on each tap.
        on_hold: called with the button and True when a press becomes a
            hold, and with False when that hold ends.
        color: the ring's and icon's colour, ``0xRRGGBB``.
        ring: the ring's width in pixels.
        hit: the side of the square a finger can land on, at least *size*.
    """

    def __init__(self, parent, x, y, size, theme, icon=None, text="", on_press=None, color=None, ring=1, hit=0,
                 on_hold=None):
        self.theme = theme
        self.on_press = on_press
        self.on_hold = on_hold
        self.held = False  # this press became a hold: its tap is ignored
        self._holding = False
        self.enabled = True
        self.rgb = None
        b = lv.button(parent)
        b.remove_style_all()
        b.remove_flag(lv.obj.FLAG.SCROLLABLE)
        b.set_pos(x, y)
        b.set_size(size, size)
        b.set_style_radius(lv.RADIUS_CIRCLE, 0)
        b.set_style_border_width(ring, 0)
        b.set_style_bg_opa(lv.OPA.TRANSP, 0)
        b.set_style_bg_opa(_PRESSED_OPA, lv.STATE.PRESSED)
        if hit > size:
            b.set_ext_click_area((hit - size) // 2)
        self.obj = b
        self.icon = None
        self.text = None
        if icon is not None:
            self.icon = lv.image(b)
            self.icon.set_src(icon)
            self.icon.set_style_image_recolor_opa(lv.OPA.COVER, 0)
            self.icon.center()
        elif text:
            self.text = label(b, text, theme["legend"], None, 0)
            self.text.center()
        self.set_color(theme["legend"] if color is None else color)
        b.add_event_cb(safe(self._event), lv.EVENT.ALL, None)

    def _event(self, e):
        code = e.get_code()
        if code == lv.EVENT.PRESSED:
            self.held = False
        elif code == lv.EVENT.CLICKED:
            if self.enabled and not self.held and self.on_press is not None:
                self.on_press(self)
            self.held = False
        elif code == lv.EVENT.LONG_PRESSED:
            if self.enabled and self.on_hold is not None:
                self.held = self._holding = True
                self.on_hold(self, True)
        elif code in (lv.EVENT.RELEASED, lv.EVENT.PRESS_LOST):
            # The tap that follows the release of a hold is ignored above.
            if self._holding:
                self._holding = False
                self.on_hold(self, False)

    def set_color(self, rgb):
        """Draw the ring and its icon in *rgb*, ``0xRRGGBB``."""
        if rgb == self.rgb:
            return
        self.rgb = rgb
        c = lv.color_hex(rgb)
        self.obj.set_style_border_color(c, 0)
        self.obj.set_style_bg_color(c, 0)
        if self.icon is not None:
            self.icon.set_style_image_recolor(c, 0)
        if self.text is not None:
            self.text.set_style_text_color(c, 0)

    def set_icon(self, icon):
        """Show another image source in the ring, such as pause for play."""
        if self.icon is not None:
            self.icon.set_src(icon)
            self.icon.center()

    def set_enabled(self, enabled):
        """A disabled button is dimmed and ignores taps."""
        enabled = bool(enabled)
        if enabled == self.enabled:
            return
        self.enabled = enabled
        self.obj.set_style_opa(lv.OPA.COVER if enabled else 90, 0)
        if enabled:
            self.obj.add_flag(lv.obj.FLAG.CLICKABLE)
        else:
            self.obj.remove_flag(lv.obj.FLAG.CLICKABLE)
