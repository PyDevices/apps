# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Hover styles for LVGL apps: a control lights up under the mouse.

LVGL marks the widget under the pointer as hovered, but its default theme
draws nothing for that. `apply` layers one outline on top of the display's
theme, for buttons, list rows, tabs, sliders and switches, so every app gets
the same look without styling its own. An outline works on any colour an app
gives a control. `Shell` calls it once, after the board's own theme is set.

Hover follows the mouse only. A finger never hovers: the display driver moves
the pointer off the screen when a touch lifts.
"""

import lvgl as lv

#: How wide the outline is, in pixels, and how strongly it shows.
WIDTH = 2
OPACITY = 200

_style = None
_applied = []  # [True] once the theme is layered, so a second call is a no-op


def _hover_style():
    global _style
    if _style is None:
        _style = lv.style_t()
        _style.init()
        _style.set_outline_width(WIDTH)
        _style.set_outline_color(lv.color_white())
        _style.set_outline_opa(OPACITY)
        _style.set_outline_pad(-1)  # half inside: a clipping parent still shows the ring
    return _style


def _apply_cb(theme, obj):
    style = _hover_style()
    if obj.has_class(lv.button_class) or obj.has_class(lv.list_button_class):
        obj.add_style(style, lv.STATE.HOVERED)
    elif obj.has_class(lv.slider_class) or obj.has_class(lv.switch_class):
        obj.add_style(style, lv.PART.KNOB | lv.STATE.HOVERED)


def apply(disp=None):
    """Add hover styles to *disp*'s theme (the default display's if omitted).

    Call it after the board's own theme is set: it wraps whatever theme is
    there. Widgets made afterwards get the styles.
    """
    disp = disp or lv.display_get_default()
    if _applied or disp is None or disp.get_theme() is None:
        return
    theme = lv.theme_create()
    theme.set_parent(disp.get_theme())
    theme.set_apply_cb(_apply_cb)
    disp.set_theme(theme)
    _applied.append(True)
