# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""The factory's images and fonts, loaded once.

Images are LVGL 9 ``.bin`` files (RGB565 plane, then alpha) in ``images/``,
shown through an ``image_dsc_t`` that points at the file's bytes: no decoder
runs. Fonts are KoHo ``.bin`` files in ``fonts/`` loaded with
``lv.binfont_create_from_buffer``. A font that isn't there falls back to the
nearest built-in Montserrat, so the app still runs without them.
"""

import lvgl as lv

HEADER = 12  # LVGL 9 image header: magic, cf, flags, w, h, stride, reserved

_here = __file__.rsplit("/", 1)[0] if "/" in __file__ else "."
_images = {}
_fonts = {}
_keep = []

# Name: (file stem, built-in fallback)
FONTS = {
    "bold28": ("koho_bold_28", "font_montserrat_24"),
    "bold18": ("koho_bold_18", "font_montserrat_16"),
    "semi24": ("koho_semibold_24", "font_montserrat_16"),
    "semi22": ("koho_semibold_22", "font_montserrat_16"),
    "semi18": ("koho_semibold_18", "font_montserrat_16"),
    "semi14": ("koho_semibold_14", "font_montserrat_14"),
}

fallbacks = []  # font names that fell back, for the log


def _read(path):
    with open(path, "rb") as f:
        return f.read()


def image(name):
    """The ``image_dsc_t`` for ``images/<name>.bin``."""
    dsc = _images.get(name)
    if dsc is not None:
        return dsc
    data = _read("%s/images/%s.bin" % (_here, name))
    w = data[4] | (data[5] << 8)
    h = data[6] | (data[7] << 8)
    dsc = lv.image_dsc_t()
    dsc.header.magic = lv.IMAGE_HEADER_MAGIC
    dsc.header.cf = data[1]
    dsc.header.w = w
    dsc.header.h = h
    dsc.header.stride = data[8] | (data[9] << 8)
    pixels = memoryview(data)[HEADER:]
    dsc.data_size = len(pixels)
    dsc.data = pixels
    _keep.append(data)
    _images[name] = dsc
    return dsc


def font(name):
    """A KoHo font by role ("bold28", "semi18", ...), or its fallback."""
    f = _fonts.get(name)
    if f is not None:
        return f
    stem, builtin = FONTS[name]
    try:
        data = _read("%s/fonts/%s.bin" % (_here, stem))
        f = lv.binfont_create_from_buffer(data, len(data))
        if f is None:
            raise OSError("binfont_create_from_buffer failed")
        _keep.append(data)
    except OSError:
        f = getattr(lv, builtin)
        fallbacks.append(name)
    _fonts[name] = f
    return f


def montserrat(size):
    return getattr(lv, "font_montserrat_%d" % size)
