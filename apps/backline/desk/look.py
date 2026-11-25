# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The desk view's colours, fonts and the few widgets it styles itself.

Every widget here sets its own colours, so the desk looks the same under
any LVGL theme: on the box's own screen inside the shell, or alone on a
remote screen.
"""

import lvgl as lv
from icons import lvgl as lvicons

from .. import art, glyphs

BG = 0x0A0D12
PANEL = 0x121821
RAISED = 0x1A2230
LINE = 0x2A3444
TEXT = 0xDDE3EC
DIM = 0x8792A5
FAINT = 0x5A6578
AMBER = art.AMBER
BAD = 0xFF4D6D
ROLE_COLORS = art.ROLE_COLORS
FONT_SIZES = (14, 16, 24, 32, 40)


def color(rgb):
    return lv.color_hex(rgb)


def font(px):
    """The largest built-in font no taller than ``px``, else the smallest."""
    best = None
    for size in FONT_SIZES:
        f = getattr(lv, "font_montserrat_%d" % size, None)
        if f is not None and (best is None or size <= px):
            best = f
    return best or lv.font_get_default()


def plain(obj):
    """``obj`` with no theme style, no scrolling and no clicks."""
    obj.remove_style_all()
    obj.remove_flag(lv.obj.FLAG.SCROLLABLE)
    obj.remove_flag(lv.obj.FLAG.CLICKABLE)
    return obj


def box(parent, x, y, w, h, bg=PANEL, radius=8, border=LINE, opa=255):
    """A filled rectangle with a rounded edge."""
    b = plain(lv.obj(parent))
    b.set_pos(int(x), int(y))
    b.set_size(int(w), int(h))
    b.set_style_bg_color(color(bg), 0)
    b.set_style_bg_opa(opa, 0)
    b.set_style_radius(radius, 0)
    if border is not None:
        b.set_style_border_color(color(border), 0)
        b.set_style_border_width(1, 0)
    return b


def text(parent, value, fnt, rgb=TEXT, width=None, align=None):
    """A label; with ``width``, one line ending in dots when it's too long."""
    lbl = lv.label(parent)
    lbl.set_style_text_font(fnt, 0)
    lbl.set_style_text_color(color(rgb), 0)
    lbl.set_text(value)
    if width is not None:
        lbl.set_width(int(width))
        lbl.set_height(fnt.line_height)
        lbl.set_long_mode(lv.label.LONG_MODE.DOTS)
    if align is not None:
        lbl.set_style_text_align(align, 0)
    return lbl


def heading(parent, value, fnt, x, y, role=None):
    """A small, spaced, dim heading over a group of controls, after the icon
    for ``role`` (`glyphs.ICONS`) when one is given."""
    lbl = text(parent, value.upper(), fnt, DIM)
    lbl.set_style_text_letter_space(2, 0)
    lbl.set_pos(int(x), int(y))
    if role is not None:
        size = fnt.line_height + 4
        icon = glyphs.show(parent, role, size, color(DIM))
        icon.set_pos(int(x) - 2, int(y) - 2)
        lbl.set_x(int(x) + size + 2)
    return lbl


def button(parent, x, y, w, h, label=None, icon=None, fnt=None, on_click=None, radius=8, role=None):
    """A flat button: ``label`` text, an ``icon`` from the icons package, or
    the icon for ``role`` (`glyphs.ICONS`).

    Returns:
        The button; its child 0 is the label or the icon.
    """
    b = box(parent, x, y, w, h, RAISED, radius, LINE)
    b.add_flag(lv.obj.FLAG.CLICKABLE)
    b.set_style_bg_color(color(LINE), lv.STATE.PRESSED)
    b.set_style_border_color(color(AMBER), lv.STATE.PRESSED)
    if icon is not None or role is not None:
        size = int(min(w, h) * 0.62)
        if role is not None:
            img = glyphs.show(b, role, size, color(TEXT))
        else:
            img = lvicons.image(b, icon, size, color(TEXT))
        img.center()
    else:
        lbl = text(b, label or "", fnt or font(16))
        lbl.center()
    if on_click is not None:
        b.add_event_cb(lambda _e: on_click(), lv.EVENT.CLICKED, None)
    return b


def select(btn, on, rgb=AMBER):
    """Show ``btn`` (made by `button`) chosen, or not."""
    btn.set_style_border_color(color(rgb if on else LINE), 0)
    btn.set_style_border_width(2 if on else 1, 0)
    btn.set_style_bg_color(color(art.mix(rgb, RAISED, 0.78) if on else RAISED), 0)


def slider(parent, x, y, w, h, lo, hi, on_change):
    """A slider in the desk's colours; vertical when taller than wide.
    ``on_change(value)`` runs as it moves."""
    s = lv.slider(parent)
    s.set_pos(int(x), int(y))
    s.set_size(int(w), int(h))
    s.set_range(lo, hi)
    s.set_style_bg_color(color(LINE), lv.PART.MAIN)
    s.set_style_bg_opa(255, lv.PART.MAIN)
    s.set_style_radius(4, lv.PART.MAIN)
    s.set_style_bg_color(color(AMBER), lv.PART.INDICATOR)
    s.set_style_bg_opa(255, lv.PART.INDICATOR)
    s.set_style_radius(4, lv.PART.INDICATOR)
    s.set_style_bg_color(color(TEXT), lv.PART.KNOB)
    s.set_style_bg_opa(255, lv.PART.KNOB)
    s.set_style_pad_all(max(2, int(min(w, h) // 3)), lv.PART.KNOB)
    s.set_style_shadow_width(0, lv.PART.KNOB)
    s.set_style_outline_width(0, lv.PART.MAIN)
    s.set_style_outline_width(0, lv.PART.KNOB)
    s.add_event_cb(lambda _e: on_change(s.get_value()), lv.EVENT.VALUE_CHANGED, None)
    return s


def dropdown(parent, x, y, w, h, fnt, on_pick):
    """A dropdown in the desk's colours; ``on_pick(index)`` when one is chosen."""
    d = lv.dropdown(parent)
    d.set_pos(int(x), int(y))
    d.set_size(int(w), int(h))
    d.set_style_text_font(fnt, 0)
    d.set_style_bg_color(color(RAISED), 0)
    d.set_style_text_color(color(TEXT), 0)
    d.set_style_border_color(color(LINE), 0)
    d.set_style_border_width(1, 0)
    d.set_style_radius(8, 0)
    d.set_style_pad_ver(max(2, (int(h) - fnt.line_height) // 2 - 1), 0)
    lst = d.get_list()
    lst.set_style_text_font(fnt, 0)
    lst.set_style_bg_color(color(PANEL), 0)
    lst.set_style_text_color(color(TEXT), 0)
    lst.set_style_border_color(color(LINE), 0)
    lst.set_style_bg_color(color(art.mix(AMBER, PANEL, 0.6)), lv.PART.SELECTED | lv.STATE.CHECKED)
    d.add_event_cb(lambda _e: on_pick(d.get_selected()), lv.EVENT.VALUE_CHANGED, None)
    return d
