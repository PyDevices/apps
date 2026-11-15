# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Build a vector drawing in Python and draw it at any size with svgio.

A `Doc` collects shapes and gradients and gives back SVG text that keeps to
what svgio reads: paths, strokes, transforms, opacity and gradients. The view
is a rectangle of the drawing, so a close-up is the same drawing with a
smaller view.

Example::

    doc = Doc()
    glow = doc.radial([(0, 0xFFF3B0, 1), (1, 0xFFF3B0, 0)])
    doc.add(circle(50, 50, 40, glow))
    pixels, alpha, w, h = render(doc.svg((0, 0, 100, 100)), 200)
"""

import math

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


def _paint(value):
    # a colour as an int, or a gradient's "url(#id)" from a Doc
    if value is None:
        return "none"
    if isinstance(value, int):
        return "#%06x" % value
    return value


def _style(fill, stroke, width, opacity, extra):
    s = ' fill="%s"' % _paint(fill)
    if stroke is not None:
        s += ' stroke="%s" stroke-width="%s" stroke-linecap="round" stroke-linejoin="round"' % (
            _paint(stroke),
            _n(width),
        )
    if opacity is not None and opacity < 1:
        s += ' opacity="%s"' % _n(opacity)
    if extra:
        s += " " + extra
    return s


def _n(v):
    # two decimals is finer than a pixel at any size a board draws
    if isinstance(v, int):
        return "%d" % v
    s = "%.2f" % v
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def circle(cx, cy, r, fill=None, stroke=None, width=1, opacity=None, extra=""):
    return '<circle cx="%s" cy="%s" r="%s"%s/>' % (_n(cx), _n(cy), _n(r), _style(fill, stroke, width, opacity, extra))


def ellipse(cx, cy, rx, ry, fill=None, stroke=None, width=1, opacity=None, rot=0, extra=""):
    if rot:
        extra = (extra + ' transform="rotate(%s %s %s)"' % (_n(rot), _n(cx), _n(cy))).strip()
    return '<ellipse cx="%s" cy="%s" rx="%s" ry="%s"%s/>' % (
        _n(cx),
        _n(cy),
        _n(rx),
        _n(ry),
        _style(fill, stroke, width, opacity, extra),
    )


def rect(x, y, w, h, fill=None, r=0, stroke=None, width=1, opacity=None, extra=""):
    if r:
        extra = ('rx="%s" ' % _n(r)) + extra
    return '<rect x="%s" y="%s" width="%s" height="%s"%s/>' % (
        _n(x),
        _n(y),
        _n(w),
        _n(h),
        _style(fill, stroke, width, opacity, extra),
    )


def path(d, fill=None, stroke=None, width=1, opacity=None, extra=""):
    return '<path d="%s"%s/>' % (d, _style(fill, stroke, width, opacity, extra))


def line(x0, y0, x1, y1, stroke, width=1, opacity=None, extra=""):
    return path("M%s %sL%s %s" % (_n(x0), _n(y0), _n(x1), _n(y1)), None, stroke, width, opacity, extra)


def pts(points, close=False):
    """Path data through *points*, straight lines."""
    d = "M" + "L".join("%s %s" % (_n(x), _n(y)) for x, y in points)
    return d + "Z" if close else d


def smooth(points, close=False):
    """Path data through *points* as one smooth curve (Catmull-Rom, as cubics)."""
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
    return "".join(d)


def limb(x0, y0, x1, y1, bend, w0, w1, fill, opacity=None):
    """A curved, tapering limb from one point to another, round at both ends.

    *bend* pushes the middle sideways, as a fraction of the length: positive
    bends to the left of the direction of travel.
    """
    dx, dy = x1 - x0, y1 - y0
    length = math.sqrt(dx * dx + dy * dy) or 1
    nx, ny = dy / length, -dx / length
    cx, cy = (x0 + x1) / 2 + nx * bend * length, (y0 + y1) / 2 + ny * bend * length

    def normal(ax, ay, bx, by):
        ex, ey = bx - ax, by - ay
        el = math.sqrt(ex * ex + ey * ey) or 1
        return ey / el, -ex / el

    n0x, n0y = normal(x0, y0, cx, cy)
    n1x, n1y = normal(cx, cy, x1, y1)
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
    return path(d, fill, opacity=opacity) + circle(x0, y0, h0, fill, opacity=opacity) + circle(x1, y1, h1, fill, opacity=opacity)


def group(body, transform=None, opacity=None):
    attrs = ""
    if transform:
        attrs += ' transform="%s"' % transform
    if opacity is not None and opacity < 1:
        attrs += ' opacity="%s"' % _n(opacity)
    return "<g%s>%s</g>" % (attrs, body)


def at(x, y, body, rot=0, scale=1, flip=False):
    """*body* moved to (x, y), turned *rot* degrees and scaled about its origin."""
    t = "translate(%s %s)" % (_n(x), _n(y))
    if rot:
        t += " rotate(%s)" % _n(rot)
    if flip:
        t += " scale(%s %s)" % (_n(-scale), _n(scale))
    elif scale != 1:
        t += " scale(%s)" % _n(scale)
    return group(body, t)


class Doc:
    """A drawing: shapes in paint order, and the gradients they use."""

    def __init__(self):
        self._defs = []
        self._body = []

    def _stops(self, stops):
        out = []
        for stop in stops:
            offset, color = stop[0], stop[1]
            opacity = stop[2] if len(stop) > 2 else 1
            s = '<stop offset="%s" stop-color="#%06x"' % (_n(offset), color)
            if opacity < 1:
                s += ' stop-opacity="%s"' % _n(opacity)
            out.append(s + "/>")
        return "".join(out)

    def linear(self, stops, x1=0, y1=0, x2=0, y2=1, user=False):
        """A linear gradient; returns the paint to fill or stroke with.

        Coordinates are fractions of the shape's box, or drawing units with
        *user*. Each stop is ``(offset, colour)`` or ``(offset, colour, opacity)``.
        """
        gid = "g%d" % len(self._defs)
        units = ' gradientUnits="userSpaceOnUse"' if user else ""
        self._defs.append(
            '<linearGradient id="%s" x1="%s" y1="%s" x2="%s" y2="%s"%s>%s</linearGradient>'
            % (gid, _n(x1), _n(y1), _n(x2), _n(y2), units, self._stops(stops))
        )
        return "url(#%s)" % gid

    def radial(self, stops, cx=0.5, cy=0.5, r=0.5, fx=None, fy=None, user=False):
        """A radial gradient, with its bright point at (*fx*, *fy*) when given."""
        gid = "g%d" % len(self._defs)
        units = ' gradientUnits="userSpaceOnUse"' if user else ""
        focus = ""
        if fx is not None:
            focus = ' fx="%s" fy="%s"' % (_n(fx), _n(fy))
        self._defs.append(
            '<radialGradient id="%s" cx="%s" cy="%s" r="%s"%s%s>%s</radialGradient>'
            % (gid, _n(cx), _n(cy), _n(r), focus, units, self._stops(stops))
        )
        return "url(#%s)" % gid

    def add(self, *shapes):
        self._body.extend(shapes)

    def svg(self, view):
        """The SVG text showing *view*, an ``(x, y, width, height)`` of the drawing."""
        x, y, w, h = view
        return '<svg xmlns="http://www.w3.org/2000/svg" width="%s" height="%s" viewBox="%s %s %s %s"><defs>%s</defs>%s</svg>' % (
            _n(w),
            _n(h),
            _n(x),
            _n(y),
            _n(w),
            _n(h),
            "".join(self._defs),
            "".join(self._body),
        )


def render(svg_text, width, background=None):
    """Draw SVG text *width* pixels wide.

    Returns:
        ``(pixels, alpha, width, height)``: RGB565 and coverage, the pair
        LVGL calls RGB565A8. With a *background* colour the picture is
        blended over it and *alpha* is None.
    """
    decoder = svgio.SvgDecoder()
    w, h = decoder.open(svg_text.encode(), width=width)
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
