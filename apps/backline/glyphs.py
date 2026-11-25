# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Backline's icons, and what it shows on the status bar.

Each place an icon goes has a role here, and each role lists the Material
Symbols it can use, best first, then a glyph of LVGL's own font. The first
name the firmware's `icons` font has is drawn (``icons.has`` decides), and
with none of them the glyph is drawn as text, so a board whose firmware
is older than an icon still shows something in its place.

`bar_reading` is what the app's item on appkit's status bar shows while a
song plays: a dot, the part and the tempo.
"""

import icons
import lvgl as lv
from icons import lvgl as lvicons

#: role: (icon names, best first; the glyph drawn when the font has none of them)
ICONS = {
    "desk": (("view_module", "grid_on"), lv.SYMBOL.LIST),
    "floor": (("footprint", "speed"), lv.SYMBOL.LEFT),
    "songs": (("playlist_play", "queue_music"), lv.SYMBOL.LIST),
    "form": (("timeline",), lv.SYMBOL.RIGHT),
    "grid": (("view_module", "grid_on"), lv.SYMBOL.LIST),
    "record": (("mic_external_on", "mic"), lv.SYMBOL.AUDIO),
    "cast": (("cast_connected", "cast"), lv.SYMBOL.WIFI),
    "remote": (("smartphone", "devices"), lv.SYMBOL.WIFI),
    "loop": (("repeat_one", "repeat"), lv.SYMBOL.LOOP),
    "playing": (("queue_music",), lv.SYMBOL.PLAY),
    "prompt": (("auto_awesome",), lv.SYMBOL.EDIT),
}
DOT = "•"            # a bullet, in every built-in Montserrat
FONT_SIZES = (14, 16, 24, 32, 40)


def pick(role):
    """The first icon name for ``role`` that the font has, or None."""
    for name in ICONS[role][0]:
        if icons.has(name):
            return name
    return None


def glyph_font(px):
    """The largest built-in font no taller than ``px``, else the smallest."""
    best = None
    for size in FONT_SIZES:
        f = getattr(lv, "font_montserrat_%d" % size, None)
        if f is not None and (best is None or size <= px):
            best = f
    return best or lv.font_get_default()


def show(parent, role, size, color):
    """The icon for ``role`` on ``parent``, ``size`` pixels square in ``color``
    (an ``lv.color_t``): an ``lv.image``, or an ``lv.label`` holding the glyph
    when the font has none of the role's icons."""
    name = pick(role)
    if name is not None:
        return lvicons.image(parent, name, size, color)
    lbl = lv.label(parent)
    lbl.set_style_text_font(glyph_font(size), 0)
    lbl.set_style_text_color(color, 0)
    lbl.set_text(ICONS[role][1])
    return lbl


def bar_reading(t):
    """``(icon, text)`` for the status bar from the box's telemetry ``t``,
    or None while the song is stopped. The icon is the cast's while the
    desk is cast; where the font has no icon for it, the glyph leads the
    text instead."""
    if not t.get("playing"):
        return None
    role = "cast" if t.get("cast") else "playing"
    name = pick(role)
    text = "%s %s  %d" % (DOT, (t.get("part") or "").upper(), int(t.get("tempo", 0) + 0.5))
    if name is None:
        text = ICONS[role][1] + " " + text
    return name, text
