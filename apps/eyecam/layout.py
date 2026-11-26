# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Where the 240x240 camera layout sits on the panel in front of it.

The pages are drawn for a 240x240 screen and never change. On a bigger panel
each page's objects go in a 240x240 `stage`, which is enlarged by a whole
number and centred, so one layout looks the same everywhere. On a 240x240
panel the stage is the screen and nothing moves.
"""

try:
    import lvgl as lv
except ImportError:
    lv = None

BASE = 240
UNIT = 256  # LVGL's transform scale: 256 is 1x


def scale_for(width, height, base=BASE):
    """The whole-number enlargement that fits *base* x *base* on the panel.

    A panel smaller than *base* in either direction still gets 1: the layout
    is not shrunk.
    """
    return max(1, min(width // base, height // base))


def stage(screen, width, height):
    """A 240x240 container on *screen*, enlarged and centred for the panel.

    Returns ``(container, scale)``. Draw the page's objects in the container.
    """
    scale = scale_for(width, height)
    if (width, height) != (BASE, BASE):
        screen.set_style_bg_color(lv.color_hex(0x000000), 0)  # the border round the stage
        screen.set_style_bg_opa(255, 0)
    box = lv.obj(screen)
    box.remove_style_all()
    box.set_size(BASE, BASE)
    box.align(lv.ALIGN.CENTER, 0, 0)
    box.remove_flag(lv.obj.FLAG.SCROLLABLE)
    if scale > 1:
        box.set_style_transform_pivot_x(BASE // 2, 0)
        box.set_style_transform_pivot_y(BASE // 2, 0)
        box.set_style_transform_scale(UNIT * scale, 0)
    return box, scale
