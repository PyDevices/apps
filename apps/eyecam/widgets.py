# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Small builders that place objects the way the SquareLine export does:
centre-aligned with an (x, y) offset, hidden at creation unless asked."""

import lvgl as lv

from . import assets

CENTER = lv.ALIGN.CENTER
HIDDEN = lv.obj.FLAG.HIDDEN
FOCUSED = lv.PART.MAIN | lv.STATE.FOCUSED
GREY = 0xC9C9C9


def hide(*objs):
    for o in objs:
        if o is not None:
            o.add_flag(HIDDEN)


def show(*objs):
    for o in objs:
        if o is not None:
            o.remove_flag(HIDDEN)


def visible(obj):
    return obj is not None and not obj.has_flag(HIDDEN)


def panel(parent, w, h, x, y, radius=30, bg=GREY, opa=50, hidden=True):
    """A plain panel: the theme's padding and border width stay, its border is clear."""
    p = lv.obj(parent)
    p.set_size(w, h)
    p.align(CENTER, x, y)
    p.remove_flag(lv.obj.FLAG.SCROLLABLE)
    p.set_style_radius(radius, 0)
    p.set_style_bg_color(lv.color_hex(bg), 0)
    p.set_style_bg_opa(opa, 0)
    p.set_style_border_opa(0, 0)
    if hidden:
        p.add_flag(HIDDEN)
    return p


def bar(parent, w, x, y):
    """A popup's 6 px black divider; like the original it keeps the theme border."""
    b = lv.obj(parent)
    b.set_size(w, 6)
    b.align(CENTER, x, y)
    b.remove_flag(lv.obj.FLAG.SCROLLABLE)
    b.set_style_bg_color(lv.color_hex(0x000000), 0)
    b.set_style_bg_opa(255, 0)
    return b


def label(parent, text, x, y, font=None, color=0x000000, hidden=False):
    lb = lv.label(parent)
    lb.set_text(text)
    lb.align(CENTER, x, y)
    if font is not None:
        lb.set_style_text_font(assets.font(font) if isinstance(font, str) else font, 0)
    if color is not None:
        lb.set_style_text_color(lv.color_hex(color), 0)
    if hidden:
        lb.add_flag(HIDDEN)
    return lb


def image(parent, name, x=0, y=0, hidden=True):
    im = lv.image(parent)
    im.set_src(assets.image(name))
    im.align(CENTER, x, y)
    im.remove_flag(lv.obj.FLAG.SCROLLABLE)
    if hidden:
        im.add_flag(HIDDEN)
    return im


def pin_to_panel(images, turn):
    """Keep *images* (``(widget, x, y)`` with their 0-degree offsets from the
    centre; images or labels) beside the board's switches when the panel is
    turned by *turn* degrees: each moves to the spot that lands there and
    turns back, so it reads as at 0 degrees."""
    back = (360 - turn) % 360
    for im, x, y in images:
        if back == 90:
            x, y = -y, x
        elif back == 180:
            x, y = -x, -y
        elif back == 270:
            x, y = y, -x
        im.align(CENTER, x, y)
        # A style transform turns labels as well as images; about the middle.
        im.set_style_transform_pivot_x(lv.pct(50), 0)
        im.set_style_transform_pivot_y(lv.pct(50), 0)
        im.set_style_transform_rotation(back * 10, 0)


def popup(parent, w, h, x, y, titles, bar_w, bar_x, bar_y, body, body_font, body_x, body_y, title_color=0x000000):
    """A grey popup: one or two KoHo Bold 28 titles, a divider, a body.

    *titles* is a list of (text, x, y). Returns (panel, [title labels], body label).
    """
    p = panel(parent, w, h, x, y)
    labels = [label(p, t, tx, ty, "bold28", title_color) for (t, tx, ty) in titles]
    bar(p, bar_w, bar_x, bar_y)
    b = label(p, body, body_x, body_y, body_font)
    return p, labels, b


def row(parent, w, h, x, y, opa_focused=100):
    """A settings row: clear until it has the FOCUSED state."""
    r = lv.obj(parent)
    r.set_size(w, h)
    r.align(CENTER, x, y)
    r.remove_flag(lv.obj.FLAG.SCROLLABLE)
    r.set_style_radius(30, 0)
    r.set_style_bg_color(lv.color_hex(GREY), 0)
    r.set_style_bg_opa(0, 0)
    r.set_style_border_opa(0, 0)
    r.set_style_bg_color(lv.color_hex(GREY), FOCUSED)
    r.set_style_bg_opa(opa_focused, FOCUSED)
    return r


def focus(obj, on):
    if on:
        obj.add_state(lv.STATE.FOCUSED)
    else:
        obj.remove_state(lv.STATE.FOCUSED)


def rgb565_dsc(buf, w, h):
    """An ``image_dsc_t`` over an RGB565 buffer (keep *buf* alive)."""
    dsc = lv.image_dsc_t()
    dsc.header.magic = lv.IMAGE_HEADER_MAGIC
    dsc.header.cf = lv.COLOR_FORMAT.RGB565
    dsc.header.w = w
    dsc.header.h = h
    dsc.header.stride = w * 2
    dsc.data_size = len(buf)
    dsc.data = buf
    return dsc
