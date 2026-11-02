# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The panel's small meters: one bar each for left and right, and a light that
flashes when a note comes in over MIDI.

Together they say which side a silence is on: the light with no bars is a note
the instrument didn't sound, and neither means nothing arrived. The bars show
what the board sends the codec, so the codec's volume doesn't move them.
"""

import math

import lvgl as lv

#: The peaks an empty and a full bar stand for.
FLOOR_DB = -60.0
TOP_DB = 0.0
#: A bar's steps, 3 dB each. Every redraw of the panel slows the pump a little,
#: because the framebuffer shares memory with the audio's buffers, so the meters
#: draw ten times a second and a held note stays still within a step.
BAR_TOP = 20
TICK_MS = 100
#: Taken off per tick: a bar falls in a second, and the light goes out in 200 ms,
#: so that hits at 120 bpm stay apart.
BAR_DECAY = 2
LIGHT_DECAY = 64
#: The softest note's flash, of 127, so that it can still be seen.
LIGHT_FLOOR = 64

#: Sizes on an 800 wide panel. The light's column is as wide as its legend.
BAR_W = 9
BAR_GAP = 5
LIGHT_GAP = 4
LIGHT_W = 40

BAR_ON = 0x35C24A
TROUGH = 0x101114
LIGHT_ON = 0xFF5A36
LEGEND = 0x8A8D93


def bar_height(peak):
    """A peak in 0.0 to 1.0 as a bar's height in 0 to :data:`BAR_TOP`."""
    if peak <= 0:
        return 0
    db = 20 * math.log10(peak)
    return max(0, min(BAR_TOP, int((db - FLOOR_DB) * BAR_TOP / (TOP_DB - FLOOR_DB))))


def _legend(parent, text, x, y, w):
    label = lv.label(parent)
    label.set_text(text)
    label.set_style_text_color(lv.color_hex(LEGEND), 0)
    label.set_style_text_font(getattr(lv, "font_montserrat_12", lv.font_montserrat_14), 0)
    label.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
    label.set_width(w)
    label.set_pos(x, y)
    return label


class Meters:
    """The bars and the light, drawn on *parent* at (*x*, *y*), :meth:`width`
    wide and *h* high."""

    @staticmethod
    def width(s):
        """How wide they draw, for a panel whose sizes go through *s*."""
        return 2 * s(BAR_W) + s(BAR_GAP) + s(LIGHT_GAP) + s(LIGHT_W)

    def __init__(self, parent, x, y, h, s):
        bar_w = s(BAR_W)
        gap = s(BAR_GAP)
        bars_h = h - s(16)
        self.bars = []
        self._shown = [0, 0]
        self._light = 0
        self._lit = 0
        for i, name in enumerate(("L", "R")):
            at = x + i * (bar_w + gap)
            bar = lv.bar(parent)
            bar.set_size(bar_w, bars_h)
            bar.set_pos(at, y)
            bar.set_range(0, BAR_TOP)
            bar.set_value(0, False)
            bar.set_style_bg_color(lv.color_hex(TROUGH), lv.PART.MAIN)
            bar.set_style_bg_opa(255, lv.PART.MAIN)
            bar.set_style_bg_color(lv.color_hex(BAR_ON), lv.PART.INDICATOR)
            bar.set_style_radius(2, lv.PART.MAIN)
            bar.set_style_radius(2, lv.PART.INDICATOR)
            bar.remove_flag(lv.obj.FLAG.CLICKABLE)
            self.bars.append(bar)
            _legend(parent, name, at - gap // 2, y + bars_h + 1, bar_w + gap)
        size = s(14)
        light_x = x + 2 * bar_w + gap + s(LIGHT_GAP)
        socket = lv.obj(parent)
        socket.remove_style_all()
        socket.set_size(size, size)
        socket.set_pos(light_x + (s(LIGHT_W) - size) // 2, y + (bars_h - size) // 2)
        socket.set_style_radius(size // 2, 0)
        socket.set_style_bg_color(lv.color_hex(TROUGH), 0)
        socket.set_style_bg_opa(255, 0)
        socket.remove_flag(lv.obj.FLAG.CLICKABLE)
        lit = lv.obj(socket)
        lit.remove_style_all()
        lit.set_size(size, size)
        lit.set_style_radius(size // 2, 0)
        lit.set_style_bg_color(lv.color_hex(LIGHT_ON), 0)
        lit.set_style_bg_opa(0, 0)
        lit.remove_flag(lv.obj.FLAG.CLICKABLE)
        self.lit = lit
        _legend(parent, "MIDI", light_x, y + bars_h + 1, s(LIGHT_W))

    def strike(self, velocity):
        """A note came in."""
        self._light = max(self._light, LIGHT_FLOOR + velocity * (127 - LIGHT_FLOOR) // 127)

    def tick(self, left, right):
        """Show the newest peaks, 0.0 to 1.0: a bar jumps up and falls slowly."""
        shown = self._shown
        for i, peak in enumerate((left, right)):
            height = bar_height(peak)
            if height < shown[i]:
                # A step's wobble isn't worth a redraw.
                height = shown[i] if height == shown[i] - 1 else max(height, shown[i] - BAR_DECAY)
            if height != shown[i]:
                shown[i] = height
                self.bars[i].set_value(height, False)
        light = self._light
        if light != self._lit:
            self._lit = light
            self.lit.set_style_bg_opa(light * 2, 0)
        self._light = max(0, light - LIGHT_DECAY)
