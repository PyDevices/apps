# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Build a vector drawing in Python and draw it at any size with svgio.

A `Doc` collects shapes and gradients, keeping to what svgio reads: paths,
strokes, transforms, opacity and gradients. The view is a rectangle of the
drawing, so a close-up is the same drawing with a smaller view.

Shapes are kept as numbers, in svgio's compact form, not as text: writing
every coordinate out in Python, for svgio to read back, is most of the time a
drawing takes on a board. `Doc.source` gives what `SvgDecoder.open` takes:
the compact form where svgio reads it, and SVG text where it doesn't.
`Doc.svg` gives the SVG text anywhere.

Example::

    doc = Doc()
    glow = doc.radial([(0, 0xFFF3B0, 1), (1, 0xFFF3B0, 0)])
    doc.add(circle(50, 50, 40, glow))
    pixels, alpha, w, h = render(doc.source((0, 0, 100, 100)), 200)
"""

import math
import struct

import svgio


def mix(a, b, t):
    """The colour *t* of the way from *a* to *b*, each 0xRRGGBB."""
    if t <= 0:
        return a
    if t >= 1:
        return b
    r = (a >> 16) + ((b >> 16) - (a >> 16)) * t
    g = ((a >> 8) & 255) + (((b >> 8) & 255) - ((a >> 8) & 255)) * t
    bl = (a & 255) + ((b & 255) - (a & 255)) * t
    return (int(r + 0.5) << 16) | (int(g + 0.5) << 8) | int(bl + 0.5)


def lerp(a, b, t):
    return a + (b - a) * t


_wash = None


def wash(color=None, amount=0.0):
    """Mix every colour drawn from now on toward *color*: moonlight, dusk, fog.

    Call it with no arguments to draw in true colours again.
    """
    global _wash
    _wash = (color, amount) if color is not None and amount > 0 else None


# -- the compact form ---------------------------------------------------
#
# What the helpers below return is bytes: records of svgio's compact form,
# which is SVG with its numbers left as numbers. svgio's README describes it.
# A record is an opcode byte and its fields; a number is this runtime's own
# float, so it prints as "%.5g" would print it here.

_F = "d" if 1.0 + 1e-10 != 1.0 else "f"
_MAGIC = b"\x01SVG" + (b"\x08" if _F == "d" else b"\x04")
_NO_PAINT = 0xFFFFFFFF  # fill="none"
_NO_STROKE = 0xFFFFFFFE  # no stroke attributes at all
_GRADIENT = 0x1000000  # a paint at or above this is a gradient, by its number

_pack = struct.pack
_STYLE = "II2" + _F + "H"  # fill, stroke, stroke width, opacity, bytes of extra attributes
_CIRCLE = "<B3" + _F + _STYLE
_ELLIPSE = "<B5" + _F + _STYLE
_RECT = "<B5" + _F + _STYLE
_PATH = "<BI"
_STYLED = "<" + _STYLE
_SEG2 = "<B2" + _F
_SEG6 = "<B6" + _F
_TEXT = "<BH"
_LIMB = "<BIB2" + _F + "B4" + _F + "B2" + _F + "B4" + _F + "B" + _STYLE + "B3" + _F + _STYLE + "B3" + _F + _STYLE
_LIMB_D = 5 + 12 * struct.calcsize(_F)
_GROUP = "<B" + _F + "H"
_AT = "<B4" + _F + "B"
_VIEW = "<B4" + _F
_LINEAR = "<B4" + _F + "BB"
_RADIAL = "<B3" + _F + "B2" + _F + "BB"
_STOP = "<" + _F + "I" + _F
_M, _L, _C, _Q, _Z, _P, _T = 77, 76, 67, 81, 90, 80, 84


def _paint(value):
    # a colour as an int, or a gradient from a Doc; None paints nothing
    if value is None:
        return _NO_PAINT
    if _wash and value < _GRADIENT:
        return mix(value, _wash[0], _wash[1])
    return value


def _style(fill, stroke, width, opacity, extra):
    return (
        _paint(fill),
        _NO_STROKE if stroke is None else _paint(stroke),
        width,
        1.0 if opacity is None else opacity,
        len(extra),
    )


class Data:
    """Path data: what `pts` and `smooth` give, and `path` takes.

    Add path data written as text to either end of it, as you would to a
    string: ``smooth(points) + "L800 480Z"``.
    """

    def __init__(self, segments):
        self.segments = segments

    def __add__(self, other):
        return Data(self.segments + _data(other))

    def __radd__(self, other):
        return Data(_data(other) + self.segments)

    def tail(self):
        """The same path without its opening "M", to carry on from another."""
        return Data(bytes((_P,)) + self.segments[1:])


def _data(d):
    if isinstance(d, Data):
        return d.segments
    d = d.encode()
    return _pack(_TEXT, _T, len(d)) + d


def circle(cx, cy, r, fill=None, stroke=None, width=1, opacity=None, extra=""):
    shape = _pack(_CIRCLE, 1, cx, cy, r, *_style(fill, stroke, width, opacity, extra))
    return shape + extra.encode() if extra else shape


def ellipse(cx, cy, rx, ry, fill=None, stroke=None, width=1, opacity=None, rot=0, extra=""):
    shape = _pack(_ELLIPSE, 2, cx, cy, rx, ry, rot, *_style(fill, stroke, width, opacity, extra))
    return shape + extra.encode() if extra else shape


def rect(x, y, w, h, fill=None, r=0, stroke=None, width=1, opacity=None, extra=""):
    shape = _pack(_RECT, 3, x, y, w, h, r, *_style(fill, stroke, width, opacity, extra))
    return shape + extra.encode() if extra else shape


def path(d, fill=None, stroke=None, width=1, opacity=None, extra=""):
    """A path from its data: text, as SVG writes it, or what `pts` and `smooth` give."""
    d = _data(d)
    shape = _pack(_PATH, 4, len(d)) + d + _pack(_STYLED, *_style(fill, stroke, width, opacity, extra))
    return shape + extra.encode() if extra else shape


def line(x0, y0, x1, y1, stroke, width=1, opacity=None, extra=""):
    return path(Data(_pack(_SEG2, _M, x0, y0) + _pack(_SEG2, _L, x1, y1)), None, stroke, width, opacity, extra)


def pts(points, close=False):
    """Path data through *points*, straight lines."""
    d = [_pack(_SEG2, _L, x, y) for x, y in points]
    d[0] = _pack(_SEG2, _M, points[0][0], points[0][1])
    if close:
        d.append(b"Z")
    return Data(b"".join(d))


def smooth(points, close=False):
    """Path data through *points* as one smooth curve (Catmull-Rom, as cubics)."""
    n = len(points)
    d = [_pack(_SEG2, _M, points[0][0], points[0][1])]
    last = n if close else n - 1
    for i in range(last):
        if close:
            p0, p1, p2, p3 = points[(i - 1) % n], points[i], points[(i + 1) % n], points[(i + 2) % n]
        else:
            p0, p1, p2, p3 = points[max(i - 1, 0)], points[i], points[i + 1], points[min(i + 2, n - 1)]
        d.append(
            _pack(
                _SEG6,
                _C,
                p1[0] + (p2[0] - p0[0]) / 6,
                p1[1] + (p2[1] - p0[1]) / 6,
                p2[0] - (p3[0] - p1[0]) / 6,
                p2[1] - (p3[1] - p1[1]) / 6,
                p2[0],
                p2[1],
            )
        )
    if close:
        d.append(b"Z")
    return Data(b"".join(d))


def limb(x0, y0, x1, y1, bend, w0, w1, fill, opacity=None):
    """A curved, tapering limb from one point to another, round at both ends.

    *bend* pushes the middle sideways, as a fraction of the length: positive
    bends to the left of the direction of travel.
    """
    dx, dy = x1 - x0, y1 - y0
    length = math.sqrt(dx * dx + dy * dy) or 1
    nx, ny = dy / length, -dx / length
    cx, cy = (x0 + x1) / 2 + nx * bend * length, (y0 + y1) / 2 + ny * bend * length
    ex, ey = cx - x0, cy - y0
    el = math.sqrt(ex * ex + ey * ey) or 1
    n0x, n0y = ey / el, -ex / el
    ex, ey = x1 - cx, y1 - cy
    el = math.sqrt(ex * ex + ey * ey) or 1
    n1x, n1y = ey / el, -ex / el
    h0, h1, hm = w0 / 2, w1 / 2, (w0 + w1) / 4
    fill = _paint(fill)
    if opacity is None:
        opacity = 1.0
    # the body, a path, and a circle at each end: three shapes in one go
    return _pack(
        _LIMB,
        4,
        _LIMB_D,
        _M,
        x0 + n0x * h0,
        y0 + n0y * h0,
        _Q,
        cx + nx * hm,
        cy + ny * hm,
        x1 + n1x * h1,
        y1 + n1y * h1,
        _L,
        x1 - n1x * h1,
        y1 - n1y * h1,
        _Q,
        cx - nx * hm,
        cy - ny * hm,
        x0 - n0x * h0,
        y0 - n0y * h0,
        _Z,
        fill,
        _NO_STROKE,
        1,
        opacity,
        0,
        1,
        x0,
        y0,
        h0,
        fill,
        _NO_STROKE,
        1,
        opacity,
        0,
        1,
        x1,
        y1,
        h1,
        fill,
        _NO_STROKE,
        1,
        opacity,
        0,
    )


def group(body, transform=None, opacity=None):
    transform = transform.encode() if transform else b""
    return _pack(_GROUP, 6, 1.0 if opacity is None else opacity, len(transform)) + transform + body + b"\x07"


def at(x, y, body, rot=0, scale=1, flip=False):
    """*body* moved to (x, y), turned *rot* degrees and scaled about its origin."""
    return _pack(_AT, 8, x, y, rot, scale, 1 if flip else 0) + body + b"\x07"


class Doc:
    """A drawing: shapes in paint order, and the gradients they use."""

    def __init__(self):
        self._defs = []
        self._body = []

    def _stops(self, stops):
        out = []
        for stop in stops:
            out.append(_pack(_STOP, stop[0], _paint(stop[1]), stop[2] if len(stop) > 2 else 1))
        return b"".join(out)

    def linear(self, stops, x1=0, y1=0, x2=0, y2=1, user=False):
        """A linear gradient; returns the paint to fill or stroke with.

        Coordinates are fractions of the shape's box, or drawing units with
        *user*. Each stop is ``(offset, colour)`` or ``(offset, colour, opacity)``.
        """
        self._defs.append(_pack(_LINEAR, 11, x1, y1, x2, y2, 1 if user else 0, len(stops)) + self._stops(stops))
        return _GRADIENT + len(self._defs) - 1

    def radial(self, stops, cx=0.5, cy=0.5, r=0.5, fx=None, fy=None, user=False):
        """A radial gradient, with its bright point at (*fx*, *fy*) when given."""
        focus = fx is not None
        self._defs.append(
            _pack(_RADIAL, 12, cx, cy, r, 1 if focus else 0, fx if focus else 0, fy if focus else 0, 1 if user else 0, len(stops))
            + self._stops(stops)
        )
        return _GRADIENT + len(self._defs) - 1

    def add(self, *shapes):
        self._body.extend(shapes)

    def compact(self, view):
        """The drawing showing *view*, an ``(x, y, width, height)`` of it, in svgio's compact form."""
        x, y, w, h = view
        return b"".join([_MAGIC, _pack(_VIEW, 10, x, y, w, h)] + self._defs + [b"\x0d"] + self._body + [b"\x0e"])

    def source(self, view):
        """What `svgio.SvgDecoder.open` takes for *view*: compact where svgio reads it, else SVG text."""
        if COMPACT:
            return self.compact(view)
        return expand(self.compact(view)).encode()

    def svg(self, view):
        """The SVG text showing *view*, an ``(x, y, width, height)`` of the drawing."""
        return expand(self.compact(view))


