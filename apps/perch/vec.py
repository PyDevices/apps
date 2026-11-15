# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Build a vector drawing in Python and draw it at any size with svgio.

A `Doc` collects shapes and gradients, keeping to what svgio reads: paths,
strokes, transforms, opacity and gradients. The view is a rectangle of the
drawing, so a close-up is the same drawing with a smaller view.

Where svgio reads its compact form, shapes are kept as numbers, not text:
writing every coordinate out in Python, for svgio to read back, is most of
the time a drawing takes on a board. Where it doesn't, the same helpers
write SVG text. Either way a shape is bytes to the code that draws, so the
art is written once. `Doc.source` gives what `SvgDecoder.open` takes, and
`Doc.svg` the SVG text.

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
_seen = None


def wash(color=None, amount=0.0):
    """Mix every colour drawn from now on toward *color*: moonlight, dusk, fog.

    Call it with no arguments to draw in true colours again.
    """
    global _wash
    _wash = (color, amount) if color is not None and amount > 0 else None


def colours(note=True):
    """Start noting every colour drawn, in order; returns the list they go in.

    The same drawing made in two sets of colours gives two lists that pair
    off, old with new: the table `svgio.SvgDecoder.decode` takes as
    ``colors`` to draw one as the other. ``colours(False)`` stops.
    """
    global _seen
    _seen = [] if note else None
    return _seen


#: True where svgio opens the compact form itself.
COMPACT = hasattr(svgio, "expand")

_GRADIENT = 0x1000000  # a paint at or above this is a gradient, by its number


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
        if COMPACT:
            return Data(b"P" + self.segments[1:])
        return Data(self.segments[1:])


# -- shapes as records of svgio's compact form ---------------------------
#
# A record is an opcode byte and its fields, which svgio's README lists; a
# number is this runtime's own float, so svgio writes it as "%.5g" would here.

_F = "d" if 1.0 + 1e-10 != 1.0 else "f"
_MAGIC = b"\x01SVG" + (b"\x08" if _F == "d" else b"\x04")
_NO_PAINT = 0xFFFFFFFF  # fill="none"
_NO_STROKE = 0xFFFFFFFE  # no stroke attributes at all

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


def _p_paint(value):
    # a colour as an int, or a gradient from a Doc; None paints nothing
    if value is None:
        return _NO_PAINT
    if value < _GRADIENT:
        if _wash:
            value = mix(value, _wash[0], _wash[1])
        if _seen is not None:
            _seen.append(value)
    return value


def _p_style(fill, stroke, width, opacity, extra):
    return (
        _p_paint(fill),
        _NO_STROKE if stroke is None else _p_paint(stroke),
        width,
        1.0 if opacity is None else opacity,
        len(extra),
    )


def _p_data(d):
    if isinstance(d, Data):
        return d.segments
    d = d.encode()
    return _pack(_TEXT, _T, len(d)) + d



def _p_circle(cx, cy, r, fill=None, stroke=None, width=1, opacity=None, extra=""):
    shape = _pack(_CIRCLE, 1, cx, cy, r, *_p_style(fill, stroke, width, opacity, extra))
    return shape + extra.encode() if extra else shape


def _p_ellipse(cx, cy, rx, ry, fill=None, stroke=None, width=1, opacity=None, rot=0, extra=""):
    shape = _pack(_ELLIPSE, 2, cx, cy, rx, ry, rot, *_p_style(fill, stroke, width, opacity, extra))
    return shape + extra.encode() if extra else shape


def _p_rect(x, y, w, h, fill=None, r=0, stroke=None, width=1, opacity=None, extra=""):
    shape = _pack(_RECT, 3, x, y, w, h, r, *_p_style(fill, stroke, width, opacity, extra))
    return shape + extra.encode() if extra else shape


def _p_path(d, fill=None, stroke=None, width=1, opacity=None, extra=""):
    """A path from its data: text, as SVG writes it, or what `pts` and `smooth` give."""
    d = _p_data(d)
    shape = _pack(_PATH, 4, len(d)) + d + _pack(_STYLED, *_p_style(fill, stroke, width, opacity, extra))
    return shape + extra.encode() if extra else shape


def _p_line(x0, y0, x1, y1, stroke, width=1, opacity=None, extra=""):
    return _p_path(Data(_pack(_SEG2, _M, x0, y0) + _pack(_SEG2, _L, x1, y1)), None, stroke, width, opacity, extra)


def _p_pts(points, close=False):
    """Path data through *points*, straight lines."""
    d = [_pack(_SEG2, _L, x, y) for x, y in points]
    d[0] = _pack(_SEG2, _M, points[0][0], points[0][1])
    if close:
        d.append(b"Z")
    return Data(b"".join(d))


def _p_smooth(points, close=False):
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


def _p_limb(x0, y0, x1, y1, bend, w0, w1, fill, opacity=None):
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
    fill = _p_paint(fill)
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


def _p_group(body, transform=None, opacity=None):
    transform = transform.encode() if transform else b""
    return _pack(_GROUP, 6, 1.0 if opacity is None else opacity, len(transform)) + transform + body + b"\x07"


