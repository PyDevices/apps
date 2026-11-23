# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The floor view's vector art, drawn once per screen size by svgio.

Each piece is a small SVG document: the panel behind everything, a lit
segment of the beat ring for each beat, seven-segment digits for the beat
and the tempo, and the glow of a pedal's lamp. `Picture` draws one into a
buffer and shows it as an LVGL image, so a beat costs LVGL an image shown
and one hidden, never a redraw of the art. A piece with see-through parts is
RGB565A8, three bytes a pixel; the panel covers the screen, so it is RGB565,
two, and drawn in bands (`bands`) so no one picture needs a big block.

The shapes keep to what every svgio draws the same way: paths, circles,
rectangles, lines, and linear and radial gradients with their stops'
opacity.
"""

import math

import lvgl as lv
import svgio

_HEAD = '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">'

#: The colour each part lights the face in.
ROLE_COLORS = {
    "stopped": 0x7A8698,
    "intro": 0x4CC9F0,
    "main": 0xFFB703,
    "fill": 0xFF6B1A,
    "transition": 0xB28DFF,
    "outro": 0xFF4D6D,
    "end": 0x7A8698,
}
AMBER = 0xFFB703
GLASS = 0x05070B
TEMPO_DIGITS = "0123456789 "    # the tempo's digits: a blank where it has fewer than three

# Which of the seven segments each digit lights: a top, b upper right,
# c lower right, d bottom, e lower left, f upper left, g middle.
SEGMENTS = {
    "0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc", "5": "afgcd",
    "6": "afgedc", "7": "abc", "8": "abcdefg", "9": "abcdfg", "-": "g", " ": "",
}


def hexcolor(rgb):
    return "#%06x" % rgb


def mix(a, b, t):
    """The colour ``t`` of the way from ``a`` to ``b``, each 0xRRGGBB."""
    out = 0
    for shift in (16, 8, 0):
        ca = (a >> shift) & 255
        cb = (b >> shift) & 255
        out |= int(ca + (cb - ca) * t + 0.5) << shift
    return out


def image(parent, x, y, w, h):
    """An LVGL image ``w`` by ``h`` at ``(x, y)`` in ``parent``, showing
    nothing until it is given a `Picture`'s ``dsc``."""
    img = lv.image(parent)
    img.set_size(w, h)
    img.set_pos(x, y)
    img.remove_flag(lv.obj.FLAG.CLICKABLE)
    img.remove_flag(lv.obj.FLAG.SCROLLABLE)
    return img


class Picture:
    """An SVG drawn into a buffer, and the LVGL image that shows it.

    ``svg`` is its text, as a str or bytes-like. With ``alpha`` (the default)
    the buffer is RGB565A8, so what's behind shows through; without, it is
    RGB565, a third smaller, for art that covers its whole box. Pictures
    drawn together can share a ``decoder`` (`decoder`), which saves the heap
    a parse's worth of small blocks each.
    """

    def __init__(self, parent, svg, width, height, x=0, y=0, alpha=True, decoder=None):
        own = decoder is None
        if own:
            decoder = svgio.SvgDecoder()
        if isinstance(svg, str):
            svg = svg.encode()
        w, h = decoder.open(svg, width=width)
        if (w, h) != (width, height):
            raise ValueError("art drew at %dx%d, not %dx%d" % (w, h, width, height))
        size = w * h * (3 if alpha else 2)
        self.data = bytearray(size)
        if alpha:
            planes = memoryview(self.data)
            decoder.decode(planes[: w * h * 2], planes[w * h * 2:])
        else:
            decoder.decode(self.data)
        if own and hasattr(decoder, "close"):
            decoder.close()
        dsc = lv.image_dsc_t()
        dsc.header.magic = lv.IMAGE_HEADER_MAGIC
        dsc.header.cf = lv.COLOR_FORMAT.RGB565A8 if alpha else lv.COLOR_FORMAT.RGB565
        dsc.header.w = w
        dsc.header.h = h
        dsc.header.stride = w * 2
        dsc.data_size = size
        dsc.data = self.data
        self.dsc = dsc
        self.image = None
        if parent is not None:
            self.image = self.show(parent, x, y)

    def show(self, parent, x=0, y=0):
        """Another LVGL image of the same pixels, at ``(x, y)`` in ``parent``."""
        header = self.dsc.header
        img = image(parent, x, y, header.w, header.h)
        img.set_src(self.dsc)
        return img

    @property
    def bytes(self):
        return len(self.data)


