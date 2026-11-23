# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Backline's floor view: the face you read from a pedalboard.

A big ring lights the beat of the bar, its colour the part's: blue for the
intro, amber for a main, orange for a fill, violet for a transition, red for
the outro. The beat number sits inside it in seven-segment digits, with the
bar of the part under it. Beside the ring are the song's name, the part
playing in a glass window, a chip with the part coming next, the tempo, the
kit, and the two pedals' lamps, which light while a pedal is down. Touching
a lamp is pressing that pedal.

The view holds nothing but an ``hmilink.Panel``: what it shows comes from
the device's telemetry and document, and a pedal press goes back as a
command. So the same view works on the box's own screen, through
``hmilink.local``, or on another screen over any hmilink link.

Everything is sized from ``(width, height)``. The art is drawn once by
svgio at that size (art.py); a beat shows one lit segment and hides
another, and nothing else is redrawn unless it changed.
"""

import lvgl as lv

from . import art, glyphs
from .engine import BAR, meter

PEDAL_COLORS = (0xFFB703, 0x4CC9F0)
HINTS = {
    "stopped": "TAP TO START",
    "intro": "INTRO",
    "main": "TAP  FILL\nHOLD  NEXT\nTAP TAP  END",
    "fill": "FILL, THEN BACK",
    "transition": "ON TO THE NEXT",
    "outro": "TAP TAP: STOP NOW",
}
ARROW = "  " + lv.SYMBOL.RIGHT + "  "
PULSE_LEVELS = 3          # how many steps the beat's pulse fades in
PULSE_SPAN = 0.34         # the share of a beat it lasts


def pulse(tele, steps):
    """How bright the beat's pulse is now, 0 to `PULSE_LEVELS`: brightest
    as a beat lands, gone a third of the way through it. Read from where the
    part is (``at``), so it keeps time with the song, not with the screen."""
    beats = tele.get("beats") or steps
    span = BAR * (steps // max(1, beats) or 1) / float(steps)
    phase = (tele.get("at", 0) % BAR) % span / span
    return max(0, PULSE_LEVELS - int(phase * PULSE_LEVELS / PULSE_SPAN))


def _label(parent, font, color, text="", width=None):
    """A label; with ``width``, one line that ends in dots when it's too long."""
    lbl = lv.label(parent)
    lbl.set_style_text_font(font, 0)
    lbl.set_style_text_color(lv.color_hex(color), 0)
    lbl.set_text(text)
    if width is not None:
        lbl.set_width(width)
        lbl.set_height(font.line_height)
        lbl.set_long_mode(lv.label.LONG_MODE.DOTS)
    return lbl


def _meter(doc):
    """``(steps, group)`` for the ring, from a song document (4/4 without one)."""
    return meter(doc or {})


def text_width(text, font, space=0):
    """How wide ``text`` draws in ``font`` with ``space`` between letters."""
    n = len(text.encode())        # LVGL counts bytes, and a symbol is three
    try:
        attrs = lv.text_attributes_t()
        attrs.init()
        attrs.letter_space = space
        return lv.text_get_width(text, n, font, attrs)
    except AttributeError:  # LVGL before 9.4 takes the spacing itself
        return lv.text_get_width(text, n, font, space)


def fit(label, choices, width, space=1):
    """Show the first of ``choices`` that fits ``width`` on ``label``: each
    with ``space`` between letters, then each with none. The last choice,
    tightest, is shown when none fits."""
    font = label.get_style_text_font(0)
    for sp in (space, 0) if space else (0,):
        for text in choices:
            if text_width(text, font, sp) <= width:
                label.set_style_text_letter_space(sp, 0)
                label.set_text(text)
                return text
    label.set_style_text_letter_space(0, 0)
    label.set_text(choices[-1])
    return choices[-1]