# -- the compact form as SVG text ----------------------------------------

#: True where svgio opens the compact form itself.
COMPACT = hasattr(svgio, "expand")


def _n(v):
    # five figures is finer than a pixel at any size a board draws
    return "%.5g" % v


def _color(paint):
    if paint == _NO_PAINT:
        return "none"
    if paint >= _GRADIENT:
        return "url(#g%d)" % (paint - _GRADIENT)
    return "#%06x" % paint


def _styled(blob, at, extra_first=""):
    """The style attributes at *at*, and where the record ends."""
    fill, stroke, width, opacity, n = struct.unpack_from(_STYLED, blob, at)
    at += struct.calcsize(_STYLED)
    extra = extra_first + str(blob[at : at + n], "utf-8")
    s = ' fill="%s"' % _color(fill)
    if stroke != _NO_STROKE:
        s += ' stroke="%s" stroke-width="%s" stroke-linecap="round" stroke-linejoin="round"' % (_color(stroke), _n(width))
    if opacity < 1:
        s += ' opacity="%s"' % _n(opacity)
    return s, extra, at + n


def _stops_text(blob, at, count):
    out = []
    size = struct.calcsize(_STOP)
    for _ in range(count):
        offset, color, opacity = struct.unpack_from(_STOP, blob, at)
        at += size
        s = '<stop offset="%s" stop-color="%s"' % (_n(offset), _color(color))
        if opacity < 1:
            s += ' stop-opacity="%s"' % _n(opacity)
        out.append(s + "/>")
    return "".join(out), at


