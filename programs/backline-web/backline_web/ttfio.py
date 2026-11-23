# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Draw icon glyphs in a web page, where MicroPython has no ttfio.

MicroPython's WebAssembly build has no ``ttfio``, so the page puts this one in
its place. The page loads the icons font itself (``page.js`` registers it
with the browser) and draws each glyph on a canvas; this module asks it for
one glyph's box and coverage at a time, with the same calls ``icons`` makes
of the real module.

Only the font the page loaded is drawn: ``Font`` ignores the bytes it's
given.
"""

import js


class Font:
    """The page's icons font, at any size."""

    def __init__(self, data=None, scratch=0):
        if not js.backlineGlyph:
            raise OSError("the page has no icons font loaded")

    def glyph(self, code, size):
        """``(w, h, x, y, advance)`` of glyph ``code`` at ``size`` px: its
        inked box, its left edge from the origin and its top from the
        baseline (negative is up)."""
        return tuple(int(v) for v in str(js.backlineGlyph(code, size)).split(","))

    def render(self, code, size, buf=None, stride=0):
        """The glyph's coverage, ``w * h`` bytes, or drawn into ``buf`` at
        ``stride`` bytes a row."""
        w, h = self.glyph(code, size)[:2]
        data = bytes(js.backlineRender(code, size))
        if buf is None:
            return bytearray(data)
        stride = stride or w
        for row in range(h):
            buf[row * stride:row * stride + w] = data[row * w:row * w + w]
        return buf