class Floor:
    """The floor view on ``root``, ``size`` = (width, height), showing ``panel``.

    With ``on_switch``, a button in the corner calls it: the app shows the
    desk view there instead.
    """

    def __init__(self, root, size, panel, on_switch=None):
        self.root = root
        self.panel = panel
        w, h = size
        lay = self.lay = art.Layout(w, h)
        self.pictures = []
        self.shown = {}
        self.tele = {}
        self.doc_name = ""

        base = lv.obj(root)
        base.remove_style_all()
        base.set_size(w, h)
        base.set_pos(0, 0)
        base.remove_flag(lv.obj.FLAG.SCROLLABLE)
        base.set_style_bg_color(lv.color_hex(0x06080C), 0)
        base.set_style_bg_opa(255, 0)
        self.base = base

        # The panel and the ring's lit segments, one a step of the bar, are
        # drawn for the song's meter, and again when it changes.
        self.meter = None
        self.ring_pictures = []
        self.segments = []
        self.looks = []
        self._ring(*_meter(panel.doc))

        # Seven-segment digits: drawn once, shown by swapping an image's source.
        self.big = {}
        for ch in "0123456789- ":
            self.big[ch] = art.Picture(None, art.digit_svg(ch, lay.big_w, lay.big_h), lay.big_w, lay.big_h)
        self.small = {}
        for ch in "0123456789 ":
            self.small[ch] = art.Picture(None, art.digit_svg(ch, lay.small_w, lay.small_h), lay.small_w, lay.small_h)
        self.pictures.extend(self.big.values())
        self.pictures.extend(self.small.values())
        self.beat_digit = self.big["-"].show(base, int(lay.cx - lay.big_w / 2), int(lay.cy - lay.big_h * 0.62))
        _x, ty, _tw, th = lay.tempo
        self.tempo_digits = [self.small[" "].show(base, x, ty + (th - lay.small_h) // 2) for x in art.tempo_slots(lay)]

        small = lay.font(0.06)
        tiny = lay.font(0.05)
        eyebrow = _label(base, tiny, 0x8792A5, "BEAT")
        eyebrow.align_to(self.beat_digit, lv.ALIGN.OUT_TOP_MID, 0, -2)
        eyebrow.set_style_text_letter_space(2, 0)
        self.bar = _label(base, small, 0xC8D0DC, "")
        self.bar.set_style_text_letter_space(1, 0)
        self.bar.set_width(int(lay.r))
        self.bar.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        self.bar.set_pos(int(lay.cx - lay.r / 2), int(lay.cy + lay.big_h * 0.45))

        cx, cy, cw, _ch = lay.col
        self.song = _label(base, small, 0x9AA6B8, "", cw - 2)
        self.song.set_pos(cx + 2, cy)

        wx, wy, ww, wh = lay.window
        part_font = lay.font(0.11)
        while part_font.line_height > wh - 4 and part_font is not small:
            part_font = small
        self.part = _label(base, part_font, art.ROLE_COLORS["stopped"], "", ww - 8)
        self.part.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        self.part.set_pos(wx + 4, wy + (wh - part_font.line_height) // 2)

        chip = lv.obj(base)
        chip.remove_style_all()
        chip.set_style_radius(lv.RADIUS_CIRCLE, 0)
        chip.set_style_border_width(max(1, lay.h // 240), 0)
        chip.set_style_border_color(lv.color_hex(0x3A4555), 0)
        chip.set_style_bg_color(lv.color_hex(0x0E131B), 0)
        chip.set_style_bg_opa(255, 0)
        chip.set_size(cw, lay.chip_h)
        chip.set_pos(cx, lay.chip_y)
        chip.remove_flag(lv.obj.FLAG.SCROLLABLE)
        self.chip = chip
        self.chip_text = _label(chip, tiny, 0xC8D0DC, "", cw - 8)
        self.chip_text.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        self.chip_text.align(lv.ALIGN.CENTER, 0, 0)

        tx, ty, tw, th = lay.tempo
        gap = max(4, lay.m // 2)
        bpm = _label(base, tiny, 0x8792A5, "BPM")
        bpm.set_style_text_letter_space(2, 0)
        bpm.set_pos(tx + tw + gap, ty + (th - tiny.line_height) // 2)
        # A size smaller than the song's, so on a big screen it clears the lamps.
        self.kit = _label(base, tiny, 0xC8D0DC, "", cw)
        self.kit.set_pos(cx + 2, lay.kit_y)
        # What the pedal does now, between the lamps, where there's room.
        hint_font = lay.font(0.034)
        self.hint_room = (lay.pedal_x[1] - lay.pedal_x[0] - int(2.8 * lay.pedal_r), 2 * lay.pedal_r + lay.m)
        self.hint = _label(base, hint_font, 0x7E8A9C, "")
        self.hint.set_width(max(10, self.hint_room[0]))
        self.hint.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        self.hint.set_pos(lay.pedal_x[0] + int(1.4 * lay.pedal_r), lay.pedal_y)

        # The pedals' lamps: a glow over each, and a touch area that is the pedal.
        self.glows = []
        for i, px in enumerate(lay.pedal_x):
            gr = int(lay.pedal_r * 1.6)
            pic = art.Picture(base, art.glow_svg(gr, PEDAL_COLORS[i]), 2 * gr, 2 * gr, px - gr, lay.pedal_y - gr)
            pic.image.add_flag(lv.obj.FLAG.HIDDEN)
            self.pictures.append(pic)
            self.glows.append(pic.image)
            letter = _label(base, small, 0xDDE3EC, "AB"[i])
            letter.align_to(pic.image, lv.ALIGN.CENTER, 0, 0)
            pad = lv.obj(base)
            pad.remove_style_all()
            pad.set_size(2 * gr, 2 * gr)
            pad.set_pos(px - gr, lay.pedal_y - gr)
            pad.add_flag(lv.obj.FLAG.CLICKABLE)
            pad.add_event_cb(self._pad(i, True), lv.EVENT.PRESSED, None)
            pad.add_event_cb(self._pad(i, False), lv.EVENT.RELEASED, None)
            pad.add_event_cb(self._pad(i, False), lv.EVENT.PRESS_LOST, None)

        # Where the screen can show the desk instead, a button for it in the
        # corner above the ring.
        self.switch = None
        if on_switch is not None:
            size = max(28, min(lay.m * 3, 48))
            btn = lv.obj(base)
            btn.remove_style_all()
            btn.set_size(size, size)
            btn.set_pos(max(2, lay.m // 3), max(2, lay.m // 3))
            btn.set_style_radius(size // 4, 0)
            btn.set_style_bg_color(lv.color_hex(0x0E131B), 0)
            btn.set_style_bg_opa(220, 0)
            btn.set_style_border_color(lv.color_hex(0x3A4555), 0)
            btn.set_style_border_width(1, 0)
            btn.add_flag(lv.obj.FLAG.CLICKABLE)
            btn.remove_flag(lv.obj.FLAG.SCROLLABLE)
            icon = glyphs.show(btn, "desk", size * 2 // 3, lv.color_hex(0xC8D0DC))
            icon.center()
            btn.add_event_cb(lambda _e: on_switch(), lv.EVENT.CLICKED, None)
            self.switch = btn

        panel.on_doc = self._doc
        panel.on_tele = self._tele
        if panel.doc is not None:
            self._doc(panel.doc, panel.desc)
        self._tele({})

    # -- the pedals ------------------------------------------------------------

    def _pad(self, which, down):
        def on_event(_event):
            self.pedal(which, down)

        return on_event

    def pedal(self, which, down):
        """Pedal ``which`` went down or up: tell the device."""
        self.panel.command("pedal", pedal=which, down=down)

    # -- what it shows ---------------------------------------------------------

    def poll(self):
        self.panel.poll()

    def bytes(self):
        """What the art holds, in bytes."""
        return sum(p.bytes for p in self.pictures) + sum(p.bytes for p in self.ring_pictures)

    def _ring(self, steps, group):
        """Draw the panel and the ring's segments for a bar of ``steps``,
        ``group`` to a beat, unless that is what is drawn already."""
        if self.meter == (steps, group):
            return
        self.meter = (steps, group)
        for pic in self.ring_pictures:
            pic.image.delete()
        lay = self.lay
        panel = art.Picture(self.base, art.panel_svg(lay, steps, group), lay.w, lay.h)
        panel.image.move_to_index(0)
        self.ring_pictures = [panel]
        self.segments = []
        for b in range(steps):
            x, y, bw, bh = art.segment_box(lay, b, steps, group)
            pic = art.Picture(self.base, art.segment_svg(lay, b, steps, group), bw, bh, x, y)
            pic.image.add_flag(lv.obj.FLAG.HIDDEN)
            pic.image.move_to_index(1 + b)
            self.ring_pictures.append(pic)
            self.segments.append(pic.image)
        self.looks = ["off"] * steps
        self.shown.pop("beat", None)

    def _doc(self, doc, desc):
        self.doc_name = doc.get("name", "") if doc else ""
        self._ring(*_meter(doc))
        if not self.tele.get("song"):
            self._set("song", self.doc_name.upper(), self._song)

    def _song(self, text):
        fit(self.song, [text], self.song.get_width(), 1)

    def _set(self, key, value, fn):
        if self.shown.get(key) != value:
            self.shown[key] = value
            fn(value)
            return True
        return False

    def _hint(self, text):
        """The hint centred between the lamps, or none when it doesn't fit there."""
        hint = self.hint
        hint.set_text(text)
        hint.update_layout()
        h = hint.get_height()
        lay = self.lay
        if self.hint_room[0] < 40 or h > self.hint_room[1]:
            hint.add_flag(lv.obj.FLAG.HIDDEN)
            return
        hint.remove_flag(lv.obj.FLAG.HIDDEN)
        hint.set_y(lay.pedal_y - h // 2)

    def _pulse(self, level):
        """Brighten the beat's digit and its lit segment by ``level`` (0 to
        `PULSE_LEVELS`), more on the bar's first beat."""
        accent = self.tele.get("beat") == 1
        self.beat_digit.set_style_image_recolor(lv.color_hex(0xFFFFFF), 0)
        self.beat_digit.set_style_image_recolor_opa(level * (36 if accent else 24), 0)
        step = self.shown.get("beat", 0)
        if 0 < step <= len(self.segments):
            self.segments[step - 1].set_style_image_recolor_opa(120 - level * (30 if accent else 20), 0)

    def _tele(self, values):
        v = self.tele
        v.update(values)
        role = v.get("role", "stopped")
        color = art.ROLE_COLORS.get(role, art.ROLE_COLORS["stopped"])
        playing = v.get("playing", False)
        steps = v.get("steps") or 4
        self._ring(steps, max(1, steps // (v.get("beats") or steps)))
        step = v.get("step", v.get("beat", 0)) if playing else 0
        beat = v.get("beat", 0) if playing else 0
        self._set("song", (v.get("song") or self.doc_name).upper(), self._song)
        recolor = self._set("color", color, lambda c: None)
        if recolor:
            self.part.set_style_text_color(lv.color_hex(color), 0)
        if self._set("beat", step, lambda b: None) or recolor:
            # The beat now is hot, its centre near white; the beats before it
            # stay lit in a deeper shade of the part's colour.
            deep = lv.color_hex(art.mix(color, 0x000000, 0.35))
            for i, seg in enumerate(self.segments):
                look = "off" if i >= step else "now" if i == step - 1 else "past"
                if not recolor and self.looks[i] == look:
                    continue          # unchanged: left alone, so it isn't redrawn
                self.looks[i] = look
                if look == "off":
                    seg.add_flag(lv.obj.FLAG.HIDDEN)
                    continue
                seg.remove_flag(lv.obj.FLAG.HIDDEN)
                now = look == "now"
                seg.set_style_image_recolor(lv.color_hex(color) if now else deep, 0)
                seg.set_style_image_recolor_opa(120 if now else 225, 0)
            self.beat_digit.set_src(self.big[str(beat) if 0 < beat < 10 else "-"].dsc)
            self.shown.pop("pulse", None)
        self._set("pulse", pulse(v, steps) if playing else 0, self._pulse)
        bar = ("BAR %d / %d" % (v.get("bar", 1), v.get("bars", 1))) if playing else "STOPPED"
        self._set("bar", bar, self.bar.set_text)
        self._set("part", (v.get("part") or "Ready").upper(), self.part.set_text)
        nxt = v.get("next") or ""
        if self._set("next", (nxt, playing), lambda n: None):
            if nxt:
                up = nxt.upper()
                choices = ["NEXT" + ARROW + up, lv.SYMBOL.RIGHT + " " + up, up]
            else:
                choices = [lv.SYMBOL.LOOP + "  LOOPING", "LOOPING"] if playing else ["TAP" + ARROW + "INTRO", "TAP " + lv.SYMBOL.RIGHT + " INTRO"]
            fit(self.chip_text, choices, self.chip_text.get_width(), 1)
            ncolor = art.ROLE_COLORS.get(v.get("next_role") or "stopped", 0x3A4555)
            self.chip.set_style_border_color(lv.color_hex(ncolor if nxt else 0x3A4555), 0)
            self.chip_text.set_style_text_color(lv.color_hex(ncolor if nxt else 0x9AA6B8), 0)
        tempo = int(v.get("tempo", 0) + 0.5)
        if self._set("tempo", tempo, lambda t: None):
            text = ("%3d" % tempo)[-3:] if tempo else "   "
            for img, ch in zip(self.tempo_digits, text):
                img.set_src(self.small[ch if ch in self.small else " "].dsc)
        self._set("kit", v.get("kit", ""), self.kit.set_text)
        self._set("hint", HINTS.get(role, ""), self._hint)
        pedals = v.get("pedals") or ["up", "up"]
        for i, state in enumerate(pedals[:2]):
            if self._set("pedal%d" % i, state, lambda s: None):
                if state == "up":
                    self.glows[i].add_flag(lv.obj.FLAG.HIDDEN)
                else:
                    self.glows[i].remove_flag(lv.obj.FLAG.HIDDEN)
                    self.glows[i].set_style_image_opa(255 if state == "held" else 210, 0)