def _p_at(x, y, body, rot=0, scale=1, flip=False):
    """*body* moved to (x, y), turned *rot* degrees and scaled about its origin."""
    return _pack(_AT, 8, x, y, rot, scale, 1 if flip else 0) + body + b"\x07"


# -- shapes as SVG text, for an svgio that reads nothing else ------------


def _n(v):
    # five figures is finer than a pixel at any size a board draws, and one
    # format is the cheapest way to write a number
    return "%.5g" % v


def _t_paint(value):
    if value is None:
        return "none"
    if value >= _GRADIENT:
        return "url(#g%d)" % (value - _GRADIENT)
    if _wash:
        value = mix(value, _wash[0], _wash[1])
    if _seen is not None:
        _seen.append(value)
    return "#%06x" % value


def _t_style(fill, stroke, width, opacity, extra):
    s = ' fill="%s"' % _t_paint(fill)
    if stroke is not None:
        s += ' stroke="%s" stroke-width="%s"' % (_t_paint(stroke), _n(width))
        # round, unless the extra attributes say how
        if "stroke-linecap" not in extra:
            s += ' stroke-linecap="round"'
        if "stroke-linejoin" not in extra:
            s += ' stroke-linejoin="round"'
    if opacity is not None and opacity < 1:
        s += ' opacity="%s"' % _n(opacity)
    if extra:
        s += " " + extra
    return s


def _t_data(d):
    return d.segments if isinstance(d, Data) else d.encode()


def _t_circle(cx, cy, r, fill=None, stroke=None, width=1, opacity=None, extra=""):
    return ('<circle cx="%s" cy="%s" r="%s"%s/>' % (_n(cx), _n(cy), _n(r), _t_style(fill, stroke, width, opacity, extra))).encode()


def _t_ellipse(cx, cy, rx, ry, fill=None, stroke=None, width=1, opacity=None, rot=0, extra=""):
    if rot:
        extra = (extra + ' transform="rotate(%s %s %s)"' % (_n(rot), _n(cx), _n(cy))).strip()
    return (
        '<ellipse cx="%s" cy="%s" rx="%s" ry="%s"%s/>' % (_n(cx), _n(cy), _n(rx), _n(ry), _t_style(fill, stroke, width, opacity, extra))
    ).encode()


def _t_rect(x, y, w, h, fill=None, r=0, stroke=None, width=1, opacity=None, extra=""):
    if r:
        extra = ('rx="%s" ' % _n(r)) + extra
    return (
        '<rect x="%s" y="%s" width="%s" height="%s"%s/>' % (_n(x), _n(y), _n(w), _n(h), _t_style(fill, stroke, width, opacity, extra))
    ).encode()


def _t_path(d, fill=None, stroke=None, width=1, opacity=None, extra=""):
    style = _t_style(fill, stroke, width, opacity, extra)
    if isinstance(d, Data):
        return b'<path d="' + d.segments + ('"%s/>' % style).encode()
    return ('<path d="%s"%s/>' % (d, style)).encode()


def _t_line(x0, y0, x1, y1, stroke, width=1, opacity=None, extra=""):
    return _t_path("M%s %sL%s %s" % (_n(x0), _n(y0), _n(x1), _n(y1)), None, stroke, width, opacity, extra)


def _t_pts(points, close=False):
    d = "M" + "L".join("%s %s" % (_n(x), _n(y)) for x, y in points)
    return Data((d + "Z" if close else d).encode())


def _t_smooth(points, close=False):
    n = len(points)
    d = ["M%s %s" % (_n(points[0][0]), _n(points[0][1]))]
    last = n if close else n - 1
    for i in range(last):
        if close:
            p0, p1, p2, p3 = points[(i - 1) % n], points[i], points[(i + 1) % n], points[(i + 2) % n]
        else:
            p0, p1, p2, p3 = points[max(i - 1, 0)], points[i], points[i + 1], points[min(i + 2, n - 1)]
        d.append(
            "C%s %s %s %s %s %s"
            % (
                _n(p1[0] + (p2[0] - p0[0]) / 6),
                _n(p1[1] + (p2[1] - p0[1]) / 6),
                _n(p2[0] - (p3[0] - p1[0]) / 6),
                _n(p2[1] - (p3[1] - p1[1]) / 6),
                _n(p2[0]),
                _n(p2[1]),
            )
        )
    if close:
        d.append("Z")
    return Data("".join(d).encode())


def _t_limb(x0, y0, x1, y1, bend, w0, w1, fill, opacity=None):
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
    d = "M%s %sQ%s %s %s %sL%s %sQ%s %s %s %sZ" % (
        _n(x0 + n0x * h0),
        _n(y0 + n0y * h0),
        _n(cx + nx * hm),
        _n(cy + ny * hm),
        _n(x1 + n1x * h1),
        _n(y1 + n1y * h1),
        _n(x1 - n1x * h1),
        _n(y1 - n1y * h1),
        _n(cx - nx * hm),
        _n(cy - ny * hm),
        _n(x0 - n0x * h0),
        _n(y0 - n0y * h0),
    )
    return _t_path(d, fill, opacity=opacity) + _t_circle(x0, y0, h0, fill, opacity=opacity) + _t_circle(x1, y1, h1, fill, opacity=opacity)


