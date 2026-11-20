# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The receiver's screen: the cover, what's playing, and the transport.

`Screen` builds every widget once and then only changes them: a new track
sets some labels, a new cover sets one image, and the spectrum moves a few
bars. Nothing here talks to Bluetooth; the app hands it what the sink says.
"""

import lvgl as lv
from controlkit import RingButton, SpectrumBars
from controlkit.theme import BLACK

from . import glyphs

BG = 0x0B0E14
TEXT = 0xFFFFFF
SUB = 0xC6CDD8  # the artist: a step down from the title
MUTED = 0x7D8799  # the album, the details and the times
LINE = 0x3A4458  # the thin outlines
TEAL = 0x4DB6AC  # the accent until a cover gives one
AMBER = 0xFFB74D  # a warning about the sender: its battery, its signal

BANDS = 24
WEAK_DB = -10  # a link this far below the radio's ideal range is weak
# What the sender's AVRCP battery report is worth saying; "normal" isn't.
BATTERY = {"warning": "Phone battery low", "critical": "Phone battery critical", "external": "Phone charging",
           "full": "Phone charged"}


def _font(*sizes):
    for s in sizes:
        f = getattr(lv, "font_montserrat_%d" % s, None)
        if f is not None:
            return f
    return lv.font_default()


F_HUGE = _font(40, 32, 28, 24)
F_TITLE = _font(32, 28, 24)
F_BIG = _font(24, 20, 16)
F_BODY = _font(16, 14)
F_SMALL = _font(14, 12)


def clock(ms):
    """``m:ss``, or ``h:mm:ss`` for an hour or more."""
    s = max(0, ms // 1000)
    if s >= 3600:
        return "%d:%02d:%02d" % (s // 3600, s // 60 % 60, s % 60)
    return "%d:%02d" % (s // 60, s % 60)


def mix(a, b, t):
    """``0xRRGGBB`` *t* of the way from *a* to *b*."""
    out = 0
    for shift in (16, 8, 0):
        x = (a >> shift) & 255
        y = (b >> shift) & 255
        out |= int(x + (y - x) * t + 0.5) << shift
    return out


def accent_of(pixels, w, h):
    """A colour for the screen from a cover's RGB565 *pixels*: its most vivid
    hue, made light enough to read on the dark background. A grey cover
    gives a soft white."""
    r = g = b = wt = 0.0
    step = max(1, w // 24)
    for y in range(step // 2, h, step):
        row = y * w
        for x in range(step // 2, w, step):
            i = (row + x) * 2
            v = pixels[i] | pixels[i + 1] << 8
            pr = (v >> 8) & 0xF8
            pg = (v >> 3) & 0xFC
            pb = (v << 3) & 0xF8
            hi = max(pr, pg, pb)
            if hi < 40:
                continue
            sat = (hi - min(pr, pg, pb)) / hi
            k = sat * sat * hi
            r += pr * k
            g += pg * k
            b += pb * k
            wt += k
    if wt < 200:
        return 0xDCE3EC
    r, g, b = r / wt, g / wt, b / wt
    hi = max(r, g, b)
    lo = min(r, g, b)
    # Keep the hue; set the saturation and brightness for text on BG.
    sat = (hi - lo) / hi if hi else 0
    sat = 0.38 if sat < 0.38 else (0.78 if sat > 0.78 else sat)
    val = 245.0
    out = 0
    for c in (r, g, b):
        f = (c - lo) / (hi - lo) if hi > lo else 1.0
        out = (out << 8) | int(val * (1 - sat * (1 - f)))
    return out


def _plain(obj):
    obj.remove_style_all()
    obj.remove_flag(lv.obj.FLAG.SCROLLABLE)
    obj.remove_flag(lv.obj.FLAG.CLICKABLE)
    return obj


def _box(parent, x, y, w, h):
    o = _plain(lv.obj(parent))
    o.set_pos(x, y)
    o.set_size(w, h)
    return o


def _label(parent, font, rgb, space=0):
    lbl = lv.label(parent)
    lbl.set_text("")
    lbl.set_style_text_font(font, 0)
    lbl.set_style_text_color(lv.color_hex(rgb), 0)
    if space:
        lbl.set_style_text_letter_space(space, 0)
    return lbl


def _show(obj, on):
    if on:
        obj.remove_flag(lv.obj.FLAG.HIDDEN)
    else:
        obj.add_flag(lv.obj.FLAG.HIDDEN)


# Where everything goes in the app's area: 800 x 416 under Home's header.
COVER = (24, 24, 368)  # x, y, side: the cover fills the left
COL_X, COL_W = 416, 360  # everything else stacks in a column beside it
SOURCE_Y = 24
TEXT_Y = 60
SPECTRUM = (416, 246, 360, 30)
PROGRESS = (416, 292, 360)
TRANSPORT = (416, 326, 56, 72, 14)  # x, y, small ring, play ring, gap
VOLUME = (650, 362, 126)  # x, middle y, width
PAIR_RING = 300


class Screen:
    """Everything on the receiver's screen, in *root* (*size* pixels).

    *on* maps ``"play"``, ``"next"``, ``"previous"`` and ``"volume"`` to what
    the buttons and the slider do.
    """

    def __init__(self, root, size, on):
        self.root = root
        self.on = on
        self.accent = TEAL
        self.keep = {}
        self._dragging = False
        self._title_text = None
        self._pos_text = None
        root.remove_flag(lv.obj.FLAG.SCROLLABLE)
        root.set_style_bg_opa(lv.OPA.COVER, 0)
        root.set_style_bg_grad_dir(lv.GRAD_DIR.VER, 0)
        root.set_style_bg_grad_color(lv.color_hex(BG), 0)
        root.set_style_bg_main_stop(0, 0)
        root.set_style_bg_grad_stop(230, 0)

        self._build_cover(*COVER)
        self._build_text()
        self._build_progress()
        self._build_transport()
        self._build_volume()
        x, y, w, h = SPECTRUM
        self.bars = SpectrumBars(root, x, y, w, h, BLACK, bands=BANDS, gap=w // BANDS * 3 // 5, color=TEAL)
        self.set_accent(TEAL)

    # -- building -------------------------------------------------------

    def _build_cover(self, x, y, s):
        box = self.cover_box = _box(self.root, x, y, s, s)
        box.set_style_radius(18, 0)
        box.set_style_clip_corner(True, 0)
        box.set_style_bg_opa(lv.OPA.COVER, 0)
        box.set_style_bg_color(lv.color_hex(0x141A26), 0)
        box.set_style_bg_grad_color(lv.color_hex(0x0E121A), 0)
        box.set_style_bg_grad_dir(lv.GRAD_DIR.VER, 0)
        # A glow in the cover's own colour. Only a new cover redraws it: the
        # spectrum and the progress bar are clear of it.
        box.set_style_shadow_width(40, 0)
        box.set_style_shadow_offset_y(10, 0)
        box.set_style_shadow_opa(0, 0)
        self.art = lv.image(box)
        self.art.set_size(s, s)
        self.art.set_inner_align(lv.image.ALIGN.STRETCH)
        self.art.set_antialias(True)
        _show(self.art, False)
        self.note = glyphs.tinted(box, "note", s * 2 // 5, lv.color_hex(0x3A4458))
        self.note.center()
        # A hairline on top of the art, so a dark cover still has an edge.
        edge = self.edge = _box(self.root, x, y, s, s)
        edge.set_style_radius(18, 0)
        edge.set_style_border_width(1, 0)
        edge.set_style_border_color(lv.color_hex(0xFFFFFF), 0)
        edge.set_style_border_opa(36, 0)
        # Pairing: the Bluetooth mark in rings, where the cover goes.
        pair = self.pair = _box(self.root, x, y, s, s)
        ring = PAIR_RING
        self.rings = []
        for d, opa in ((ring, 50), (ring * 7 // 10, 90), (ring * 2 // 5, 255)):
            c = _box(pair, (s - d) // 2, (s - d) // 2, d, d)
            c.set_style_radius(lv.RADIUS_CIRCLE, 0)
            c.set_style_border_width(1, 0)
            c.set_style_border_opa(opa, 0)
            self.rings.append(c)
        self.pair_mark = glyphs.tinted(pair, "bluetooth", ring // 4, lv.color_hex(TEAL))
        self.pair_mark.center()
        _show(pair, False)
        # Beside it, the steps, and the PIN an older device asks for.
        steps = self.steps = _box(self.root, COL_X, 150, COL_W, 210)
        self.step_rings = []
        for i, text in enumerate(("Open Bluetooth on your phone", "Choose this name in its list", "Play anything")):
            ring = _box(steps, 0, i * 52, 32, 32)
            ring.set_style_radius(lv.RADIUS_CIRCLE, 0)
            ring.set_style_border_width(1, 0)
            num = _label(ring, F_SMALL, TEXT)
            num.set_text(str(i + 1))
            num.center()
            lbl = _label(steps, F_BODY, SUB)
            lbl.set_text(text)
            lbl.set_pos(48, i * 52 + 7)
            self.step_rings.append(ring)
        self.pin = _label(steps, F_SMALL, MUTED, 1)
        self.pin.set_pos(0, 168)
        _show(steps, False)

    def _build_text(self):
        cx, cw = COL_X, COL_W
        root = self.root
        # The source: the Bluetooth mark, the sender's name, its details.
        self.src_mark = glyphs.tinted(root, "bluetooth", 18, lv.color_hex(MUTED))
        self.src_mark.set_pos(cx - 3, SOURCE_Y)
        self.src_name = _label(root, F_SMALL, MUTED)
        self.src_name.set_pos(cx + 18, SOURCE_Y + 1)
        self.warn = _label(root, F_SMALL, AMBER)
        self.warn.set_width(cw - 150)
        self.warn.set_style_text_align(lv.TEXT_ALIGN.RIGHT, 0)
        self.warn.set_pos(cx + 150, SOURCE_Y + 1)
        # What's playing, top down, each line only when it has something.
        col = self.text = _box(root, cx, TEXT_Y, cw, 220)
        col.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        col.set_style_pad_row(6, 0)
        self.eyebrow = _label(col, F_SMALL, TEAL, 2)
        tf = F_TITLE
        self.title = _label(col, tf, TEXT)
        self.title.set_width(cw)
        self.title.set_style_text_line_space(-2, 0)
        self.title_font = tf
        self.artist = _label(col, F_BIG, SUB)
        self.artist.set_width(cw)
        self.artist.set_long_mode(lv.label.LONG_MODE.DOTS)
        self.album = _label(col, F_BODY, MUTED)
        self.album.set_width(cw)
        self.album.set_long_mode(lv.label.LONG_MODE.DOTS)
        self.meta = _label(col, F_SMALL, MUTED, 1)
        self.meta.set_width(cw)
        self.hint = _label(col, F_BODY, SUB)
        self.hint.set_width(cw)
        self.hint.set_style_text_line_space(4, 0)

    def _build_progress(self):
        x, y, w = PROGRESS
        root = self.root
        self.track = _box(root, x, y, w, 2)
        self.track.set_style_bg_opa(lv.OPA.COVER, 0)
        self.track.set_style_bg_color(lv.color_hex(LINE), 0)
        self.track.set_style_radius(1, 0)
        self.fill = _box(self.track, 0, 0, 0, 2)
        self.fill.set_style_bg_opa(lv.OPA.COVER, 0)
        self.fill.set_style_radius(1, 0)
        self.head = _box(root, x - 4, y - 3, 8, 8)
        self.head.set_style_bg_opa(lv.OPA.COVER, 0)
        self.head.set_style_radius(lv.RADIUS_CIRCLE, 0)
        self.head.set_style_bg_color(lv.color_hex(TEXT), 0)
        self.t_pos = _label(root, F_SMALL, MUTED, 1)
        self.t_len = _label(root, F_SMALL, MUTED, 1)
        self.t_pos.set_pos(x, y + 10)
        self.t_len.set_width(120)
        self.t_len.set_style_text_align(lv.TEXT_ALIGN.RIGHT, 0)
        self.t_len.set_pos(x + w - 120, y + 10)
        # The stream's details, between the two times.
        self.codec = _label(root, F_SMALL, MUTED)
        self.codec.set_width(w - 140)
        self.codec.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        self.codec.set_pos(x + 70, y + 10)

    def _build_transport(self):
        x, y, small, big, gap = TRANSPORT
        on = self.on
        dy = (big - small) // 2
        self.prev = RingButton(self.root, x, y + dy, small, BLACK, icon=glyphs.image("previous", small * 3 // 8),
                               on_press=lambda b: on["previous"](), color=0xDCE3EC, ring=1, hit=84,
                               on_hold=lambda b, held: on["seek"](-1 if held else 0))
        self.play = RingButton(self.root, x + small + gap, y, big, BLACK, icon=glyphs.image("play", big * 3 // 8),
                               on_press=lambda b: on["play"](), color=TEAL, ring=2, hit=92)
        self.next = RingButton(self.root, x + small + gap + big + gap, y + dy, small, BLACK,
                               icon=glyphs.image("next", small * 3 // 8),
                               on_press=lambda b: on["next"](), color=0xDCE3EC, ring=1, hit=84,
                               on_hold=lambda b, held: on["seek"](1 if held else 0))
        self._playing = False

    def _build_volume(self):
        x, y, w = VOLUME
        root = self.root
        self.vol_mark = glyphs.tinted(root, "volume", 22, lv.color_hex(MUTED))
        self.vol_mark.set_pos(x, y - 9)
        s = self.vol = lv.slider(root)
        s.set_range(0, 127)
        s.set_pos(x + 34, y)
        s.set_size(w - 34 - 8, 4)
        s.set_ext_click_area(22)
        s.set_style_bg_opa(lv.OPA.COVER, lv.PART.MAIN)
        s.set_style_bg_color(lv.color_hex(LINE), lv.PART.MAIN)
        s.set_style_radius(2, lv.PART.MAIN)
        s.set_style_radius(2, lv.PART.INDICATOR)
        s.set_style_bg_color(lv.color_hex(TEXT), lv.PART.KNOB)
        s.set_style_pad_all(6, lv.PART.KNOB)
        s.set_style_shadow_width(0, lv.PART.KNOB)
        s.set_style_border_width(0, lv.PART.KNOB)
        s.set_style_outline_width(0, lv.PART.KNOB)
        s.set_style_outline_width(0, lv.PART.MAIN | lv.STATE.FOCUSED)
        s.add_event_cb(self._vol_event, lv.EVENT.ALL, None)

    def _vol_event(self, e):
        code = e.get_code()
        if code == lv.EVENT.PRESSED:
            self._dragging = True
        elif code == lv.EVENT.VALUE_CHANGED:
            self.on["volume"](self.vol.get_value())
        elif code in (lv.EVENT.RELEASED, lv.EVENT.PRESS_LOST):
            self._dragging = False

    # -- what the app calls ---------------------------------------------

    def set_accent(self, rgb):
        """Take *rgb* as the screen's colour: from the cover, or the default."""
        self.accent = rgb
        c = lv.color_hex(rgb)
        self.root.set_style_bg_color(lv.color_hex(mix(BG, rgb, 0.14)), 0)
        self.eyebrow.set_style_text_color(c, 0)
        self.fill.set_style_bg_color(c, 0)
        self.play.set_color(rgb)
        self.bars.set_color(mix(BG, rgb, 0.85))
        self.vol.set_style_bg_color(c, lv.PART.INDICATOR)
        for ring in self.rings:
            ring.set_style_border_color(c, 0)
        for ring in self.step_rings:
            ring.set_style_border_color(c, 0)
        glyphs.tint(self.pair_mark, c)

    def show_pairing(self, name, pin=None):
        """Nothing connected: the name to pick on the phone, and the steps."""
        self._pairing(True)
        self._cover_shown(False)
        self.set_accent(TEAL)
        self._set_title(name)
        self.eyebrow.set_text("READY TO PAIR")
        _show(self.eyebrow, True)
        self._lines("", "", "", "")
        # The steps start under the name, however many lines it takes.
        self.text.update_layout()
        self.steps.set_y(max(150, TEXT_Y + self.title.get_y() + self.title.get_height() + 22))
        self.pin.set_text("PIN FOR OLDER DEVICES  %s" % pin if pin else "")
        self.show_source("", None)
        self._playback(False)

    def show_idle(self, peer):
        """Connected, nothing playing yet."""
        self._pairing(False)
        self._set_title(peer or "Connected")
        self.eyebrow.set_text("CONNECTED")
        _show(self.eyebrow, True)
        self._lines("", "", "", "Play something on your phone, or tap play.")
        self._playback(False, transport=True)

    def show_track(self, title, artist, album, number, count, genre):
        """A track: every line the sender filled in, and nothing for the rest."""
        self._pairing(False)
        self._set_title(title or "Untitled")
        meta = []
        if number:
            meta.append("TRACK %d OF %d" % (number, count) if count else "TRACK %d" % number)
        if genre:
            meta.append(genre.upper())
        self._lines(artist, album, "  /  ".join(meta), "")
        self._playback(True)

    def show_status(self, status):
        """The play status: the eyebrow over the title, and play or pause."""
        word = {"playing": "NOW PLAYING", "paused": "PAUSED", "stopped": "STOPPED", "error": "PLAYER ERROR",
                "seeking forward": "FAST FORWARD", "seeking back": "REWIND"}.get(status, "")
        self.eyebrow.set_text(word)
        _show(self.eyebrow, bool(word))
        playing = status == "playing"
        if playing != self._playing:
            self._playing = playing
            self.play.set_icon(glyphs.image("pause" if playing else "play", self.play.obj.get_width() * 3 // 8))

    def show_source(self, name, link):
        """The sender's name and what its link says: the codec, rate and
        channels under the progress bar, and its battery and signal at the
        top when they need saying."""
        self.src_name.set_text(name)
        _show(self.src_mark, bool(name))
        parts = []
        notes = []
        if link:
            if link.get("codec"):
                parts.append(link["codec"])
            rate = link.get("sample_rate")
            if rate:
                parts.append("%g kHz" % (rate / 1000))
            mode = link.get("channel_mode")
            if mode:
                parts.append(mode[0].upper() + mode[1:])
            battery = BATTERY.get(link.get("battery"))
            if battery:
                notes.append(battery)
            rssi = link.get("rssi_delta")
            if rssi is not None and rssi <= WEAK_DB:
                notes.append("Weak signal")
        self.codec.set_text("  /  ".join(parts))
        self.warn.set_text("  /  ".join(notes))

    def show_position(self, pos, length):
        if pos is None or not length:
            _show(self.head, False)
            self.fill.set_width(0)
            self.t_pos.set_text("")
            self.t_len.set_text(clock(length) if length else "")
            return
        text = clock(pos)
        if text == self._pos_text:
            return
        self._pos_text = text
        w = self.track.get_width()
        px = w * min(pos, length) // length
        self.fill.set_width(px)
        _show(self.head, True)
        self.head.set_x(PROGRESS[0] + px - 4)
        self.t_pos.set_text(text)
        self.t_len.set_text(clock(length))

    def show_volume(self, v):
        if not self._dragging:
            self.vol.set_value(v, False)

    def show_cover(self, pixels, w, h):
        """Show the cover, RGB565 *pixels* of *w* x *h*, or None for none."""
        if pixels is None:
            self._cover_shown(False)
            self.set_accent(TEAL)
            return
        dsc = lv.image_dsc_t()
        dsc.header.magic = lv.IMAGE_HEADER_MAGIC
        dsc.header.cf = lv.COLOR_FORMAT.RGB565
        dsc.header.w = w
        dsc.header.h = h
        dsc.header.stride = w * 2
        dsc.data_size = w * h * 2
        dsc.data = pixels
        self.keep["art"] = (dsc, pixels)  # LVGL holds a pointer, not a reference
        self.art.set_src(dsc)
        self._cover_shown(True)
        self.set_accent(accent_of(pixels, w, h))
        self.cover_box.set_style_shadow_color(lv.color_hex(self.accent), 0)
        self.cover_box.set_style_shadow_opa(90, 0)

    def show_levels(self, levels):
        self.bars.set_levels(levels)

    # -- inside ---------------------------------------------------------

    def _pairing(self, on):
        _show(self.pair, on)
        _show(self.steps, on)
        _show(self.cover_box, not on)
        _show(self.edge, not on)

    def _cover_shown(self, on):
        _show(self.art, on)
        _show(self.note, not on)
        if not on:
            self.cover_box.set_style_shadow_opa(0, 0)

    def _set_title(self, text):
        if text == self._title_text:
            return
        self._title_text = text
        t = self.title
        t.set_long_mode(lv.label.LONG_MODE.WRAP)
        t.set_height(lv.SIZE_CONTENT)
        t.set_text(text)
        t.update_layout()
        two = 2 * self.title_font.get_line_height()
        if t.get_height() > two + 4:
            t.set_long_mode(lv.label.LONG_MODE.DOTS)
            t.set_height(two)

    def _lines(self, artist, album, meta, hint):
        for lbl, text in ((self.artist, artist), (self.album, album), (self.meta, meta), (self.hint, hint)):
            lbl.set_text(text or "")
            _show(lbl, bool(text))

    def _playback(self, on, transport=None):
        """Show the progress and spectrum while a track is loaded; the
        transport while connected."""
        for o in (self.track, self.t_pos, self.t_len, self.codec, self.bars.obj):
            _show(o, on)
        if not on:
            _show(self.head, False)
            self._pos_text = None
        t = on if transport is None else transport
        for b in (self.prev, self.play, self.next):
            _show(b.obj, t)
        for o in (self.vol, self.vol_mark):
            _show(o, t)
