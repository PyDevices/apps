# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Glass controls: buttons that float over an app, see-through so the app
shows behind them.

The colours, the see-through amounts and the size are here once, for every
control drawn this way: Huey's Perch's dock and the corner Home button an app
without the status bar gets.
"""

import lvgl as lv
from icons import lvgl as lvicons

#: The glass behind a control, and how much of it shows (of 255).
GLASS = 0x0B2A4A
GLASS_OPA = 170
#: A key on a pane of glass: a light tint of white, and how much of it shows.
KEY_OPA = 36
#: A control while it's pressed.
PRESSED = 0xC4DC4C
PRESSED_OPA = 150
#: The icon on a control, in pixels.
ICON = 24


def side(w, h):
    """How big a control is on a *w* by *h* screen, in pixels: an eighth of
    the shorter side, from 34 to 56."""
    return max(34, min(56, min(w, h) // 8))


def pane(obj):
    """Make *obj* a pane of glass: its own styles off, the glass behind it."""
    obj.remove_style_all()
    obj.set_style_bg_color(lv.color_hex(GLASS), 0)
    obj.set_style_bg_opa(GLASS_OPA, 0)
    obj.remove_flag(lv.obj.FLAG.SCROLLABLE)
    return obj


def _pressed(obj):
    obj.set_style_bg_color(lv.color_hex(PRESSED), lv.STATE.PRESSED)
    obj.set_style_bg_opa(PRESSED_OPA, lv.STATE.PRESSED)
    obj.add_flag(lv.obj.FLAG.CLICKABLE)


def key(obj, icon):
    """Make *obj* a key on a pane: a light tint over the glass, lit while
    pressed, with *icon* in white at its middle. Returns the icon."""
    obj.remove_style_all()
    obj.set_style_bg_color(lv.color_hex(0xFFFFFF), 0)
    obj.set_style_bg_opa(KEY_OPA, 0)
    _pressed(obj)
    obj.remove_flag(lv.obj.FLAG.SCROLLABLE)
    return _icon(obj, icon)


def button(parent, icon, size, radius=None):
    """A square glass button of its own, *size* pixels a side, on *parent*,
    with *icon* in white at its middle. *radius* rounds its corners (a
    quarter of *size* by default). A finger can press it from a quarter of
    *size* outside it, the room a key has on a pane. Returns the button."""
    b = pane(lv.obj(parent))
    _pressed(b)
    b.set_size(size, size)
    b.set_style_radius(size // 4 if radius is None else radius, 0)
    b.set_ext_click_area(size // 4)
    _icon(b, icon)
    return b


def _icon(obj, icon):
    image = lvicons.image(obj, icon, ICON, lv.color_white())
    image.center()
    image.remove_flag(lv.obj.FLAG.CLICKABLE)
    return image
