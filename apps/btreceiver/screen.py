# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The receiver's screen: the cover, what's playing, the transport, and calls.

`Screen` builds every widget once and then only changes them: a new track
sets some labels, a new cover sets one image, and the spectrum moves a few
bars. A call shows a card over the player until it ends. Nothing here talks
to Bluetooth; the app hands it what the sink and the hands-free unit say.
"""

import lvgl as lv
from controlkit import RingButton, SpectrumBars
from icons import lvgl as lvicons
from controlkit.theme import BLACK

from . import glyphs

BG = 0x0B0E14
TEXT = 0xFFFFFF
SUB = 0xC6CDD8  # the artist: a step down from the title
MUTED = 0x7D8799  # the album, the details and the times
LINE = 0x3A4458  # the thin outlines
TEAL = 0x4DB6AC  # the accent until a cover gives one
AMBER = 0xFFB74D  # a warning about the sender: its battery, its signal
GREEN = 0x66BB6A  # answer
RED = 0xEF5350  # decline and hang up

BANDS = 24
WEAK_DB = -10  # a link this far below the radio's ideal range is weak
# The phone's battery as its hands-free link reports it, 0 to 5, and the icon
# for each. At LOW_BATTERY or under it turns amber. A sender with no
# hands-free link, such as a computer, reports none.
BATTERY = ("battery_0_bar", "battery_1_bar", "battery_2_bar", "battery_4_bar", "battery_5_bar", "battery_full")
LOW_BATTERY = 1
# The sender's battery as AVRCP reports it, a state rather than a level, and
# the icon and colour for each: what shows without the hands-free link's. A
# sender that reports neither shows none.
PLAYER_BATTERY = {"full": ("battery_full", MUTED), "normal": ("battery_5_bar", MUTED),
                  "warning": ("battery_2_bar", AMBER), "critical": ("battery_0_bar", AMBER),
                  "external": ("battery_charging_full", MUTED)}
SIGNAL_BARS = 4  # the phone's signal, 0 to 5, as this many bars
# What the card says over the caller for each of HandsFree's call states.
# The calls setting's label, beside its switch in the header.
CALLS_LABEL = "Phone calls and battery"
STATUS_W = 120  # the shell's status line, moved to the label's left
HEADER_ROOM = 480  # the least header width the switch, its label and the status line share with the title
# The pairing steps as one paragraph, where there's no room for them numbered.
STEPS_TEXT = "Open Bluetooth on your phone, choose this name in its list, and play anything."
CALL_WORDS = {"incoming": "INCOMING CALL", "dialing": "CALLING", "alerting": "RINGING", "active": "ON A CALL",
              "held": "ON HOLD"}


def _font(*sizes):
    for s in sizes:
        f = getattr(lv, "font_montserrat_%d" % s, None)
        if f is not None:
            return f
    return lv.font_get_default()


F_HUGE = _font(40, 32, 28, 24)
F_TITLE = _font(32, 28, 24)
F_BIG = _font(24, 20, 16)
F_MID = _font(20, 18, 16)
F_BODY = _font(16, 14)
F_SMALL = _font(14, 12)
F_TINY = _font(12, 14)


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


MODE_ICON = 24
MODE_HIT = 40  # each button's square, a finger's size around the icon
WIDE = (600, 360)  # an app area this big or bigger has the cover on the left, the rest in a column beside it
COLUMN = 360  # that column's width
SMALL = (400, 220)  # under this width or height, the smallest controls and fonts
ROUND_MARGIN = 6  # how far everything keeps in from a round screen's edge
CAP = 30  # the top of a round screen the compact status bar covers
SWITCH_ROOM = (250, 160)  # the calls setting's width at the top right of the app's area, and on a small one
# What each size of screen uses: the margin, the transport's small ring, play
# ring and gap, the gap between the two rows of modes and volume, and the
# call card's small ring, main ring and gap.
METRICS = {
    "large": (24, 56, 72, 14, 44, 64, 80, 40),
    "medium": (12, 44, 56, 12, 36, 48, 60, 24),
    "small": (8, 36, 44, 10, 32, 36, 44, 20),
}


class Layout:
    """Where everything goes in an app area *w* x *h* pixels.

    An area of 600 x 360 or more has the cover on the left and the rest in a
    column beside it. A smaller landscape area (480 x 320, 320 x 240) keeps
    the cover and the column, with the sender's line along the top and the
    progress bar, the transport and the volume along the bottom. A square or
    round screen stacks everything in one column down the middle, and drops
    the cover, then the album and the details, when there's no room for them.

    *switch* is True when the calls setting sits in the app's area, not in
    the shell's header: room is kept for it at the top. *round_* keeps
    everything inside a round screen's circle.
    """

    def __init__(self, w, h, switch=False, round_=False):
        self.w, self.h = w, h
        self.round = round_
        self.switch = switch
        small = w < SMALL[0] or h < SMALL[1]
        if w >= WIDE[0] and h >= WIDE[1]:
            self.kind, size = "wide", "large"
        elif w > h * 5 // 4 and not round_:
            self.kind, size = "side", "small" if small else "medium"
        else:
            self.kind, size = "stack", "small" if small else "medium"
        self.size = size
        m, ring, play, gap, rows, csmall, cbig, cgap = METRICS[size]
        self.m = m
        self.mode_rows = rows
        self.call_rings = (csmall, cbig, cgap)
        if size == "large":
            self.fonts = (F_TITLE, F_BIG, F_BODY, F_SMALL)  # title, artist, album, details
            self.title_lines = 2
            self.caller_font = F_HUGE
            self.step_font, self.step_pitch, self.step_ring = F_BODY, 52, 32
        elif size == "medium":
            self.fonts = (F_BIG, F_BODY, F_SMALL, F_TINY)
            self.title_lines = 1
            self.caller_font = F_TITLE
            self.step_font, self.step_pitch, self.step_ring = F_SMALL, 36, 26
        else:
            self.fonts = (F_MID, F_SMALL, F_TINY, F_TINY)
            self.title_lines = 1
            self.caller_font = F_MID
            self.step_font, self.step_pitch, self.step_ring = F_TINY, 30, 22
        self.ring, self.play, self.gap = ring, play, gap
        self.extras = True  # the album and the details
        self.eyebrow = True  # NOW PLAYING over the title
        self.center = False  # each line centred, not from the left
        self.switch_at = None  # where the calls setting goes when it's in the app's area
        self.bottom = h
        self.codec = True  # the stream's details between the two times
        self.times = True  # the two times under the progress bar
        getattr(self, "_" + self.kind)()
        self.pair_ring = self.cover[2] * 300 // 368
        if not hasattr(self, "modes"):
            # Shuffle over the volume's mark, repeat over the slider's end.
            vx, vw = self.volume[0], self.volume[1]
            margin = (MODE_HIT - MODE_ICON) // 2
            self.modes = (vx - margin, vx + vw - 8 - MODE_ICON - margin)

    def _text_need(self):
        """How tall the lines about the track are, with what's shown."""
        title, artist, album, meta = self.fonts
        need = self.title_lines * title.get_line_height() + artist.get_line_height() + 6
        if self.eyebrow:
            need += F_SMALL.get_line_height() + 6
        if self.extras:
            need += album.get_line_height() + meta.get_line_height() + 12
        return need

    def _rows(self, y):
        """The transport's row at *y*: where the volume sits alone, and the
        middles of the modes' row and the volume's row under it."""
        mid = y + self.play // 2
        half = self.mode_rows // 2
        return mid, mid - half, mid + half

    def _wide(self):
        w, h, m = self.w, self.h, self.m
        s = min(h - 2 * m, w - 3 * m - COLUMN)
        cy = (h - s) // 2
        self.cover = (m, cy, s)
        cx = m + s + m
        cw = w - m - cx
        self.source = (cx, max(cy, 44) if self.switch else cy, cw)
        ty = self.source[1] + 36
        trans_y = h - m - self.play + 6
        py = trans_y - 34
        self.spectrum = (cx, py - 46, cw, 30)
        self.text = (cx, ty, cw, py - 46 - 6 - ty)
        self.progress = (cx, py, cw)
        self.transport = (cx, trans_y)
        end = cx + 2 * self.ring + self.play + 2 * self.gap
        alone, over, under = self._rows(trans_y)
        self.volume = (end + 22, cx + cw - end - 22, alone, over, under)
        self.steps = (cx, cw, 150)
        self._call_side(cx, cw, ty)
        if self.switch:
            self.switch_at = ("right", 8)

    def _side(self):
        w, h, m = self.w, self.h, self.m
        strip = 34 if self.size == "medium" else 30
        # The sender's line along the top, beside the calls setting.
        room = (SWITCH_ROOM[0] if self.size == "medium" else SWITCH_ROOM[1]) if self.switch else 0
        self.source = (m, 4 + strip // 2 - 9, w - 2 * m - room)
        top = 4 + strip + 2
        trans_y = h - m - self.play
        py = trans_y - (34 if self.size == "medium" else 30)
        s = min(py - 14 - top, w * 2 // 5)
        self.cover = (m, top, s)
        cx = m + s + (16 if self.size == "medium" else 12)
        cw = w - m - cx
        text_h = py - 12 - top + 4
        need = self._text_need()
        if text_h < need:
            self.extras = False
        self.spectrum = None
        if text_h >= self._text_need() + 28:
            self.spectrum = (cx, py - 14 - 22, cw, 22)
            text_h = py - 14 - 22 - 6 - top + 4
        self.text = (cx, top - 4, cw, text_h)
        self.progress = (m, py, w - 2 * m)
        self.transport = (m, trans_y)
        end = m + 2 * self.ring + self.play + 2 * self.gap
        right = w - m
        vx = end + (24 if self.size == "medium" else 16)
        vw = min(220, right - vx)
        alone, over, under = self._rows(trans_y)
        self.volume = (right - vw, vw, alone, over, under)
        # A small screen has no room for the numbered steps: they're a
        # paragraph under the name, and the stream's details are left out.
        self.steps = (cx, cw, top + 50) if self.size == "medium" else None
        self.codec = self.size == "medium"
        self._call_side(cx, cw, top)
        if self.switch:
            self.switch_at = ("right", 4 + strip // 2 - 13)

    def _call_side(self, cx, cw, ty):
        """The call card beside the cover: its lines, then its buttons along
        the bottom, under the lines when they fit there."""
        small, big, gap = self.call_rings
        by = self.h - big - 36 if self.kind == "wide" else self.h - self.m - (26 if self.size == "medium" else 20) - big
        x = cx if cw >= 2 * small + big + 2 * gap else self.m
        self.call_text = (cx, ty, cw, by - 8 - ty)
        self.call_buttons = (x, by, x)

    def _band(self, y0, y1):
        """``(x, width)``: the band rows *y0* to *y1* can use: the screen
        less its margins, or on a round screen the inside of the circle,
        clear of the Home button on the diagonal at the top right."""
        w, m = self.w, self.m
        if not self.round:
            return m, w - 2 * m
        r = w // 2
        reach = r - ROUND_MARGIN
        half = r
        for y in (y0, y1):
            dy = r - y
            half = min(half, int(max(0, reach * reach - dy * dy) ** 0.5))
        x0, x1 = r - half, r + half
        hx, hy, d = self.home
        if y0 < hy + d and y1 > hy:
            x1 = min(x1, hx - 6)
        return x0, max(0, x1 - x0)

    def _stack(self):
        w, h, m = self.w, self.h, self.m
        medium = self.size == "medium"
        # appkit's round Home button: a circle on the diagonal at the top right.
        d = max(36, w // 6)
        off = int((w // 2 - 4 - d / 2) * 0.7071)
        self.home = (w // 2 + off - d // 2, w // 2 - off - d // 2, d)
        top = CAP if self.round else m
        bottom = h - (h // 14 if self.round else m)
        g = 8 if medium else 3
        # The calls setting's row. Beside the Home button on a small round
        # screen there's no room for its label: a handset stands for it.
        self.switch_icon = False
        if self.switch:
            bw = self._band(top, top + 36)[1]
            self.switch_icon = bw - 10 - 48 < 90
        switch_h = self.switch_h = (30 if self.switch_icon else 36) if self.switch else 0
        rows = {"source": 22, "times": 34 if medium else 28, "volume": 30}

        def room():
            used = switch_h + self._text_need() + self.play + sum(rows.values()) + g * (len(rows) + 2)
            return bottom - top - used

        # What goes when there isn't room, least missed first.
        for drop in ("extras", "eyebrow", "source", "codec", "times"):
            if room() >= 48 or (drop != "extras" and room() >= 0):
                break
            if drop == "extras":
                self.extras = False
            elif drop == "eyebrow":
                self.eyebrow = False
            elif drop == "source":
                del rows["source"]
            elif drop == "codec":
                self.codec = False
            else:
                rows["times"] = 12
                self.times = False
        if not medium:
            self.codec = False  # no room for the stream's details between the times
        y = top
        self.center = True
        if self.switch:
            self.switch_at = ("center", y) + self._band(y, y + switch_h)
            y += switch_h
        if "source" in rows:
            x, bw = self._band(y, y + 22)
            self.source = (x + 8, y, bw - 16)
            y += 22 + g
        else:
            self.source = None
        # The cover takes what's left, kept clear of the Home button.
        s = max(0, min(room() - g, w // 2))
        if self.round and s:
            hx, hy, hd = self.home
            if y < hy + hd:
                s = min(s, 2 * (hx - 6 - w // 2))
        if s < 48:
            s = 0
        y += max(0, room() - g - s) // 2  # what's spare goes above and below
        self.cover = ((w - s) // 2, y, s)
        if s:
            y += s + g
        need = self._text_need()
        x, bw = self._band(y, y + need)
        self.text = (x, y, bw, need)
        self.spectrum = None
        y += need + g
        th = rows["times"]
        x, bw = self._band(y, y + th)
        self.progress = (x + 8, y + 3, bw - 16)
        y += th + g
        # The volume on a row of its own, shuffle and repeat at its ends,
        # then the transport at the bottom, where round buttons fit a round
        # screen best.
        x, bw = self._band(y, y + rows["volume"])
        vw = min(bw - 2 * MODE_HIT, 240)
        mid = y + rows["volume"] // 2
        vx = (w - vw) // 2
        self.volume = (vx, vw, mid, mid, mid)
        self.modes = (vx - MODE_HIT, vx + vw - 4)
        y += rows["volume"] + g
        row = 2 * self.ring + self.play + 2 * self.gap
        self.transport = ((w - row) // 2, y)
        self.steps = None  # the steps go in a paragraph under the name
        self.bottom = bottom
        self.paragraph = self._band(self.text[1] + 40, bottom - 30)
        small, big, gap = self.call_rings
        by = bottom - 20 - big
        # Its captions' row has to fit inside a round screen too.
        while self.round and self._band(by + big, by + big + 20)[1] < 2 * small + big + 4 * gap and by > self.text[1] + 60:
            by -= 4
        ty = self.text[1]
        x, bw = self._band(ty, by - 4)
        self.call_text = (x, ty, bw, by - 4 - ty)
        self.call_buttons = ((w - 2 * big - 2 * gap) // 2, by, (w - 2 * small - big - 2 * gap) // 2)


class Screen:
    """Everything on the receiver's screen, in *root* (*size* pixels), laid
    out for that size by `Layout`. *switch* and *round_* are `Layout`'s.

    *on* maps ``"play"``, ``"next"``, ``"previous"``, ``"seek"``, ``"repeat"``,
    ``"shuffle"`` and ``"volume"`` to what the buttons and the slider do, and
    ``"answer"``, ``"hangup"``, ``"mute"`` and ``"route"`` to the call card's
    buttons.
    """

    def __init__(self, root, size, on, switch=False, round_=False):
        self.root = root
        self.lay = lay = Layout(size[0], size[1], switch, round_)
        self.on = on
        self.accent = TEAL
        self.keep = {}
        self._dragging = False
        self._title_text = None
        self._pos_text = None
        self._link_notes = []
        self._phone_notes = []
        self._phone_battery = None
        self._player_battery = None
        self.call_state = None
        root.remove_flag(lv.obj.FLAG.SCROLLABLE)
        root.set_style_bg_opa(lv.OPA.COVER, 0)
        root.set_style_bg_grad_dir(lv.GRAD_DIR.VER, 0)
        root.set_style_bg_grad_color(lv.color_hex(BG), 0)
        root.set_style_bg_main_stop(0, 0)
        root.set_style_bg_grad_stop(230, 0)

        self._build_cover(*lay.cover)
        self._build_text()
        self._build_progress()
        self._build_transport()
        self._build_volume()
        self._build_modes()
        # The spectrum, where there's room for it.
        x, y, w, h = lay.spectrum or (0, 0, BANDS * 2, 4)
        self.bars = SpectrumBars(root, x, y, w, h, BLACK, bands=BANDS, gap=w // BANDS * 3 // 5, color=TEAL)
        self.has_bars = lay.spectrum is not None
        self._build_call(size)
        # The sender's line stays over the call card: the battery always shows.
        for o in (self.src_mark, self.src_name, self.signal, self.battery, self.warn):
            o.move_foreground()
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
        self.note = glyphs.tinted(box, "note", max(8, s * 2 // 5), lv.color_hex(0x3A4458))
        self.note.center()
        # A hairline on top of the art, so a dark cover still has an edge.
        edge = self.edge = _box(self.root, x, y, s, s)
        edge.set_style_radius(18, 0)
        edge.set_style_border_width(1, 0)
        edge.set_style_border_color(lv.color_hex(0xFFFFFF), 0)
        edge.set_style_border_opa(36, 0)
        # Pairing: the Bluetooth mark in rings, where the cover goes.
        pair = self.pair = _box(self.root, x, y, s, s)
        ring = self.lay.pair_ring
        self.rings = []
        for d, opa in ((ring, 50), (ring * 7 // 10, 90), (ring * 2 // 5, 255)):
            c = _box(pair, (s - d) // 2, (s - d) // 2, d, d)
            c.set_style_radius(lv.RADIUS_CIRCLE, 0)
            c.set_style_border_width(1, 0)
            c.set_style_border_opa(opa, 0)
            self.rings.append(c)
        self.pair_mark = glyphs.tinted(pair, "bluetooth", max(8, ring // 4), lv.color_hex(TEAL))
        self.pair_mark.center()
        _show(pair, False)
        # Beside it, the steps, and the PIN an older device asks for.
        lay = self.lay
        sx, sw, _ = lay.steps or (0, COLUMN, 0)
        pitch, d, font = lay.step_pitch, lay.step_ring, lay.step_font
        steps = self.steps = _box(self.root, sx, 150, sw, 4 * pitch + 10)
        self.step_rings = []
        for i, text in enumerate(("Open Bluetooth on your phone", "Choose this name in its list", "Play anything")):
            ring = _box(steps, 0, i * pitch, d, d)
            ring.set_style_radius(lv.RADIUS_CIRCLE, 0)
            ring.set_style_border_width(1, 0)
            num = _label(ring, F_SMALL if d > 24 else F_TINY, TEXT)
            num.set_text(str(i + 1))
            num.center()
            lbl = _label(steps, font, SUB)
            lbl.set_width(sw - d * 3 // 2)
            lbl.set_text(text)
            lbl.set_pos(d * 3 // 2, i * pitch + (d - font.get_line_height()) // 2)
            self.step_rings.append(ring)
        self.pin = _label(steps, F_SMALL if d > 24 else F_TINY, MUTED, 1)
        self.pin.set_width(sw)
        self.pin.set_pos(0, 3 * pitch + 12)
        _show(steps, False)

    def _build_text(self):
        lay = self.lay
        root = self.root
        if lay.source is None:
            # No room for the sender's line: its parts are made, and stay hidden.
            root = _box(self.root, 0, 0, 1, 1)
            _show(root, False)
        cx, sy, cw = lay.source or (0, 0, COLUMN)
        # The source: the Bluetooth mark, the sender's name, its details.
        self.src_mark = glyphs.tinted(root, "bluetooth", 18, lv.color_hex(MUTED))
        self.src_mark.set_pos(cx - 3, sy)
        self.src_name = _label(root, F_SMALL, MUTED)
        wx = 150 if cw >= COLUMN else cw * 3 // 5  # where a warning starts
        if cw < COLUMN:
            self.src_name.set_size(wx - 24, F_SMALL.get_line_height())
            self.src_name.set_long_mode(lv.label.LONG_MODE.DOTS)
        self.src_name.set_pos(cx + 18, sy + 1)
        # The sender's battery at the right end, on its side like a phone's.
        self.battery = lvicons.image(root, "battery_full", 24, lv.color_hex(MUTED))
        self.battery.set_rotation(900)
        self.battery.set_pos(cx + cw - 22, sy - 3)
        self.battery_state = None
        _show(self.battery, False)
        # The phone's signal beside it: thin bars, filled up to the level.
        sig = self.signal = _box(root, cx + cw - 56, sy + 3, 4 * SIGNAL_BARS + 3 * (SIGNAL_BARS - 1), 14)
        self.signal_bars = []
        for i in range(SIGNAL_BARS):
            h = 5 + i * 3
            bar = _box(sig, i * 7, 14 - h, 4, h)
            bar.set_style_radius(1, 0)
            bar.set_style_border_width(1, 0)
            bar.set_style_border_color(lv.color_hex(MUTED), 0)
            bar.set_style_bg_color(lv.color_hex(MUTED), 0)
            self.signal_bars.append(bar)
        self.signal_state = None
        _show(sig, False)
        self.warn = _label(root, F_SMALL, AMBER)
        self.warn.set_size(cw - wx - 68, F_SMALL.get_line_height())
        self.warn.set_long_mode(lv.label.LONG_MODE.DOTS)
        self.warn.set_style_text_align(lv.TEXT_ALIGN.RIGHT, 0)
        self.warn.set_pos(cx + wx, sy + 1)
        # What's playing, top down, each line only when it has something.
        tx, ty, tw, th = lay.text
        col = self.text = _box(self.root, tx, ty, tw, th)
        col.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        col.set_style_pad_row(6, 0)
        if lay.center:
            col.set_flex_align(lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
        tf, af, bf, mf = lay.fonts
        self.eyebrow = _label(col, F_SMALL, TEAL, 2)
        self.title = _label(col, tf, TEXT)
        self.title.set_width(tw)
        self.title.set_style_text_line_space(-2, 0)
        self.title_font = tf
        self.artist = _label(col, af, SUB)
        self.artist.set_width(tw)
        self.artist.set_long_mode(lv.label.LONG_MODE.DOTS)
        self.album = _label(col, bf, MUTED)
        self.album.set_width(tw)
        self.album.set_long_mode(lv.label.LONG_MODE.DOTS)
        self.meta = _label(col, mf, MUTED, 1)
        self.meta.set_width(tw)
        self.meta.set_long_mode(lv.label.LONG_MODE.DOTS)
        self.hint = _label(col, F_BODY if lay.size != "small" else F_SMALL, SUB)
        self.hint.set_width(tw)
        self.hint.set_style_text_line_space(4, 0)
        if lay.center:
            for lbl in (self.title, self.artist, self.album, self.meta, self.hint):
                lbl.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        # The pairing steps as a paragraph, where they don't fit numbered.
        # Lower down a round screen is wider: it takes the width it has there.
        px, pw = lay.paragraph if lay.center else (tx, tw)
        self.para = _label(self.root, F_BODY if lay.size == "medium" else F_SMALL, SUB)
        self.para.set_pos(px, ty)
        self.para.set_width(pw)
        if lay.center:
            self.para.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        _show(self.para, False)

    def _build_progress(self):
        x, y, w = self.lay.progress
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
        font = F_TINY if self.lay.size == "small" else F_SMALL
        tw = 120 if w >= COLUMN else 56
        self.t_pos = _label(root, font, MUTED, 1)
        self.t_len = _label(root, font, MUTED, 1)
        self.t_pos.set_pos(x, y + 10)
        self.t_len.set_width(tw)
        self.t_len.set_style_text_align(lv.TEXT_ALIGN.RIGHT, 0)
        self.t_len.set_pos(x + w - tw, y + 10)
        # The stream's details, between the two times, on one line.
        self.codec = _label(root, font, MUTED)
        self.codec.set_size(w - 140, font.get_line_height())
        self.codec.set_long_mode(lv.label.LONG_MODE.DOTS)
        self.codec.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        self.codec.set_pos(x + 70, y + 10)

    def _build_transport(self):
        lay = self.lay
        x, y = lay.transport
        small, big, gap = lay.ring, lay.play, lay.gap
        on = self.on
        dy = (big - small) // 2
        self.prev = RingButton(self.root, x, y + dy, small, BLACK, icon=glyphs.image("previous", small * 3 // 8),
                               on_press=lambda b: on["previous"](), color=0xDCE3EC, ring=1, hit=small + 28,
                               on_hold=lambda b, held: on["seek"](-1 if held else 0))
        self.play = RingButton(self.root, x + small + gap, y, big, BLACK, icon=glyphs.image("play", big * 3 // 8),
                               on_press=lambda b: on["play"](), color=TEAL, ring=2, hit=big + 20)
        self.next = RingButton(self.root, x + small + gap + big + gap, y + dy, small, BLACK,
                               icon=glyphs.image("next", small * 3 // 8),
                               on_press=lambda b: on["next"](), color=0xDCE3EC, ring=1, hit=small + 28,
                               on_hold=lambda b, held: on["seek"](1 if held else 0))
        self._playing = False

    def _build_volume(self):
        x, w, y = self.lay.volume[:3]
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

    def _build_modes(self):
        # Repeat and shuffle, lit in the accent while on; "single" marks the
        # repeat with a small 1, as the icons package has no repeat-one icon.
        # Over the volume they line up with its mark and the slider's end; on
        # a row with it, they sit at its ends.
        sx, rx = self.lay.modes
        y = self.lay.volume[3]
        self._modes = (None, None)
        self._modes_on = False
        self.shuffle, self.shuffle_icon = self._mode_button(sx, y, "shuffle")
        self.repeat, self.repeat_icon = self._mode_button(rx, y, "repeat")
        one = self.repeat_one = _label(self.repeat, F_TINY, TEXT)
        one.set_text("1")
        one.align_to(self.repeat_icon, lv.ALIGN.TOP_RIGHT, 6, -8)
        _show(one, False)

    def _mode_button(self, x, y, name):
        """A button for mode *name* with the icon of that name: ``(button, icon)``."""
        b = _box(self.root, x, y - MODE_HIT // 2, MODE_HIT, MODE_HIT)
        b.add_flag(lv.obj.FLAG.CLICKABLE)
        b.add_event_cb(lambda e: self.on[name](), lv.EVENT.CLICKED, None)
        img = lvicons.image(b, name, MODE_ICON, lv.color_hex(MUTED))
        img.center()
        img.remove_flag(lv.obj.FLAG.CLICKABLE)
        _show(b, False)
        return b, img

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
        self._paint_modes()

    def show_pairing(self, name, pin=None):
        """Nothing connected: the name to pick on the phone, and the steps."""
        self._pairing(True)
        self._cover_shown(False)
        self.set_accent(TEAL)
        self._set_title(name)
        self.eyebrow.set_text("READY TO PAIR")
        _show(self.eyebrow, self.lay.eyebrow)
        self._lines("", "", "", "")
        # The steps start under the name, however many lines it takes.
        self.text.update_layout()
        lay = self.lay
        pin_text = "PIN FOR OLDER DEVICES  %s" % pin if pin else ""
        self.pin.set_text(pin_text)
        if lay.steps is None:
            # No room for the numbered steps: they're a paragraph under the name.
            para = self.para
            para.set_text(STEPS_TEXT + ("\n" + pin_text if pin else ""))
            para.set_y(lay.text[1] + self.title.get_y() + self.title.get_height() + 8)
            _show(para, True)
        else:
            self.steps.set_y(max(lay.steps[2], lay.text[1] + self.title.get_y() + self.title.get_height() + 22))
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
        _show(self.eyebrow, bool(word) and self.lay.eyebrow)
        playing = status == "playing"
        if playing != self._playing:
            self._playing = playing
            self.play.set_icon(glyphs.image("pause" if playing else "play", self.play.obj.get_width() * 3 // 8))

    def show_source(self, name, link):
        """The sender's name and what its link says: the codec, rate and
        channels under the progress bar once the rate is known, its battery
        whenever it reports one, and a weak signal."""
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
            else:
                parts = []  # no stream yet: no codec to speak of
            rssi = link.get("rssi_delta")
            if rssi is not None and rssi <= WEAK_DB:
                notes.append("Weak signal")
        self.codec.set_text("  /  ".join(parts))
        self._link_notes = notes
        self._notes()
        self._player_battery = link.get("battery") if link else None
        self._show_battery()

    def show_phone(self, battery, signal, service):
        """The phone's battery and signal from its hands-free link, each 0 to
        5 or None for none, and whether it has network service (None when it
        hasn't said). Its battery shows in place of the player's."""
        self._phone_battery = battery
        self._show_battery()
        state = (signal, service)
        if state != self.signal_state:
            self.signal_state = state
            _show(self.signal, signal is not None)
            if signal is not None:
                lit = 0 if service is False else (max(0, min(5, signal)) * SIGNAL_BARS + 2) // 5
                for i, bar in enumerate(self.signal_bars):
                    bar.set_style_bg_opa(lv.OPA.COVER if i < lit else lv.OPA.TRANSP, 0)
            self._phone_notes = ["No service"] if service is False else []
            self._notes()

    def _notes(self):
        self.warn.set_text("  /  ".join(self._phone_notes + self._link_notes))

    def _show_battery(self):
        # The hands-free link's level, 0 to 5, else the player's state.
        state = self._phone_battery if self._phone_battery is not None else self._player_battery
        if state == self.battery_state:
            return
        self.battery_state = state
        if state is None or (isinstance(state, str) and state not in PLAYER_BATTERY):
            _show(self.battery, False)
            return
        if isinstance(state, str):
            icon, colour = PLAYER_BATTERY[state]
        else:
            level = max(0, min(5, state))
            icon, colour = BATTERY[level], AMBER if level <= LOW_BATTERY else MUTED
        self.battery.set_src(lvicons.dsc(icon, 24))
        self.battery.set_style_image_recolor(lv.color_hex(colour), 0)
        _show(self.battery, True)

    def show_modes(self, repeat, shuffle):
        """The sender's *repeat* ("off", "single", "all" or "group") and
        *shuffle* ("off", "all" or "group"). A button for a mode the sender
        doesn't report (None) is hidden; with neither, the volume moves back
        beside the play button."""
        modes = (repeat, shuffle)
        if modes == self._modes:
            return
        self._modes = modes
        self._place_modes()
        self._paint_modes()

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
        self.head.set_x(self.lay.progress[0] + px - 4)
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

    def show_call(self, state, caller, phone, here, muted, mic, takes=True):
        """The call card for HandsFree's call *state*, or none for ``None``
        and ``"idle"``.

        *caller* is the other side's number, *phone* the phone's name, *here*
        whether the call's audio is on the board, *muted* whether the
        microphone is off, and *mic* whether the board has one to send.
        *takes* is False on a board that can't take a call's audio at all:
        the card then answers and hangs up only, and the call stays on the
        phone.
        """
        on = state in CALL_WORDS
        self.call_state = state if on else None
        _show(self.card, on)
        if not on:
            return
        ringing = state == "incoming"
        self.call_word.set_text(CALL_WORDS[state])
        self.caller.set_text(caller or "Unknown number")
        self.call_phone.set_text("on %s" % phone if phone else "")
        _show(self.call_phone, bool(phone))
        if not takes:
            note = "The call's audio stays on the phone"
        elif ringing:
            note = "Answer here to talk through this speaker"
        elif not here:
            note = "Talking on the phone"
        elif not mic:
            note = "This board can't send its microphones: the caller can't hear you"
        elif muted:
            note = "Microphones off"
        else:
            note = "Talking through this speaker and its microphones"
        self.call_note.set_text(note)
        _show(self.call_time, state == "active")
        colour = GREEN if ringing else self.accent
        for ring in self.call_rings:
            ring.set_style_border_color(lv.color_hex(colour), 0)
        glyphs.tint(self.call_mark, lv.color_hex(colour))
        self.call_word.set_style_text_color(lv.color_hex(colour), 0)
        for b in (self.answer, self.decline):
            _show(b.obj, ringing)
        for b in (self.mute, self.route):
            _show(b.obj, not ringing and takes)
        _show(self.hang.obj, not ringing)
        for lbl in self.ring_labels:
            _show(lbl, ringing)
        for i, lbl in enumerate(self.call_labels):
            _show(lbl, not ringing and (takes or i == 2))
        self.mute.set_icon(glyphs.image("mic_off" if muted else "mic", self._icon_small))
        self.mute.set_enabled(here and mic)
        self.call_labels[0].set_text("Unmute" if muted else "Mute")
        self.route.set_icon(glyphs.image("phone" if here else "volume", self._icon_small))
        self.call_labels[1].set_text("Use phone" if here else "Use speaker")

    def show_call_time(self, ms):
        """How long the call has been answered."""
        self.call_time.set_text(clock(ms))

    # -- inside ---------------------------------------------------------

    def _place_modes(self):
        repeat, shuffle = self._modes
        on = self._modes_on
        _show(self.repeat, on and repeat is not None)
        _show(self.shuffle, on and shuffle is not None)
        _, _, alone, _, under = self.lay.volume
        y = under if repeat is not None or shuffle is not None else alone
        self.vol_mark.set_y(y - 9)
        self.vol.set_y(y)

    def _paint_modes(self):
        repeat, shuffle = self._modes
        for icon, mode in ((self.repeat_icon, repeat), (self.shuffle_icon, shuffle)):
            lit = mode not in (None, "off")
            icon.set_style_image_recolor(lv.color_hex(self.accent if lit else MUTED), 0)
        _show(self.repeat_one, repeat == "single")
        self.repeat_one.set_style_text_color(lv.color_hex(self.accent), 0)

    def _build_call(self, size):
        """The call card: over everything but the sender's line, hidden
        until a call."""
        on = self.on
        card = self.card = _box(self.root, 0, 0, size[0], size[1])
        card.add_flag(lv.obj.FLAG.CLICKABLE)  # nothing under it takes a touch
        card.set_style_bg_opa(lv.OPA.COVER, 0)
        card.set_style_bg_color(lv.color_hex(BG), 0)
        lay = self.lay
        x, y, s = lay.cover
        rings = _box(card, x, y, s, s)
        self.call_rings = []
        ring = lay.pair_ring
        for d, opa in ((ring, 50), (ring * 7 // 10, 90), (ring * 2 // 5, 255)):
            c = _box(rings, (s - d) // 2, (s - d) // 2, d, d)
            c.set_style_radius(lv.RADIUS_CIRCLE, 0)
            c.set_style_border_width(1, 0)
            c.set_style_border_opa(opa, 0)
            self.call_rings.append(c)
        self.call_mark = glyphs.tinted(rings, "handset", max(8, ring // 4), lv.color_hex(GREEN))
        self.call_mark.center()
        _show(rings, s > 0)
        cx, cy, cw, ch = lay.call_text
        col = _box(card, cx, cy, cw, ch)
        col.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        col.set_style_pad_row(8 if lay.size == "large" else 4, 0)
        if lay.center:
            col.set_flex_align(lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
        small_font = lay.size == "small"
        self.call_word = _label(col, F_SMALL, GREEN, 2)
        self.caller = _label(col, lay.caller_font, TEXT)
        self.caller.set_size(cw, lay.caller_font.get_line_height())
        self.caller.set_long_mode(lv.label.LONG_MODE.DOTS)
        self.call_phone = _label(col, F_SMALL if small_font else F_BODY, SUB)
        self.call_time = _label(col, F_BODY if small_font else F_BIG, MUTED, 1)
        self.call_note = _label(col, F_TINY if small_font else F_SMALL, MUTED)
        self.call_note.set_width(cw)
        if lay.size != "large":
            self.call_note.set_height((F_TINY if small_font else F_SMALL).get_line_height())
            self.call_note.set_long_mode(lv.label.LONG_MODE.DOTS)
        if lay.center:
            for lbl in (self.caller, self.call_note):
                lbl.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        bx, by, ax = lay.call_buttons
        small, big, gap = lay.call_rings
        self._icon_small = small * 3 // 8
        dy = (big - small) // 2

        def button(x, y, d, icon, colour, fn):
            return RingButton(card, x, y, d, BLACK, icon=glyphs.image(icon, d * 3 // 8), on_press=lambda b: fn(),
                              color=colour, ring=1 if d == small else 2, hit=d + 20)

        def caption(x, d, text):
            lbl = _label(card, F_TINY if small_font else F_SMALL, MUTED)
            lbl.set_text(text)
            lbl.update_layout()  # one line, centred under its button
            lbl.set_pos(x + d // 2 - lbl.get_width() // 2, by + big + (4 if small_font else 10))
            return lbl

        # Ringing: decline, then answer.
        self.decline = button(bx, by, big, "hangup", RED, lambda: on["hangup"]())
        self.answer = button(bx + big + gap * 2, by, big, "handset", GREEN, lambda: on["answer"]())
        self.ring_labels = [caption(bx, big, "Decline"), caption(bx + big + gap * 2, big, "Answer")]
        # Answered: mute, where the audio goes, and hang up.
        self.mute = button(ax, by + dy, small, "mic", 0xDCE3EC, lambda: on["mute"]())
        self.route = button(ax + small + gap, by + dy, small, "phone", 0xDCE3EC, lambda: on["route"]())
        hx = ax + 2 * (small + gap)
        self.hang = button(hx, by, big, "hangup", RED, lambda: on["hangup"]())
        self.call_labels = [caption(ax, small, "Mute"), caption(ax + small + gap, small, "Use phone"),
                            caption(hx, big, "Hang up")]
        _show(card, False)

    def _pairing(self, on):
        lay = self.lay
        cover = lay.cover[2] > 0
        _show(self.pair, on and cover)
        _show(self.steps, on and lay.steps is not None)
        if not on:
            _show(self.para, False)
        _show(self.cover_box, not on and cover)
        _show(self.edge, not on and cover)

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
        most = self.lay.title_lines * self.title_font.get_line_height()
        if t.get_height() > most + 4:
            t.set_long_mode(lv.label.LONG_MODE.DOTS)
            t.set_height(most)

    def _lines(self, artist, album, meta, hint):
        extras = self.lay.extras
        for lbl, text in ((self.artist, artist), (self.album, album if extras else ""),
                          (self.meta, meta if extras else ""), (self.hint, hint)):
            lbl.set_text(text or "")
            _show(lbl, bool(text))

    def _playback(self, on, transport=None):
        """Show the progress and spectrum while a track is loaded; the
        transport while connected."""
        lay = self.lay
        _show(self.track, on)
        for o in (self.t_pos, self.t_len):
            _show(o, on and lay.times)
        _show(self.codec, on and lay.codec)
        _show(self.bars.obj, on and self.has_bars)
        if not on:
            _show(self.head, False)
            self._pos_text = None
        t = on if transport is None else transport
        for b in (self.prev, self.play, self.next):
            _show(b.obj, t)
        for o in (self.vol, self.vol_mark):
            _show(o, t)
        self._modes_on = t
        self._place_modes()


def switch_header(scope):
    """The shell's header when the calls setting fits in it, else None: a
    short header (a narrow bar) keeps its room for the title."""
    header = getattr(scope, "header", None)
    if header is not None:
        header.update_layout()
        if header.get_width() < HEADER_ROOM:
            return None
    return header


def calls_switch(scope, on, changed, lay=None):
    """The calls setting, a labelled switch at the right of the shell's
    header, or where *lay* (the screen's `Layout`) keeps room for it in the
    app's area, *on* or off. *changed* gets the new setting each time it's
    flipped. The status line moves to its left."""
    header = switch_header(scope)
    parent = header or scope.root
    small = lay is not None and lay.size == "small" and header is None
    sw = lv.switch(parent)
    sw.set_size(40, 22) if small else sw.set_size(48, 26)
    sw.set_style_bg_color(lv.color_hex(LINE), lv.PART.MAIN)
    sw.set_style_bg_color(lv.color_hex(TEAL), lv.PART.INDICATOR | lv.STATE.CHECKED)
    sw.set_style_bg_color(lv.color_hex(TEXT), lv.PART.KNOB)
    sw.set_ext_click_area(12)
    if on:
        sw.add_state(lv.STATE.CHECKED)
    lbl = _label(parent, F_TINY if small else F_SMALL, SUB)
    lbl.set_text(CALLS_LABEL)
    where = lay.switch_at if lay is not None else None
    centred = header is None and where is not None and where[0] == "center"
    if small and not centred:
        # Two short lines beside the switch.
        lbl.set_width(SWITCH_ROOM[1] - 40 - 10 - 16)
    if centred:
        # A row of its own in the band *where* gives, the label on two
        # lines when one is too wide for it, or a handset in its place.
        _, y, bx, bw = where
        if lay.switch_icon:
            lbl.delete()
            lbl = glyphs.tinted(parent, "handset", 20, lv.color_hex(SUB))
        lbl.update_layout()
        room = bw - 10 - sw.get_width()
        if lbl.get_width() > room:
            lbl.set_width(room)
            lbl.update_layout()
        row = lbl.get_width() + 10 + sw.get_width()
        sw.set_pos(bx + (bw - row) // 2 + row - sw.get_width(), y + (lay.switch_h - sw.get_height()) // 2)
    elif header is not None:
        sw.align(lv.ALIGN.RIGHT_MID, -16, 0)
    else:
        sw.align(lv.ALIGN.TOP_RIGHT, -16 if lay is None else -lay.m - 4, 8 if where is None else where[1])
    lbl.align_to(sw, lv.ALIGN.OUT_LEFT_MID, -10, 0)
    status = getattr(scope, "status", None)
    if status is not None and header is not None:
        # Its text changes after this: right-aligned in a fixed width, it
        # stays clear of the label.
        status.set_width(STATUS_W)
        status.set_style_text_align(lv.TEXT_ALIGN.RIGHT, 0)
        status.align_to(lbl, lv.ALIGN.OUT_LEFT_MID, -24, 0)

    def flipped(e):
        changed(sw.has_state(lv.STATE.CHECKED))

    sw.add_event_cb(flipped, lv.EVENT.VALUE_CHANGED, None)
    return sw