def _data_text(blob, at, end):
    out = []
    two, six, four = struct.calcsize(_SEG2), struct.calcsize(_SEG6), 1 + 4 * struct.calcsize(_F)
    while at < end:
        op = blob[at]
        if op == _M or op == _L or op == _P:
            _, x, y = struct.unpack_from(_SEG2, blob, at)
            out.append("%s%s %s" % ("" if op == _P else chr(op), _n(x), _n(y)))
            at += two
        elif op == _C:
            v = struct.unpack_from(_SEG6, blob, at)
            out.append("C%s %s %s %s %s %s" % tuple(_n(c) for c in v[1:]))
            at += six
        elif op == _Q:
            v = struct.unpack_from("<B4" + _F, blob, at)
            out.append("Q%s %s %s %s" % tuple(_n(c) for c in v[1:]))
            at += four
        elif op == _Z:
            out.append("Z")
            at += 1
        elif op == _T:
            n = struct.unpack_from(_TEXT, blob, at)[1]
            out.append(str(blob[at + 3 : at + 3 + n], "utf-8"))
            at += 3 + n
        else:
            raise ValueError("not path data")
    return "".join(out)


def expand(blob):
    """The SVG text a drawing in the compact form stands for.

    It is the text svgio makes of it, character for character, so a drawing
    is the same pixels whichever way it reaches svgio.
    """
    if bytes(blob[:5]) != _MAGIC:
        raise ValueError("not a drawing in this runtime's compact form")
    blob = memoryview(blob)
    out = []
    at = 5
    end = len(blob)
    gradients = 0
    while at < end:
        op = blob[at]
        if op == 1:
            _, cx, cy, r = struct.unpack_from("<B3" + _F, blob, at)
            style, extra, at = _styled(blob, at + struct.calcsize("<B3" + _F))
            if extra:
                style += " " + extra
            out.append('<circle cx="%s" cy="%s" r="%s"%s/>' % (_n(cx), _n(cy), _n(r), style))
        elif op == 2:
            _, cx, cy, rx, ry, rot = struct.unpack_from("<B5" + _F, blob, at)
            style, extra, at = _styled(blob, at + struct.calcsize("<B5" + _F))
            if rot:
                extra = (extra + ' transform="rotate(%s %s %s)"' % (_n(rot), _n(cx), _n(cy))).strip()
            if extra:
                style += " " + extra
            out.append('<ellipse cx="%s" cy="%s" rx="%s" ry="%s"%s/>' % (_n(cx), _n(cy), _n(rx), _n(ry), style))
        elif op == 3:
            _, x, y, w, h, r = struct.unpack_from("<B5" + _F, blob, at)
            style, extra, at = _styled(blob, at + struct.calcsize("<B5" + _F))
            if r:
                extra = ('rx="%s" ' % _n(r)) + extra
            if extra:
                style += " " + extra
            out.append('<rect x="%s" y="%s" width="%s" height="%s"%s/>' % (_n(x), _n(y), _n(w), _n(h), style))
        elif op == 4:
            n = struct.unpack_from(_PATH, blob, at)[1]
            d = _data_text(blob, at + 5, at + 5 + n)
            style, extra, at = _styled(blob, at + 5 + n)
            if extra:
                style += " " + extra
            out.append('<path d="%s"%s/>' % (d, style))
        elif op == 6:
            _, opacity, n = struct.unpack_from(_GROUP, blob, at)
            at += struct.calcsize(_GROUP)
            attrs = ""
            if n:
                attrs += ' transform="%s"' % str(blob[at : at + n], "utf-8")
            if opacity < 1:
                attrs += ' opacity="%s"' % _n(opacity)
            at += n
            out.append("<g%s>" % attrs)
        elif op == 7:
            out.append("</g>")
            at += 1
        elif op == 8:
            _, x, y, rot, scale, flip = struct.unpack_from(_AT, blob, at)
            at += struct.calcsize(_AT)
            t = "translate(%s %s)" % (_n(x), _n(y))
            if rot:
                t += " rotate(%s)" % _n(rot)
            if flip:
                t += " scale(%s %s)" % (_n(-scale), _n(scale))
            elif scale != 1:
                t += " scale(%s)" % _n(scale)
            out.append('<g transform="%s">' % t)
        elif op == 10:
            _, x, y, w, h = struct.unpack_from(_VIEW, blob, at)
            at += struct.calcsize(_VIEW)
            out.append(
                '<svg xmlns="http://www.w3.org/2000/svg" width="%s" height="%s" viewBox="%s %s %s %s"><defs>'
                % (_n(w), _n(h), _n(x), _n(y), _n(w), _n(h))
            )
        elif op == 11:
            _, x1, y1, x2, y2, user, count = struct.unpack_from(_LINEAR, blob, at)
            stops, at = _stops_text(blob, at + struct.calcsize(_LINEAR), count)
            units = ' gradientUnits="userSpaceOnUse"' if user else ""
            out.append(
                '<linearGradient id="g%d" x1="%s" y1="%s" x2="%s" y2="%s"%s>%s</linearGradient>'
                % (gradients, _n(x1), _n(y1), _n(x2), _n(y2), units, stops)
            )
            gradients += 1
        elif op == 12:
            _, cx, cy, r, focus, fx, fy, user, count = struct.unpack_from(_RADIAL, blob, at)
            stops, at = _stops_text(blob, at + struct.calcsize(_RADIAL), count)
            units = ' gradientUnits="userSpaceOnUse"' if user else ""
            where = ' fx="%s" fy="%s"' % (_n(fx), _n(fy)) if focus else ""
            out.append(
                '<radialGradient id="g%d" cx="%s" cy="%s" r="%s"%s%s>%s</radialGradient>'
                % (gradients, _n(cx), _n(cy), _n(r), where, units, stops)
            )
            gradients += 1
        elif op == 13:
            out.append("</defs>")
            at += 1
        elif op == 14:
            out.append("</svg>")
            at += 1
        else:
            raise ValueError("not a drawing in the compact form")
    return "".join(out)


def render(source, width, background=None):
    """Draw a drawing, as `Doc.source` or `Doc.svg` gives it, *width* pixels wide.

    Returns:
        ``(pixels, alpha, width, height)``: RGB565 and coverage, the pair
        LVGL calls RGB565A8. With a *background* colour the picture is
        blended over it and *alpha* is None.
    """
    decoder = svgio.SvgDecoder()
    w, h = decoder.open(source.encode() if isinstance(source, str) else source, width=width)
    pixels = bytearray(w * h * 2)
    if background is None:
        alpha = bytearray(w * h)
        decoder.decode(pixels, alpha)
        return pixels, alpha, w, h
    c = ((background >> 8) & 0xF800) | ((background >> 5) & 0x07E0) | ((background >> 3) & 0x1F)
    lo, hi = c & 255, c >> 8
    if lo or hi:
        for i in range(0, len(pixels), 2):
            pixels[i] = lo
            pixels[i + 1] = hi
    decoder.decode(pixels)
    return pixels, None, w, h
