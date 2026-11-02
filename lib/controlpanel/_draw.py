# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The few drawing helpers every control shares: plain boxes, labels, grain."""

import lvgl as lv

from . import sprites


def plain(obj, clickable=False):
    obj.remove_style_all()
    obj.remove_flag(lv.obj.FLAG.SCROLLABLE)
    if not clickable:
        obj.remove_flag(lv.obj.FLAG.CLICKABLE)
    return obj


def box(parent, x, y, w, h):
    obj = plain(lv.obj(parent))
    obj.set_pos(x, y)
    obj.set_size(w, h)
    return obj


def label(parent, text, rgb, font=None, spacing=1):
    text_obj = lv.label(parent)
    text_obj.set_text(text)
    text_obj.set_style_text_color(lv.color_hex(rgb), 0)
    text_obj.set_style_text_font(font or lv.font_montserrat_14, 0)
    text_obj.set_style_text_letter_space(spacing, 0)
    return text_obj


def text_width(text, font, spacing):
    width = 0
    for i, char in enumerate(text):
        following = ord(text[i + 1]) if i + 1 < len(text) else 0
        width += font.get_glyph_width(ord(char), following) + spacing
    return width


def fill(obj, top, bottom=None):
    obj.set_style_bg_opa(lv.OPA.COVER, 0)
    obj.set_style_bg_color(lv.color_hex(top), 0)
    if bottom is not None:
        obj.set_style_bg_grad_color(lv.color_hex(bottom), 0)
        obj.set_style_bg_grad_dir(lv.GRAD_DIR.VER, 0)


def finish(obj, rgb, grain):
    """Give *obj* a grained finish: "matte", "brushed" or None for flat."""
    if grain:
        obj.set_style_bg_image_src(sprites.texture(rgb, grain == "brushed"), 0)
        obj.set_style_bg_image_tiled(True, 0)


class Lamp:
    """An indicator LED: a dark lens, and a lit image shown over it."""

    def __init__(self, parent, cx, cy, lens, theme):
        self._theme = theme
        self._lens = lens
        self._cx = cx
        self._cy = cy
        self._parent = parent
        off = box(parent, int(cx - lens - 1), int(cy - lens - 1), int(2 * lens + 2), int(2 * lens + 2))
        fill(off, theme["led_off"])
        off.set_style_radius(lv.RADIUS_CIRCLE, 0)
        off.set_style_border_width(1, 0)
        off.set_style_border_color(lv.color_hex(theme["led_rim"]), 0)
        self._image = lv.image(parent)
        self._image.remove_flag(lv.obj.FLAG.CLICKABLE)
        self._image.add_flag(lv.obj.FLAG.HIDDEN)
        self.rgb = None

    def set(self, rgb):
        """Light it in *rgb*, or put it out with None."""
        if rgb == self.rgb:
            return
        self.rgb = rgb
        if rgb is None:
            self._image.add_flag(lv.obj.FLAG.HIDDEN)
            return
        buf, size = sprites.small_led(self._lens, rgb, self._theme)
        self._image.set_src(buf)
        self._image.set_pos(int(self._cx - size / 2 + 0.5), int(self._cy - size / 2 + 0.5))
        self._image.remove_flag(lv.obj.FLAG.HIDDEN)