def _t_group(body, transform=None, opacity=None):
    attrs = ""
    if transform:
        attrs += ' transform="%s"' % transform
    if opacity is not None and opacity < 1:
        attrs += ' opacity="%s"' % _n(opacity)
    return ("<g%s>" % attrs).encode() + body + b"</g>"


def _t_at(x, y, body, rot=0, scale=1, flip=False):
    t = "translate(%s %s)" % (_n(x), _n(y))
    if rot:
        t += " rotate(%s)" % _n(rot)
    if flip:
        t += " scale(%s %s)" % (_n(-scale), _n(scale))
    elif scale != 1:
        t += " scale(%s)" % _n(scale)
    return ('<g transform="%s">' % t).encode() + body + b"</g>"


# -- the helpers the art calls: one of the two sets above ----------------

_data = _p_data if COMPACT else _t_data
circle = _p_circle if COMPACT else _t_circle
ellipse = _p_ellipse if COMPACT else _t_ellipse
rect = _p_rect if COMPACT else _t_rect
path = _p_path if COMPACT else _t_path
line = _p_line if COMPACT else _t_line
pts = _p_pts if COMPACT else _t_pts
smooth = _p_smooth if COMPACT else _t_smooth
limb = _p_limb if COMPACT else _t_limb
group = _p_group if COMPACT else _t_group
at = _p_at if COMPACT else _t_at


class Doc:
    """A drawing: shapes in paint order, and the gradients they use."""

    def __init__(self):
        self._defs = []
        self._body = []

    def _stops(self, stops):
        out = []
        for stop in stops:
            opacity = stop[2] if len(stop) > 2 else 1
            if COMPACT:
                out.append(_pack(_STOP, stop[0], _p_paint(stop[1]), opacity))
            else:
                s = '<stop offset="%s" stop-color="%s"' % (_n(stop[0]), _t_paint(stop[1]))
                out.append((s + (' stop-opacity="%s"/>' % _n(opacity) if opacity < 1 else "/>")).encode())
        return b"".join(out)

    def linear(self, stops, x1=0, y1=0, x2=0, y2=1, user=False):
        """A linear gradient; returns the paint to fill or stroke with.

        Coordinates are fractions of the shape's box, or drawing units with
        *user*. Each stop is ``(offset, colour)`` or ``(offset, colour, opacity)``.
        """
        gid = len(self._defs)
        if COMPACT:
            self._defs.append(_pack(_LINEAR, 11, x1, y1, x2, y2, 1 if user else 0, len(stops)) + self._stops(stops))
        else:
            units = ' gradientUnits="userSpaceOnUse"' if user else ""
            head = '<linearGradient id="g%d" x1="%s" y1="%s" x2="%s" y2="%s"%s>' % (gid, _n(x1), _n(y1), _n(x2), _n(y2), units)
            self._defs.append(head.encode() + self._stops(stops) + b"</linearGradient>")
        return _GRADIENT + gid

    def radial(self, stops, cx=0.5, cy=0.5, r=0.5, fx=None, fy=None, user=False):
        """A radial gradient, with its bright point at (*fx*, *fy*) when given."""
        gid = len(self._defs)
        focus = fx is not None
        if COMPACT:
            self._defs.append(
                _pack(_RADIAL, 12, cx, cy, r, 1 if focus else 0, fx if focus else 0, fy if focus else 0, 1 if user else 0, len(stops))
                + self._stops(stops)
            )
        else:
            units = ' gradientUnits="userSpaceOnUse"' if user else ""
            where = ' fx="%s" fy="%s"' % (_n(fx), _n(fy)) if focus else ""
            head = '<radialGradient id="g%d" cx="%s" cy="%s" r="%s"%s%s>' % (gid, _n(cx), _n(cy), _n(r), where, units)
            self._defs.append(head.encode() + self._stops(stops) + b"</radialGradient>")
        return _GRADIENT + gid

    def add(self, *shapes):
        self._body.extend(shapes)

    def source(self, view):
        """What `svgio.SvgDecoder.open` takes to show *view*, an ``(x, y, width, height)`` of the drawing.

        The compact form where svgio reads it, and SVG text where it doesn't.
        """
        x, y, w, h = view
        if COMPACT:
            return b"".join([_MAGIC, _pack(_VIEW, 10, x, y, w, h)] + self._defs + [b"\x0d"] + self._body + [b"\x0e"])
        head = '<svg xmlns="http://www.w3.org/2000/svg" width="%s" height="%s" viewBox="%s %s %s %s"><defs>' % (
            _n(w),
            _n(h),
            _n(x),
            _n(y),
            _n(w),
            _n(h),
        )
        return b"".join([head.encode()] + self._defs + [b"</defs>"] + self._body + [b"</svg>"])

    def svg(self, view):
        """The SVG text showing *view*, an ``(x, y, width, height)`` of the drawing."""
        source = self.source(view)
        return str(svgio.expand(source) if COMPACT else source, "utf-8")


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
