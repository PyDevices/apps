# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The receiver's icons, drawn once by svgio and kept as LVGL images.

Each icon is white on a 24-unit grid. `image(name, px)` draws it at *px*
pixels the first time it's asked for and hands back the same descriptor
after that, so a redraw never parses an SVG. LVGL tints an icon with
``image_recolor``, so one drawing serves every colour the screen takes on.
"""

import lvgl as lv
import svgio

_HEAD = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
_LINE = 'fill="none" stroke="#fff" stroke-width="%s" stroke-linecap="round" stroke-linejoin="round"'

SVG = {
    "play": '<path fill="#fff" d="M8 5.6v12.8c0 .8.9 1.3 1.6.9l10-6.4c.6-.4.6-1.3 0-1.7l-10-6.4C8.9 4.3 8 4.8 8 5.6z"/>',
    "pause": '<rect fill="#fff" x="6.5" y="5" width="3.6" height="14" rx="1.3"/>'
    '<rect fill="#fff" x="13.9" y="5" width="3.6" height="14" rx="1.3"/>',
    "next": '<path fill="#fff" d="M5.5 6.6v10.8c0 .8.9 1.3 1.6.8l8-5.4c.6-.4.6-1.2 0-1.6l-8-5.4c-.7-.5-1.6 0-1.6.8z"/>'
    '<rect fill="#fff" x="16.4" y="5.5" width="2.4" height="13" rx="1.2"/>',
    "previous": '<g transform="matrix(-1 0 0 1 24 0)">'
    '<path fill="#fff" d="M5.5 6.6v10.8c0 .8.9 1.3 1.6.8l8-5.4c.6-.4.6-1.2 0-1.6l-8-5.4c-.7-.5-1.6 0-1.6.8z"/>'
    '<rect fill="#fff" x="16.4" y="5.5" width="2.4" height="13" rx="1.2"/></g>',
    "bluetooth": '<path ' + _LINE % "1.6" + ' d="M7 7.5l10 9-5 4.5v-18l5 4.5-10 9"/>',
    "volume": '<path fill="#fff" d="M4 9.5v5c0 .6.4 1 1 1h2.6l3.8 3.3c.6.5 1.6.1 1.6-.8V6c0-.9-1-1.3-1.6-.8L7.6 8.5H5c-.6 0-1 .4-1 1z"/>'
    '<path ' + _LINE % "1.6" + ' d="M16 9a4.2 4.2 0 0 1 0 6M18.6 6.5a7.8 7.8 0 0 1 0 11"/>',
    # Drawn large, where a cover goes: a fine line at that size.
    "note": '<path ' + _LINE % ".45" + ' d="M9 18V6.5l10-2V16"/>'
    '<circle ' + _LINE % ".45" + ' cx="6.6" cy="18" r="2.4"/><circle ' + _LINE % ".45" + ' cx="16.6" cy="16" r="2.4"/>',
}

_cache = {}


def image(name, px):
    """The LVGL image source for icon *name*, *px* pixels square.

    Drawn on first use and kept for as long as the app runs: an RGB565A8
    buffer of ``px * px * 3`` bytes.
    """
    key = (name, px)
    hit = _cache.get(key)
    if hit is not None:
        return hit[0]
    dec = svgio.SvgDecoder()
    w, h = dec.open((_HEAD + SVG[name] + "</svg>").encode(), width=px)
    n = w * h
    data = bytearray(n * 3)
    view = memoryview(data)
    dec.decode(view[: n * 2], view[n * 2 :])
    close = getattr(dec, "close", None)
    if close is not None:
        close()
    dsc = lv.image_dsc_t()
    dsc.header.magic = lv.IMAGE_HEADER_MAGIC
    dsc.header.cf = lv.COLOR_FORMAT.RGB565A8
    dsc.header.w = w
    dsc.header.h = h
    dsc.header.stride = w * 2
    dsc.data_size = n * 3
    dsc.data = data
    _cache[key] = (dsc, data)
    return dsc


def tinted(parent, name, px, color):
    """An `lv.image` of icon *name* in *color* (an ``lv.color_t``) on *parent*."""
    img = lv.image(parent)
    img.set_src(image(name, px))
    tint(img, color)
    return img


def tint(img, color):
    img.set_style_image_recolor(color, 0)
    img.set_style_image_recolor_opa(lv.OPA.COVER, 0)


def forget():
    """Let every drawn icon go, when the app closes."""
    _cache.clear()
