# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Colours, spacing and the type scale, defined once, as shared LVGL styles.

Every widget takes its look from a handful of shared styles; a pressed,
checked or selected look is a state on the same style, never a restyle
(restyling objects one by one is what made a board UI take 600 ms a tap).
"""

import lvgl as lv

import iconkit
from iconkit import lvicons

import _icons_18
import _icons_24
import _icons_36
import _icons_48
import fonts

BG = 0x0E1116          # the window
PANEL = 0x161A22       # regions
RAISED = 0x1F2430      # controls, rows
HOVER = 0x283042       # a button under the mouse
PRESSED = 0x313B52     # a button held down
LINE = 0x2A3140        # borders, grid lines
LINE_BAR = 0x3C4558    # bar lines on the grid
TEXT = 0xE6E9EF
MUTED = 0x8A93A6
ACCENT = 0xFF7A45      # play head, selection
ACCENT_HOVER = 0xFF9466  # a checked button under the mouse
REC = 0xE5484D
OK = 0x46A758
WARN = 0xF5A524

# One colour per track, in order.
TRACK_COLOURS = (0xFF7A45, 0x3DB4F2, 0xB28DFF, 0x46D39A, 0xF5C542, 0xF26CA7, 0x5AD2D2, 0xA3B4C8)

S = 1.0                # the layout's scale, set by setup()
_styles = {}

# Icons come from iconkit: its shared 24 and 48 px sets plus Ostinato's own
# modules for the rest (scripts/make_icons.py). Material's PNGs, which the
# modules are built from, come in these four sizes.
ICON_SIZES = (18, 24, 36, 48)
for _m in (_icons_18, _icons_24, _icons_36, _icons_48):
    iconkit.add(_m)
_icon_size = 24        # the size icons draw at, set by setup()


def c(hexval):
    return lv.color_hex(hexval)


def px(n):
    """A design size (at 1920x1080) in pixels at the current scale."""
    return max(1, int(n * S + 0.5))


def track_colour(index):
    return TRACK_COLOURS[index % len(TRACK_COLOURS)]


def _style(**props):
    st = lv.style_t()
    st.init()
    for name, value in props.items():
        getattr(st, "set_" + name)(value)
    return st


def setup(scale):
    """Build the shared styles for this scale. Call once fonts are loaded."""
    global S
    S = scale
    _styles["panel"] = _style(bg_color=c(PANEL), bg_opa=255, radius=0, border_width=0,
                              pad_all=0, shadow_width=0)
    _styles["panel_edge"] = _style(border_color=c(LINE), border_width=1)
    _styles["button"] = _style(bg_color=c(RAISED), bg_opa=255, radius=px(6), border_width=0,
                               shadow_width=0, pad_all=px(4), text_color=c(TEXT), text_font=fonts.t(px(16)))
    _styles["button_hovered"] = _style(bg_color=c(HOVER))
    _styles["button_pressed"] = _style(bg_color=c(PRESSED))
    _styles["button_checked"] = _style(bg_color=c(ACCENT), text_color=c(BG))
    # LVGL ranks HOVERED above CHECKED: without this, a checked button under
    # the mouse would lose its colour.
    _styles["button_checked_hovered"] = _style(bg_color=c(ACCENT_HOVER), text_color=c(BG))
    _styles["text"] = _style(text_color=c(TEXT), text_font=fonts.t(px(16)))
    _styles["muted"] = _style(text_color=c(MUTED), text_font=fonts.t(px(14)))
    _styles["title"] = _style(text_color=c(TEXT), text_font=fonts.t(px(20)))
    _styles["big"] = _style(text_color=c(TEXT), text_font=fonts.t(px(28)))
    global _icon_size
    _icon_size = ICON_SIZES[0]
    for size in ICON_SIZES:     # the largest size that fits in a 24 px design icon
        if size <= px(24):
            _icon_size = size


def style(obj, *names, selector=0):
    for n in names:
        obj.add_style(_styles[n], selector)


def panel(parent, rect, edge=True):
    x, y, w, h = rect
    p = lv.obj(parent)
    p.remove_style_all()
    style(p, "panel")
    if edge:
        style(p, "panel_edge")
    p.set_pos(x, y)
    p.set_size(w, h)
    p.remove_flag(lv.OBJ_FLAG.SCROLLABLE)
    return p


def box(parent, x, y, w, h, colour=None, radius=0):
    """A plain rectangle: no scrolling, no theme padding."""
    b = lv.obj(parent)
    b.remove_style_all()
    b.set_pos(x, y)
    b.set_size(w, h)
    if colour is not None:
        b.set_style_bg_color(c(colour), 0)
        b.set_style_bg_opa(255, 0)
    if radius:
        b.set_style_radius(radius, 0)
    b.remove_flag(lv.OBJ_FLAG.SCROLLABLE)
    return b


def label(parent, text, kind="text", colour=None):
    lb = lv.label(parent)
    style(lb, kind)
    if colour is not None:
        lb.set_style_text_color(c(colour), 0)
    lb.set_text(text)
    return lb


class Button:
    """An LVGL button and its label and icon (LVGL objects take no new attributes).

    ``label`` is the word on the button and ``icon`` its image; either is None
    when the button has none.
    """

    def __init__(self, obj, label, icon=None):
        self.obj = obj
        self.label = label
        self.icon = icon
        self.icon_colour = None
        if icon is not None:
            # The button's own colours change with its state, or when a screen sets
            # one on it: the icon follows through these two events.
            obj.add_event_cb(lambda e: self._tint(), lv.EVENT.STATE_CHANGED, None)
            obj.add_event_cb(lambda e: self._tint(), lv.EVENT.STYLE_CHANGED, None)
            self._tint()

    def on(self, event, fn):
        self.obj.add_event_cb(lambda e: fn(), event, None)
        return self

    def _tint(self):
        """The icon takes the colour the text of this button has in its state."""
        if self.icon_colour is None:
            colour = self.obj.get_style_text_color(0)
        else:
            colour = c(self.icon_colour)
        self.icon.set_style_image_recolor(colour, 0)

    def set_icon_colour(self, colour):
        """Always draw the icon in *colour*, whatever the button's state."""
        self.icon_colour = colour
        self._tint()

    @property
    def checked(self):
        return bool(self.obj.has_state(lv.STATE.CHECKED))

    @checked.setter
    def checked(self, on):
        if on:
            self.obj.add_state(lv.STATE.CHECKED)
        else:
            self.obj.remove_state(lv.STATE.CHECKED)

    def set_text(self, text):
        self.label.set_text(text)


