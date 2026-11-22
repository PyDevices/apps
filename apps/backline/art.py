# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""The floor view's vector art, drawn once per screen size by svgio.

Each piece is a small SVG document: the panel behind everything, a lit
segment of the beat ring for each beat, seven-segment digits for the beat
and the tempo, and the glow of a pedal's lamp. `Picture` draws one into an
RGB565A8 buffer and shows it as an LVGL image, so a beat costs LVGL an image
shown and one hidden, never a redraw of the art.

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


class Picture:
    """An SVG drawn into an RGB565A8 buffer, and the LVGL image that shows it."""

    def __init__(self, parent, svg, width, height, x=0, y=0):
        decoder = svgio.SvgDecoder()
        w, h = decoder.open(svg.encode(), width=width)
        if (w, h) != (width, height):
            raise ValueError("art drew at %dx%d, not %dx%d" % (w, h, width, height))
        self.data = bytearray(w * h * 3)
        planes = memoryview(self.data)
        decoder.decode(planes[: w * h * 2], planes[w * h * 2:])
        if hasattr(decoder, "close"):
            decoder.close()
        dsc = lv.image_dsc_t()
        dsc.header.magic = lv.IMAGE_HEADER_MAGIC
        dsc.header.cf = lv.COLOR_FORMAT.RGB565A8
        dsc.header.w = w
        dsc.header.h = h
        dsc.header.stride = w * 2
        dsc.data_size = w * h * 3
        dsc.data = self.data
        self.dsc = dsc
        self.w = w
        self.h = h
        self.image = None
        if parent is not None:
            self.image = self.show(parent, x, y)

    def show(self, parent, x=0, y=0):
        """Another LVGL image of the same pixels, at ``(x, y)`` in ``parent``."""
        image = lv.image(parent)
        image.set_src(self.dsc)
        image.set_size(self.w, self.h)
        image.set_pos(x, y)
        image.remove_flag(lv.obj.FLAG.CLICKABLE)
        image.remove_flag(lv.obj.FLAG.SCROLLABLE)
        return image

    @property
    def bytes(self):
        return len(self.data)


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

    def font(self, share):
        """The largest built-in font no taller than ``share`` of the screen's height."""
        want = self.h * share
        best = None
        for size in (14, 16, 24, 32, 40):
            f = getattr(lv, "font_montserrat_%d" % size, None)
            if f is not None and (best is None or size <= want):
                best = f
        return best or lv.font_default()


def panel_svg(lay):
    """Everything that never moves: the panel, the ring's housing and dim
    track, the part window's glass, the tempo window with its ghost digits,
    and the pedal lamps unlit."""
    w, h = lay.w, lay.h
    cx, cy, r = lay.cx, lay.cy, lay.r
    out = [_HEAD % (w, h, w, h), "<defs>"]
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
    # Sixteenth ticks outside the beat track, the beats longer.
    for i in range(16):
        a = math.radians(-90 + i * 22.5)
        major = i % 4 == 0
        r0 = r * 0.865
        r1 = r * (0.915 if major else 0.893)
        out.append('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="#c8d0dc" stroke-opacity="%.2f" '
                   'stroke-width="%.1f" stroke-linecap="round"/>'
                   % (cx + r0 * math.cos(a), cy + r0 * math.sin(a), cx + r1 * math.cos(a), cy + r1 * math.sin(a),
                      0.75 if major else 0.3, max(1.0, r / 60.0) * (1.6 if major else 1.0)))
    # The dim beat track: four segments.
    for b in range(4):
        a0, a1 = beat_span(b)
        out.append('<path d="%s" fill="#1d2430" stroke="#3a4555" stroke-opacity="0.8" stroke-width="1"/>'
                   % _band(cx, cy, lay.beat_in, lay.beat_out, a0, a1))
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


def beat_span(beat):
    """The angles of beat ``beat``'s segment (0 at the top, clockwise), with a gap each side."""
    gap = 5.0
    a0 = -90 + beat * 90 + gap
    return a0, a0 + 90 - 2 * gap


def segment_box(lay, beat):
    """The square, in screen pixels, that holds beat ``beat``'s lit segment and its glow."""
    pad = lay.r * 0.06
    r = lay.beat_out + pad
    a0, a1 = beat_span(beat)
    xs = [lay.cx, ]
    ys = [lay.cy, ]
    for a in (a0, a1, (a0 + a1) / 2):
        for rr in (lay.beat_in - pad, r):
            xs.append(lay.cx + rr * math.cos(math.radians(a)))
            ys.append(lay.cy + rr * math.sin(math.radians(a)))
    # Each quadrant's outer corner reaches the full radius.
    qx = 1 if beat in (0, 1) else -1
    qy = -1 if beat in (0, 3) else 1
    xs.append(lay.cx + qx * r)
    ys.append(lay.cy + qy * r)
    x0, y0 = int(min(xs)) - 1, int(min(ys)) - 1
    x1, y1 = int(max(xs)) + 2, int(max(ys)) + 2
    return x0, y0, x1 - x0, y1 - y0


def segment_svg(lay, beat, color=0xFFF4E0):
    """Beat ``beat``'s lit segment: a bright band with a glow round it, in
    its own box (`segment_box`), so it moves nothing else when shown."""
    x0, y0, bw, bh = segment_box(lay, beat)
    cx, cy = lay.cx - x0, lay.cy - y0
    a0, a1 = beat_span(beat)
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

    inner = w - t
    l, rr = t / 2, w - t / 2
    top, bot = t / 2, h - t / 2
    shapes = {
        "a": seg(True, l, top, inner), "g": seg(True, l, half, inner), "d": seg(True, l, bot, inner),
        "f": seg(False, l, top, half - top), "b": seg(False, rr, top, half - top),
        "e": seg(False, l, half, bot - half), "c": seg(False, rr, half, bot - half),
    }
    lit = SEGMENTS.get(ch, "")
    if not lit:
        return ""
    d = "".join(shapes[s] for s in lit)
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