#: The working memory a shared decoder (`decoder`) is made with: room for
#: the panel's parse, its thousands of small blocks. The few large ones a
#: draw takes spill over. On an ESP32 with PSRAM, and on a desktop, the
#: memory and what spills come from outside the heap.
DECODER_MEMORY = 96 * 1024


def decoder():
    """An svgio decoder for many pictures in a row, one at a time.

    A parse makes thousands of small blocks. On a board whose heap holds a
    view's pictures, finding room for each one took longer than the drawing;
    this decoder makes them in its own memory instead. `close` it when the
    pictures are drawn.
    """
    return svgio.SvgDecoder(memory=DECODER_MEMORY)


BAND = 65536  # the most bytes a band of a screen-sized picture holds (`bands`)

_BAND_HEAD = '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 %d %d %d"'
#: The bytes a head gets in a `panel_text`: room for any band's, so a band
#: is drawn by writing its head over the whole picture's, in place.
HEAD_ROOM = len(_BAND_HEAD % (99999, 99999, 99999, 99999, 99999)) + 1


def _room_head(width, rows, y):
    """The head of band ``rows`` high at ``y``, padded to `HEAD_ROOM` bytes."""
    head = _BAND_HEAD % (width, rows, y, width, rows)
    return (head + " " * (HEAD_ROOM - 1 - len(head)) + ">").encode()


def panel_text(svg, width, height):
    """``svg``, which starts with its own size (`_HEAD`), as a bytearray
    whose head has room for a band's (`HEAD_ROOM`), for `bands`."""
    head = _HEAD % (width, height, width, height)
    svg = svg.encode() if isinstance(svg, str) else bytes(svg)
    if not svg.startswith(head.encode()):
        raise ValueError("bands() takes an SVG that starts with its own size")
    out = bytearray(HEAD_ROOM + len(svg) - len(head))
    out[:HEAD_ROOM] = _room_head(width, height, 0)
    out[HEAD_ROOM:] = memoryview(svg)[len(head):]
    return out


