# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Lines of text on a board's display, sent one row at a time.

A one-bit OLED (SH1106, SSD1305, SSD1306) is drawn with ``framebuf`` straight
into its driver's copy of the panel, and each changed row goes out as one
page: drawing a pixel at a time through ``blit_rect`` costs about 90 ms a
line on a classic ESP32, too long to sit beside audio. That leans on two
driver internals, ``_buffer`` and ``_flush``, at rotation 0. Every other
display gets each row composed in a strip with pygraphics and sent in one
``blit_rect``.
"""

WHITE = 0xFFFF
BLACK = 0


def clean(text):
    """Printable ASCII only: the fonts have nothing else."""
    return "".join(c if " " <= c <= "~" else "?" for c in text)


def wrap(text, width):
    """Split text at the last space that fits in width, or at width if none does."""
    if len(text) <= width:
        return text, ""
    cut = text.rfind(" ", 0, width + 1)
    if cut <= 0:
        return text[:width], text[width:]
    return text[:cut], text[cut + 1 :]


def _one_bit(display):
    buf = getattr(display, "_buffer", None)
    if buf is None or not hasattr(display, "_flush"):
        return False
    if getattr(display, "rotation", 0) not in (0, None):
        return False
    return len(buf) == display.width * ((display.height + 7) // 8)


class Rows:
    """Rows of text, each redrawn only when it changes.

    `line` changes a row in memory and `send` puts one changed row on the
    panel, so a program that must keep audio fed can draw a row a turn.

    Args:
        display: the board's ``display_drv``.

    Attributes:
        count: how many rows fit.
        cols: characters in a full row.
        height: a row's height in pixels.
        width: the display's width in pixels.
    """

    def __init__(self, display):
        self.display = display
        self.width = display.width
        self._dirty = []
        if _one_bit(display):
            import framebuf

            self._fb = framebuf.FrameBuffer(display._buffer, display.width, display.height, framebuf.MONO_VLSB)
            self._mono = True
            self.height = 8
            self._scale = 1
            self._fg = 1
            self._fb.fill(0)
            display._flush(0, 0, display.width - 1, display.height - 1)
        else:
            try:
                import pygraphics
            except ImportError:
                raise ImportError("this display needs pygraphics to draw text: mip.install(\"pygraphics\")")
            depth = getattr(display, "color_depth", 16) or 16
            fmt = {1: pygraphics.MONO_HMSB, 8: pygraphics.GS8, 16: pygraphics.RGB565, 24: pygraphics.RGB888}[depth]
            self._mono = False
            self._scale = max(1, display.width // 320)
            self.height = 16 * self._scale
            self._fg = WHITE if depth == 16 else (1 if depth == 1 else 0xFFFFFF if depth == 24 else 0xFF)
            self._depth = depth
            self._fmt = fmt
            self._pg = pygraphics
            self._strips = {}  # width: (buffer, FrameBuffer), one per row width in use
            display.fill_rect(0, 0, display.width, display.height, BLACK)
        self.count = display.height // self.height
        self.cols = display.width // (8 * self._scale)
        self._text = [None] * self.count
        self._widths = [self.width] * self.count

    def line(self, row, text, width=None):
        """Put text on a row, replacing what was there; nothing happens if it's unchanged.

        Args:
            row: 0 is the top.
            text: cut to fit.
            width: pixels from the left edge that the text owns; the rest of
                the row is left alone, for a program's own drawing.
        """
        if not 0 <= row < self.count:
            return
        width = self.width if width is None else width
        text = clean(text)[: width // (8 * self._scale)]
        if self._text[row] == text and self._widths[row] == width:
            return
        self._text[row] = text
        self._widths[row] = width
        if row not in self._dirty:
            self._dirty.append(row)

    def lines(self, first_row, texts):
        """Put each of ``texts`` on its own row, starting at ``first_row``."""
        for i, text in enumerate(texts):
            self.line(first_row + i, text)

    def send(self):
        """Put one changed row on the panel. Returns False when none was waiting."""
        if not self._dirty:
            return False
        row = self._dirty.pop(0)
        text = self._text[row]
        width = self._widths[row]
        y = row * self.height
        if self._mono:
            self._fb.fill_rect(0, y, width, 8, 0)
            self._fb.text(text, 0, y, 1)
            self.display._flush(0, y, width - 1, y + 7)
        else:
            strip = self._strips.get(width)
            if strip is None:
                buf = bytearray((width * self._depth + 7) // 8 * self.height)
                strip = self._strips[width] = (buf, self._pg.FrameBuffer(buf, width, self.height, self._fmt))
            buf, fb = strip
            fb.fill(BLACK)
            fb.text16(text, 0, 0, self._fg, self._scale)
            self.display.blit_rect(buf, 0, y, width, self.height)
        return True

    def send_all(self):
        """Put every changed row on the panel."""
        while self.send():
            pass

    def rect(self, x, y, w, h, on=True):
        """Fill a rectangle in white, or black when ``on`` is False, straight to the panel."""
        self.display.fill_rect(x, y, w, h, WHITE if on else BLACK)