def icon_image(parent, name):
    """An LVGL image of icon *name* at the scale's icon size; raises ValueError if there is none."""
    img = lv.image(parent)
    img.remove_style_all()
    img.set_src(lvicons.dsc(name, _icon_size))
    img.set_style_image_recolor_opa(255, 0)
    return img


def button(parent, text="", icon=None, checkable=False, w=None, h=None, kind="button"):
    """A themed button holding text, an icon (a Material icon name), or both."""
    b = lv.button(parent)
    b.remove_style_all()
    style(b, kind)
    style(b, "button_hovered", selector=lv.STATE.HOVERED)
    style(b, "button_pressed", selector=lv.STATE.PRESSED)
    style(b, "button_checked", selector=lv.STATE.CHECKED)
    style(b, "button_checked_hovered", selector=lv.STATE.CHECKED | lv.STATE.HOVERED)
    if checkable:
        b.add_flag(lv.OBJ_FLAG.CHECKABLE)
    if w and h:
        b.set_size(w, h)
    if icon and text:
        # An icon and a word: a centred row. The word takes the button's
        # colour, so checked and hovered states recolour it too; the icon
        # follows the same colours through the button's state events.
        b.set_flex_flow(lv.FLEX_FLOW.ROW)
        b.set_flex_align(lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
        b.set_style_pad_column(px(6), 0)
        img = icon_image(b, icon)
        lb = lv.label(b)
        lb.set_style_text_font(fonts.t(px(16)), 0)
        lb.set_text(text)
        return Button(b, lb, img)
    if icon:
        img = icon_image(b, icon)
        img.center()
        return Button(b, None, img)
    lb = lv.label(b)
    lb.set_text(text)
    lb.center()
    return Button(b, lb)