def bands(parent, svg, width, height, decoder=None):
    """``svg``, which covers its whole box, drawn as RGB565 pictures of a
    band of rows each, top to bottom in ``parent``, none over `BAND` bytes.

    A picture the size of the screen would need one free block that big,
    and a heap a running app has left in pieces may have the bytes but no
    such block. Each band is the same SVG with its view moved down, so the
    bands are the picture drawn whole, a few pixels a step of rounding
    apart.

    ``svg`` is best a `panel_text`, or a writable view of one: each band's
    head is then written over its head in place, and put back after, so the
    bands copy no text.
    """
    if not (isinstance(svg, (bytearray, memoryview)) and bytes(svg[:HEAD_ROOM]) == _room_head(width, height, 0)):
        svg = panel_text(svg, width, height)
    step = max(1, BAND // (2 * width))
    out = []
    try:
        for y in range(0, height, step):
            rows = min(step, height - y)
            svg[:HEAD_ROOM] = _room_head(width, rows, y)
            out.append(Picture(parent, svg, width, rows, 0, y, alpha=False, decoder=decoder))
    finally:
        svg[:HEAD_ROOM] = _room_head(width, height, 0)
    return out


def _arc(cx, cy, r, a0, a1):
    """The points of an arc from angle ``a0`` to ``a1`` (degrees, clockwise from 3 o'clock)."""
    p0 = (cx + r * math.cos(math.radians(a0)), cy + r * math.sin(math.radians(a0)))
    p1 = (cx + r * math.cos(math.radians(a1)), cy + r * math.sin(math.radians(a1)))
    return p0, p1


def _band(cx, cy, r_in, r_out, a0, a1):
    """A closed path: the ring between two radii, from angle a0 to a1."""
    (x0, y0), (x1, y1) = _arc(cx, cy, r_out, a0, a1)
    (x2, y2), (x3, y3) = _arc(cx, cy, r_in, a1, a0)
    big = 1 if a1 - a0 > 180 else 0
    return ("M%.2f %.2fA%.2f %.2f 0 %d 1 %.2f %.2fL%.2f %.2fA%.2f %.2f 0 %d 0 %.2f %.2fZ"
            % (x0, y0, r_out, r_out, big, x1, y1, x2, y2, r_in, r_in, big, x3, y3))


class Layout:
    """Where everything goes at one screen size: computed, never measured."""

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.landscape = w >= h
        m = max(6, int(min(w, h) * 0.045))
        self.m = m
        if self.landscape:
            d = min(h - 2 * m, int(w * 0.48))
            self.ring = (m, (h - d) // 2, d)
            x0 = m + d + 2 * m
            self.col = (x0, m, w - x0 - m, h - 2 * m)
        else:
            d = min(w - 2 * m, int(h * 0.5))
            self.ring = ((w - d) // 2, m, d)
            y0 = m + d + m
            self.col = (m, y0, w - 2 * m, h - y0 - m)
        x, y, d = self.ring
        self.cx = x + d / 2.0
        self.cy = y + d / 2.0
        self.r = d / 2.0
        cx, cy, cw, ch = self.col
        # The column beside the ring, top to bottom: the song, the part's
        # window, the next-up chip, the tempo, the kit, the pedals.
        unit = ch / 100.0
        self.song_y = cy
        self.window = (cx, int(cy + 10 * unit), cw, int(23 * unit))
        self.chip_y = int(cy + 37 * unit)
        self.chip_h = max(18, int(10 * unit))
        self.tempo = (cx, int(cy + 52 * unit), int(cw * 0.6), int(18 * unit))
        self.kit_y = int(cy + 73 * unit)
        self.pedal_r = max(10, int(min(9 * unit, cw / 6.0)))
        self.pedal_y = int(cy + ch - self.pedal_r - max(2, self.pedal_r // 5))
        self.pedal_x = (int(cx + self.pedal_r * 1.3), int(cx + cw - self.pedal_r * 1.3))
        # The ring's bands, as fractions of its radius.
        self.beat_in = 0.66 * self.r
        self.beat_out = 0.84 * self.r
        # Digits: the beat inside the ring, the tempo in its window.
        self.big_h = int(self.r * 0.62)
        self.big_w = int(self.big_h * 0.58)
        tw = self.tempo[3] - 8
        self.small_h = max(14, tw)
        self.small_w = int(self.small_h * 0.58)
        # Three digits and their gaps (`tempo_slots`) fit the window's width
        # too, which on a square screen is the narrower side.
        most = int((self.tempo[2] - 8) / 3.34)
        if self.small_w > most:
            self.small_w = most
            self.small_h = int(most / 0.58)

    def font(self, share):
        """The largest built-in font no taller than ``share`` of the screen's height."""
        return self.font_px(self.h * share)

    def font_px(self, want):
        """The largest built-in font no taller than ``want`` pixels (the smallest when none is)."""
        best = None
        for size in (14, 16, 24, 32, 40):
            f = getattr(lv, "font_montserrat_%d" % size, None)
            if f is not None and (best is None or size <= want):
                best = f
        return best or lv.font_default()


def panel_svg(lay, steps=4, group=1):
    """Everything that never moves: the panel, the ring's housing and its dim
    track of ``steps`` segments, the part window's glass, the tempo window
    with its ghost digits, and the pedal lamps unlit.

    It is three parts after the head: `panel_top` and `panel_bottom`, the
    same for every meter, round `panel_ring`, the ticks and the track."""
    return "".join((_HEAD % (lay.w, lay.h, lay.w, lay.h), panel_top(lay), panel_ring(lay, steps, group),
                    panel_bottom(lay)))


def panel_top(lay):
    """The panel's gradients, its brushed face and the ring's housing."""
    w, h = lay.w, lay.h
    cx, cy, r = lay.cx, lay.cy, lay.r
    out = ["<defs>"]
    out.append('<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">'
               '<stop offset="0" stop-color="#1a212d"/><stop offset="0.55" stop-color="#0d1118"/>'
               '<stop offset="1" stop-color="#06080c"/></linearGradient>')
    out.append('<radialGradient id="sheen" gradientUnits="userSpaceOnUse" cx="%.1f" cy="%.1f" r="%.1f">'
               '<stop offset="0" stop-color="#3b4a63" stop-opacity="0.35"/>'
               '<stop offset="1" stop-color="#3b4a63" stop-opacity="0"/></radialGradient>' % (w * 0.7, -h * 0.1, w * 0.7))
    out.append('<linearGradient id="bezel" x1="0" y1="0" x2="0.3" y2="1">'
               '<stop offset="0" stop-color="#5d6878"/><stop offset="0.45" stop-color="#252c37"/>'
               '<stop offset="1" stop-color="#0b0e13"/></linearGradient>')
    out.append('<linearGradient id="bezel2" x1="0" y1="1" x2="0.2" y2="0">'
               '<stop offset="0" stop-color="#4a5466"/><stop offset="1" stop-color="#0c0f14"/></linearGradient>')
    out.append('<radialGradient id="face" cx="0.4" cy="0.3" r="0.8">'
               '<stop offset="0" stop-color="#1c2533"/><stop offset="1" stop-color="#05070a"/></radialGradient>')
    out.append('<radialGradient id="hub" cx="0.5" cy="0.5" r="0.5">'
               '<stop offset="0" stop-color="#ffb703" stop-opacity="0.10"/>'
               '<stop offset="1" stop-color="#ffb703" stop-opacity="0"/></radialGradient>')
    out.append('<linearGradient id="glass" x1="0" y1="0" x2="0" y2="1">'
               '<stop offset="0" stop-color="#0d131c"/><stop offset="1" stop-color="#030406"/></linearGradient>')
    out.append('<linearGradient id="gloss" x1="0" y1="0" x2="0" y2="1">'
               '<stop offset="0" stop-color="#ffffff" stop-opacity="0.10"/>'
               '<stop offset="1" stop-color="#ffffff" stop-opacity="0"/></linearGradient>')
    out.append('<radialGradient id="lens" cx="0.4" cy="0.35" r="0.7">'
               '<stop offset="0" stop-color="#2b3443"/><stop offset="1" stop-color="#07090d"/></radialGradient>')
    out.append('<linearGradient id="chrome" x1="0" y1="0" x2="0" y2="1">'
               '<stop offset="0" stop-color="#c9d2de"/><stop offset="0.5" stop-color="#4b5565"/>'
               '<stop offset="1" stop-color="#1b2029"/></linearGradient>')
    out.append("</defs>")
    out.append('<rect width="%d" height="%d" fill="url(#bg)"/>' % (w, h))
    out.append('<rect width="%d" height="%d" fill="url(#sheen)"/>' % (w, h))
    # Fine horizontal lines across the panel, like brushed metal.
    step = max(3, h // 80)
    for y in range(0, h, step):
        out.append('<line x1="0" y1="%d" x2="%d" y2="%d" stroke="#ffffff" stroke-opacity="0.018"/>' % (y, w, y))

    # The ring's housing: a bezel, a groove, the face.
    out.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="#000000" fill-opacity="0.45"/>' % (cx + 2, cy + 4, r))
    out.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="url(#bezel)"/>' % (cx, cy, r))
    out.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="url(#bezel2)"/>' % (cx, cy, r * 0.955))
    out.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="url(#face)"/>' % (cx, cy, r * 0.93))
    out.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="url(#hub)"/>' % (cx, cy, r * 0.62))
    return "".join(out)


def panel_ring(lay, steps=4, group=1):
    """The ring's ticks and its dim track for a bar of ``steps``, ``group`` to a beat."""
    cx, cy, r = lay.cx, lay.cy, lay.r
    out = []
    # Ticks outside the track, a beat's longer: sixteenths where a beat is
    # one segment, else one tick a segment.
    per = 4 if group == 1 else 1
    ticks = steps * per
    for i in range(ticks):
        a = math.radians(-90 + i * 360.0 / ticks)
        major = i % (per * group) == 0
        r0 = r * 0.865
        r1 = r * (0.915 if major else 0.893)
        out.append('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="#c8d0dc" stroke-opacity="%.2f" '
                   'stroke-width="%.1f" stroke-linecap="round"/>'
                   % (cx + r0 * math.cos(a), cy + r0 * math.sin(a), cx + r1 * math.cos(a), cy + r1 * math.sin(a),
                      0.75 if major else 0.3, max(1.0, r / 60.0) * (1.6 if major else 1.0)))
    # The dim track, a segment a step.
    for b in range(steps):
        a0, a1 = beat_span(b, steps, group)
        out.append('<path d="%s" fill="#1d2430" stroke="#3a4555" stroke-opacity="0.8" stroke-width="1"/>'
                   % _band(cx, cy, lay.beat_in, lay.beat_out, a0, a1))
    return "".join(out)


def panel_bottom(lay):
    """The digit's hairline, the part and tempo windows and the pedal lamps unlit, and the end."""
    cx, cy, r = lay.cx, lay.cy, lay.r
    out = []
    # An inner hairline round the digit.
    out.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="none" stroke="#ffffff" stroke-opacity="0.08" '
               'stroke-width="1"/>' % (cx, cy, r * 0.60))

    # The part window: glass in a chrome rim.
    x, y, ww, wh = lay.window
    rad = max(4, wh // 6)
    out.append('<rect x="%d" y="%d" width="%d" height="%d" rx="%d" fill="url(#chrome)"/>' % (x - 2, y - 2, ww + 4, wh + 4, rad + 2))
    out.append('<rect x="%d" y="%d" width="%d" height="%d" rx="%d" fill="url(#glass)"/>' % (x, y, ww, wh, rad))
    out.append('<rect x="%d" y="%d" width="%d" height="%d" rx="%d" fill="url(#gloss)"/>' % (x + 2, y + 2, ww - 4, wh // 2, rad))

    # The tempo window, with dim eights behind the lit digits.
    x, y, tw, th = lay.tempo
    out.append('<rect x="%d" y="%d" width="%d" height="%d" rx="%d" fill="url(#chrome)"/>' % (x - 2, y - 2, tw + 4, th + 4, rad + 2))
    out.append('<rect x="%d" y="%d" width="%d" height="%d" rx="%d" fill="url(#glass)"/>' % (x, y, tw, th, rad))
    for i, dx in enumerate(tempo_slots(lay)):
        out.append(_digit_paths("8", dx, y + (th - lay.small_h) // 2, lay.small_w, lay.small_h, 0x2A1E05, None))

    # The pedal lamps, unlit.
    for px in lay.pedal_x:
        pr = lay.pedal_r
        out.append('<circle cx="%d" cy="%d" r="%.1f" fill="url(#chrome)"/>' % (px, lay.pedal_y, pr + max(2, pr * 0.18)))
        out.append('<circle cx="%d" cy="%d" r="%.1f" fill="url(#lens)"/>' % (px, lay.pedal_y, pr))
    out.append("</svg>")
    return "".join(out)


def beat_span(step, steps=4, group=1):
    """The angles of ring segment ``step`` (from 0 at the top, clockwise) of
    ``steps``, with a gap each side: a wide one where a beat starts or ends,
    a narrow one between the steps of one beat (12/8's eighths, in threes)."""
    size = 360.0 / steps
    wide = min(5.0, size * 0.2)
    narrow = min(2.0, size * 0.1)
    a0 = -90 + step * size + (wide if step % group == 0 else narrow)
    a1 = -90 + (step + 1) * size - (wide if (step + 1) % group == 0 else narrow)
    return a0, a1


def segment_box(lay, step, steps=4, group=1):
    """The box, in screen pixels, that holds a lit segment and its glow."""
    pad = lay.r * 0.06
    a0, a1 = beat_span(step, steps, group)
    xs = []
    ys = []
    for k in range(9):
        a = math.radians(a0 - 2 + (a1 - a0 + 4) * k / 8.0)
        for rr in (lay.beat_in - pad, lay.beat_out + pad):
            xs.append(lay.cx + rr * math.cos(a))
            ys.append(lay.cy + rr * math.sin(a))
    x0, y0 = int(min(xs)) - 1, int(min(ys)) - 1
    x1, y1 = int(max(xs)) + 2, int(max(ys)) + 2
    return x0, y0, x1 - x0, y1 - y0


def segment_svg(lay, step, steps=4, group=1, color=0xFFF4E0):
    """Segment ``step``'s light: a bright band with a glow round it, in its
    own box (`segment_box`), so it moves nothing else when shown."""
    x0, y0, bw, bh = segment_box(lay, step, steps, group)
    cx, cy = lay.cx - x0, lay.cy - y0
    a0, a1 = beat_span(step, steps, group)
    hot = hexcolor(color)
    out = [_HEAD % (bw, bh, bw, bh), "<defs>"]
    mid = (lay.beat_in + lay.beat_out) / 2
    am = math.radians((a0 + a1) / 2)
    out.append('<radialGradient id="lit" gradientUnits="userSpaceOnUse" cx="%.1f" cy="%.1f" r="%.1f">'
               '<stop offset="0" stop-color="#ffffff"/><stop offset="0.6" stop-color="%s"/>'
               '<stop offset="1" stop-color="%s"/></radialGradient>'
               % (cx + mid * math.cos(am), cy + mid * math.sin(am), lay.r * 0.75, hot, hexcolor(mix(color, 0x000000, 0.35))))
    out.append("</defs>")
    pad = lay.r * 0.055
    for k, opa in ((1.0, 0.10), (0.6, 0.16), (0.3, 0.24)):
        out.append('<path d="%s" fill="%s" fill-opacity="%.2f"/>'
                   % (_band(cx, cy, lay.beat_in - pad * k, lay.beat_out + pad * k, a0 - 2 * k, a1 + 2 * k), hot, opa))
    out.append('<path d="%s" fill="url(#lit)"/>' % _band(cx, cy, lay.beat_in, lay.beat_out, a0, a1))
    # A bright line along the outer edge.
    edge = lay.beat_out - max(1.0, lay.r * 0.012)
    (ex0, ey0), (ex1, ey1) = _arc(cx, cy, edge, a0 + 1, a1 - 1)
    out.append('<path d="M%.2f %.2fA%.2f %.2f 0 0 1 %.2f %.2f" fill="none" stroke="#ffffff" stroke-opacity="0.7" '
               'stroke-width="%.1f"/>' % (ex0, ey0, edge, edge, ex1, ey1, max(1.0, lay.r * 0.012)))
    out.append("</svg>")
    return "".join(out)


def _digit_paths(ch, x, y, w, h, color, glow):
    """The lit segments of ``ch`` as SVG, its box at ``(x, y)``, ``w`` by ``h``."""
    t = max(2.0, w * 0.17)              # a segment's thickness
    sl = w * 0.08                       # the slant of an italic digit
    g = t * 0.12                        # the gap between segments
    half = h / 2.0

    def pt(px, py):
        # Slant the digit: the top leans right.
        return (x + px + sl * (1 - py / h), y + py)

    def seg(horizontal, px, py, length):
        if horizontal:
            pts = [(px + g, py), (px + t / 2 + g, py - t / 2), (px + length - t / 2 - g, py - t / 2),
                   (px + length - g, py), (px + length - t / 2 - g, py + t / 2), (px + t / 2 + g, py + t / 2)]
        else:
            pts = [(px, py + g), (px + t / 2, py + t / 2 + g), (px + t / 2, py + length - t / 2 - g),
                   (px, py + length - g), (px - t / 2, py + length - t / 2 - g), (px - t / 2, py + t / 2 + g)]
        pts = [pt(a, b) for a, b in pts]
        return "M" + "L".join("%.2f %.2f" % p for p in pts) + "Z"

    lit = SEGMENTS.get(ch, "")
    if not lit:
        return ""
    inner = w - t
    l, rr = t / 2, w - t / 2
    top, bot = t / 2, h - t / 2
    shapes = {
        "a": (True, l, top, inner), "g": (True, l, half, inner), "d": (True, l, bot, inner),
        "f": (False, l, top, half - top), "b": (False, rr, top, half - top),
        "e": (False, l, half, bot - half), "c": (False, rr, half, bot - half),
    }
    d = "".join(seg(*shapes[s]) for s in lit)    # only the lit ones are written
    out = []
    if glow is not None:
        out.append('<path d="%s" fill="none" stroke="%s" stroke-opacity="0.22" stroke-width="%.1f" '
                   'stroke-linejoin="round"/>' % (d, hexcolor(glow), t * 0.9))
    out.append('<path d="%s" fill="%s"/>' % (d, hexcolor(color)))
    return "".join(out)


def digit_svg(ch, w, h, color=AMBER):
    """One seven-segment digit, lit, on nothing, with a soft glow: ``w`` by ``h``."""
    pad = max(2, int(w * 0.12))
    body = _digit_paths(ch, pad, pad, w - 2 * pad, h - 2 * pad, mix(color, 0xFFFFFF, 0.25), color)
    return _HEAD % (w, h, w, h) + body + "</svg>"


def tempo_slots(lay):
    """The x of each of the tempo window's three digits."""
    x, _y, tw, _th = lay.tempo
    span = 3 * lay.small_w + 2 * max(2, lay.small_w // 6)
    x0 = x + (tw - span) // 2
    return [x0 + i * (lay.small_w + max(2, lay.small_w // 6)) for i in range(3)]


def glow_svg(r, color):
    """A pedal lamp lit: a hot centre fading to nothing at ``r``."""
    s = int(2 * r)
    c = s / 2.0
    hot = hexcolor(color)
    return (_HEAD % (s, s, s, s)
            + '<defs><radialGradient id="g" cx="0.5" cy="0.5" r="0.5">'
            '<stop offset="0" stop-color="#ffffff"/><stop offset="0.25" stop-color="%s"/>'
            '<stop offset="0.6" stop-color="%s" stop-opacity="0.35"/>'
            '<stop offset="1" stop-color="%s" stop-opacity="0"/></radialGradient></defs>'
            '<circle cx="%.1f" cy="%.1f" r="%.1f" fill="url(#g)"/></svg>' % (hot, hot, hot, c, c, c))


def beat_digits(steps, group):
    """The beat's digits a bar of ``steps``, ``group`` to a beat, shows: a
    dash, and one to each of its beats."""
    return "-123456789"[: 1 + min(9, steps // max(1, group))]


class Texts:
    """The SVG text of one screen size's art (a `Layout`), written the first
    time it is wanted and kept until the view goes.

    A view that hides lets go of its pictures, and draws them again when it
    shows. On a board, writing the text took longer than drawing it, so the
    text is kept instead: under 50 KB a view, where its pixels are a
    megabyte or more. It is kept end to end in one `svgio.Buffer`, which on
    an ESP32 with PSRAM, and on a desktop, is outside the heap, so the heap
    holds next to nothing more than before and the collector doesn't read
    it. First what every meter shows (`face`), then the ring for one meter
    (`ring`); another meter writes only the parts of it that change. A view
    of the text it gives is good until the next call that writes some.
    """

    def __init__(self, lay):
        self.lay = lay
        self.meter = None
        self._buf = None        # the texts, end to end
        self._ends = []         # where each ends: `face`'s, then `ring`'s
        self._face = 0          # how many of them are `face`'s
        self._ring_at = (0, 0)  # where `panel_ring`'s part of the panel is

    def _text(self, i):
        """A writable view of text ``i``."""
        ends = self._ends
        return memoryview(self._buf)[ends[i - 1] if i else 0:ends[i]]

    def _keep(self, face, ring):
        """Keep ``face``'s texts and then ``ring``'s: one buffer for them all
        in place of the one there was. A text is bytes-like, or a list of
        pieces written end to end; a piece may be a view of the buffer there
        was, which is read before it goes, so no text is copied on the heap."""
        texts = face + ring
        sizes = [sum(len(p) for p in t) if isinstance(t, list) else len(t) for t in texts]
        buf = svgio.Buffer(sum(sizes))
        view = memoryview(buf)
        ends = [0] * len(texts)
        at = 0
        for i, t in enumerate(texts):
            for p in t if isinstance(t, list) else (t,):
                view[at:at + len(p)] = p
                at += len(p)
            ends[i] = at
        view = None
        old = self._buf
        self._buf, self._ends, self._face = buf, ends, len(face)
        if old is not None:
            old.close()

    def _texts(self, first, end):
        return [self._text(i) for i in range(first, end)]

    def face(self, glows):
        """The tempo's digits, ``{ch: text}`` for each of `TEMPO_DIGITS`,
        and a lit lamp's glow for each ``(radius, colour)`` of ``glows``
        (`glow_svg`), in a list. They are written once: a view's lamps
        don't change."""
        glows = list(glows)
        if not self._face:
            lay = self.lay
            face = [digit_svg(ch, lay.small_w, lay.small_h).encode() for ch in TEMPO_DIGITS]
            face += [glow_svg(r, color).encode() for r, color in glows]
            self._keep(face, self._texts(self._face, len(self._ends)))
        n = len(TEMPO_DIGITS)
        return {ch: self._text(i) for i, ch in enumerate(TEMPO_DIGITS)}, [self._text(n + i) for i in range(len(glows))]

    def ring(self, steps, group):
        """The panel, as a view of a `panel_text`, and each lit segment's
        text, in a list, for a bar of ``steps``, ``group`` to a beat.
        Another meter lets go of the last one's, and keeps the panel's
        parts that don't change with it, and the beat's digits both show."""
        first = self._face
        if self.meter != (steps, group):
            lay = self.lay
            a, b = self._ring_at
            digits = {}
            if self.meter is None:
                top = _room_head(lay.w, lay.h, 0) + panel_top(lay).encode()
                bottom = panel_bottom(lay).encode()
            else:
                panel = self._text(first)
                top, bottom = panel[:a], panel[b:]
                panel = None
                old_steps = self.meter[0]
                for i, ch in enumerate(beat_digits(*self.meter)):
                    digits[ch] = self._text(first + 1 + old_steps + i)
            self.meter = None
            mid = panel_ring(lay, steps, group).encode()
            self._ring_at = (len(top), len(top) + len(mid))
            ring = [[top, mid, bottom]]
            top = mid = bottom = None
            ring += [segment_svg(lay, i, steps, group).encode() for i in range(steps)]
            ring += [digits[ch] if ch in digits else digit_svg(ch, lay.big_w, lay.big_h).encode()
                     for ch in beat_digits(steps, group)]
            digits = None
            self._keep(self._texts(0, first), ring)
            self.meter = (steps, group)
        return self._text(first), [self._text(first + 1 + i) for i in range(steps)]

    def big(self, ch):
        """The beat's digit ``ch``, lit (`digit_svg`): kept with the ring
        where its meter shows it, else written now."""
        at = beat_digits(*self.meter).find(ch) if self.meter is not None else -1
        if at < 0:
            lay = self.lay
            return digit_svg(ch, lay.big_w, lay.big_h).encode()
        return self._text(self._face + 1 + self.meter[0] + at)

    def bytes(self):
        """The bytes of text kept."""
        return len(self._buf) if self._buf is not None else 0
