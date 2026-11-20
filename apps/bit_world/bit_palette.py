# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Provide the color palette, layout scaler, and math helpers for Bit World.

Declares the 32-color Cozy Sci-Fi and Solarpunk palette for the palettes
library, with portable random number and integer trigonometry helpers, a responsive layout scaler for
landscape screens from 480x320 to 800x480, and dithered transition routines.

Needs: palettes, pygraphics.
"""

from array import array
from random import getrandbits, seed
from palettes import Palette
from pygraphics import RGB565, Draw, FrameBuffer

try:
    import framebuf
except ImportError:  # CPython and CircuitPython: pygraphics draws everything
    framebuf = None

# Change these to match your setup.
REF_WIDTH = 800  # Reference landscape design width in pixels
REF_HEIGHT = 480  # Reference landscape design height in pixels
KEY = 0x0020  # Transparent color key; rgb565() shifts any matching color by +1


class BitPalette(Palette):
    """Bit World's 32 hand-tuned colors, each under the name the art code uses.

    The palettes library turns each ``(0xRRGGBB, name)`` pair into an RGB565
    attribute named in capitals (``BitPalette().DEEP_SLATE``).
    """

    _names = (
        # Deep space, chassis shadow, and metallic slate tones.
        (0x060812, "Void"),
        (0x0B1022, "Abyss"),
        (0x121A34, "Night"),
        (0x1C2848, "Deep Slate"),
        (0x2E4068, "Slate"),
        (0x4E6694, "Steel"),
        (0x84A0CC, "Mist"),
        (0xC0D4EE, "Silver"),
        # Maker-lab warm brass, copper, amber, gold, and cream highlights.
        (0x201410, "Dark Wood"),
        (0x3A241A, "Oak"),
        (0x623C20, "Bronze"),
        (0x9C582A, "Copper"),
        (0xE0882C, "Amber"),
        (0xFAC040, "Gold"),
        (0xFFEA78, "Sun Yellow"),
        (0xF8F2E0, "Cream"),
        (0xFFFFFF, "White"),
        # Bioluminescent cyan and hologram teal tones.
        (0x083444, "Deep Teal"),
        (0x106C80, "Teal"),
        (0x20B8D4, "Cyan"),
        (0x5CEEF8, "Aqua Glow"),
        (0xBCFCFF, "Ice Cyan"),
        # Solarpunk flora and mossy ruin greens.
        (0x0E3024, "Dark Moss"),
        (0x185838, "Forest"),
        (0x308E4E, "Moss"),
        (0x54CC6C, "Emerald"),
        (0x9EF484, "Lime Glow"),
        # Plasma, crystal, and sunset accent colors.
        (0x301444, "Plum"),
        (0x683094, "Violet"),
        (0xBC40B0, "Magenta"),
        (0xF86CC6, "Neon Pink"),
        (0xC42A44, "Crimson"),
        (0xF86054, "Coral"),
        (0xFC8E38, "Orange"),
    )

    def __init__(self):
        super().__init__("bit_world", 16)


PALETTE = BitPalette()


# Move a color that equals the transparent key off it by one step.
def keyed(c):
    return c + 1 if c == KEY else c


# Convert 8-bit red, green, and blue channels into a 16-bit RGB565 integer.
def rgb565(r, g, b):
    return keyed(PALETTE.color565(int(r), int(g), int(b)))


# Interpolate linearly between two RGB tuples and return an RGB565 color.
def lerp565(rgb_a, rgb_b, t):
    if t <= 0.0:
        return rgb565(rgb_a[0], rgb_a[1], rgb_a[2])
    if t >= 1.0:
        return rgb565(rgb_b[0], rgb_b[1], rgb_b[2])
    r = rgb_a[0] + (rgb_b[0] - rgb_a[0]) * t
    g = rgb_a[1] + (rgb_b[1] - rgb_a[1]) * t
    b = rgb_a[2] + (rgb_b[2] - rgb_a[2]) * t
    return rgb565(r, g, b)


# Look up a palette color's red, green, and blue channels by its name.
def rgb_of(name):
    for value, entry in BitPalette._names:
        if entry == name:
            return (value >> 16, value >> 8 & 0xFF, value & 0xFF)
    raise KeyError(name)


# The gradients blend between these, so they need the channels, not RGB565.
VOID_RGB = rgb_of("Void")
ABYSS_RGB = rgb_of("Abyss")
NIGHT_RGB = rgb_of("Night")
DEEP_SLATE_RGB = rgb_of("Deep Slate")
SLATE_RGB = rgb_of("Slate")
STEEL_RGB = rgb_of("Steel")
MIST_RGB = rgb_of("Mist")
SILVER_RGB = rgb_of("Silver")

# Each color as RGB565, from the palette.
VOID = keyed(PALETTE.VOID)
ABYSS = keyed(PALETTE.ABYSS)
NIGHT = keyed(PALETTE.NIGHT)
DEEP_SLATE = keyed(PALETTE.DEEP_SLATE)
SLATE = keyed(PALETTE.SLATE)
STEEL = keyed(PALETTE.STEEL)
MIST = keyed(PALETTE.MIST)
SILVER = keyed(PALETTE.SILVER)
DARK_WOOD = keyed(PALETTE.DARK_WOOD)
OAK = keyed(PALETTE.OAK)
BRONZE = keyed(PALETTE.BRONZE)
COPPER = keyed(PALETTE.COPPER)
AMBER = keyed(PALETTE.AMBER)
GOLD = keyed(PALETTE.GOLD)
SUN_YELLOW = keyed(PALETTE.SUN_YELLOW)
CREAM = keyed(PALETTE.CREAM)
WHITE = keyed(PALETTE.WHITE)
DEEP_TEAL = keyed(PALETTE.DEEP_TEAL)
TEAL = keyed(PALETTE.TEAL)
CYAN = keyed(PALETTE.CYAN)
AQUA_GLOW = keyed(PALETTE.AQUA_GLOW)
ICE_CYAN = keyed(PALETTE.ICE_CYAN)
DARK_MOSS = keyed(PALETTE.DARK_MOSS)
FOREST = keyed(PALETTE.FOREST)
MOSS = keyed(PALETTE.MOSS)
EMERALD = keyed(PALETTE.EMERALD)
LIME_GLOW = keyed(PALETTE.LIME_GLOW)
PLUM = keyed(PALETTE.PLUM)
VIOLET = keyed(PALETTE.VIOLET)
MAGENTA = keyed(PALETTE.MAGENTA)
NEON_PINK = keyed(PALETTE.NEON_PINK)
CRIMSON = keyed(PALETTE.CRIMSON)
CORAL = keyed(PALETTE.CORAL)
ORANGE = keyed(PALETTE.ORANGE)

# Flat 75-entry uint16 lookup table mapping byte (b - 46) for '.'..'x' to RGB565.
PALETTE_LUT = array(
    "H",
    (
        KEY, KEY,  # '.' (46), '/' (47)
        VOID, ABYSS, NIGHT, DEEP_SLATE, SLATE, STEEL, MIST, SILVER, WHITE, CREAM,  # '0'..'9'
        KEY, KEY, KEY, KEY, KEY, KEY, KEY,  # ':'..'@'
        KEY, KEY, KEY, KEY, KEY, KEY, KEY, KEY, KEY, KEY, KEY, KEY, KEY,  # 'A'..'M'
        KEY, KEY, KEY, KEY, KEY, KEY, KEY, KEY, KEY, KEY, KEY, KEY, KEY,  # 'N'..'Z'
        KEY, KEY, KEY, KEY, KEY, KEY,  # '['..'`'
        DARK_WOOD, OAK, BRONZE, COPPER, AMBER, GOLD, SUN_YELLOW,  # 'a'..'g'
        DEEP_TEAL, TEAL, CYAN, AQUA_GLOW, ICE_CYAN,  # 'h'..'l'
        DARK_MOSS, FOREST, MOSS, EMERALD, LIME_GLOW,  # 'm'..'q'
        PLUM, VIOLET, MAGENTA, NEON_PINK, CRIMSON, CORAL, ORANGE,  # 'r'..'x'
    ),
)

# Precomputed 256-entry sine table (-1024..1024) as a single constant buffer.
SIN256 = array(
    "h",
    b"\x00\x00\x19\x00\x32\x00\x4b\x00\x64\x00\x7d\x00\x96\x00\xaf\x00\xc7\x00\xe0\x00\xf8\x00\x11\x01\x29\x01\x41\x01\x58\x01\x70\x01\x87\x01\x9e\x01\xb5\x01\xcc\x01\xe2\x01\xf8\x01\x0e\x02\x23\x02\x38\x02\x4d\x02\x61\x02\x75\x02\x89\x02\x9c\x02\xaf\x02\xc2\x02"
    b"\xd4\x02\xe5\x02\xf6\x02\x07\x03\x17\x03\x27\x03\x36\x03\x45\x03\x53\x03\x61\x03\x6e\x03\x7a\x03\x87\x03\x92\x03\x9d\x03\xa8\x03\xb2\x03\xbb\x03\xc4\x03\xcc\x03\xd3\x03\xda\x03\xe1\x03\xe7\x03\xec\x03\xf0\x03\xf4\x03\xf8\x03\xfb\x03\xfd\x03\xfe\x03\xff\x03"
    b"\x00\x04\xff\x03\xfe\x03\xfd\x03\xfb\x03\xf8\x03\xf4\x03\xf0\x03\xec\x03\xe7\x03\xe1\x03\xda\x03\xd3\x03\xcc\x03\xc4\x03\xbb\x03\xb2\x03\xa8\x03\x9d\x03\x92\x03\x87\x03\x7a\x03\x6e\x03\x61\x03\x53\x03\x45\x03\x36\x03\x27\x03\x17\x03\x07\x03\xf6\x02\xe5\x02"
    b"\xd4\x02\xc2\x02\xaf\x02\x9c\x02\x89\x02\x75\x02\x61\x02\x4d\x02\x38\x02\x23\x02\x0e\x02\xf8\x01\xe2\x01\xcc\x01\xb5\x01\x9e\x01\x87\x01\x70\x01\x58\x01\x41\x01\x29\x01\x11\x01\xf8\x00\xe0\x00\xc7\x00\xaf\x00\x96\x00\x7d\x00\x64\x00\x4b\x00\x32\x00\x19\x00"
    b"\x00\x00\xe7\xff\xce\xff\xb5\xff\x9c\xff\x83\xff\x6a\xff\x51\xff\x39\xff\x20\xff\x08\xff\xef\xfe\xd7\xfe\xbf\xfe\xa8\xfe\x90\xfe\x79\xfe\x62\xfe\x4b\xfe\x34\xfe\x1e\xfe\x08\xfe\xf2\xfd\xdd\xfd\xc8\xfd\xb3\xfd\x9f\xfd\x8b\xfd\x77\xfd\x64\xfd\x51\xfd\x3e\xfd"
    b"\x2c\xfd\x1b\xfd\x0a\xfd\xf9\xfc\xe9\xfc\xd9\xfc\xca\xfc\xbb\xfc\xad\xfc\x9f\xfc\x92\xfc\x86\xfc\x79\xfc\x6e\xfc\x63\xfc\x58\xfc\x4e\xfc\x45\xfc\x3c\xfc\x34\xfc\x2d\xfc\x26\xfc\x1f\xfc\x19\xfc\x14\xfc\x10\xfc\x0c\xfc\x08\xfc\x05\xfc\x03\xfc\x02\xfc\x01\xfc"
    b"\x00\xfc\x01\xfc\x02\xfc\x03\xfc\x05\xfc\x08\xfc\x0c\xfc\x10\xfc\x14\xfc\x19\xfc\x1f\xfc\x26\xfc\x2d\xfc\x34\xfc\x3c\xfc\x45\xfc\x4e\xfc\x58\xfc\x63\xfc\x6e\xfc\x79\xfc\x86\xfc\x92\xfc\x9f\xfc\xad\xfc\xbb\xfc\xca\xfc\xd9\xfc\xe9\xfc\xf9\xfc\x0a\xfd\x1b\xfd"
    b"\x2c\xfd\x3e\xfd\x51\xfd\x64\xfd\x77\xfd\x8b\xfd\x9f\xfd\xb3\xfd\xc8\xfd\xdd\xfd\xf2\xfd\x08\xfe\x1e\xfe\x34\xfe\x4b\xfe\x62\xfe\x79\xfe\x90\xfe\xa8\xfe\xbf\xfe\xd7\xfe\xef\xfe\x08\xff\x20\xff\x39\xff\x51\xff\x6a\xff\x83\xff\x9c\xff\xb5\xff\xce\xff\xe7\xff",
)


# Look up the fast integer sine (-1024..1024) for a 0..255 phase index.
def isin(idx):
    return SIN256[idx & 0xFF]


# Look up the fast integer cosine (-1024..1024) for a 0..255 phase index.
def icos(idx):
    return SIN256[(idx + 64) & 0xFF]


# Generate a random integer in [lo, hi] using only getrandbits for port safety.
def rng_int(lo, hi):
    span = hi - lo + 1
    if span <= 1:
        return lo
    bits = 0
    n = span - 1
    while n:
        bits += 1
        n >>= 1
    return lo + (getrandbits(bits) % span)


# Seed the random number generator deterministically if supported.
def init_rng(val=42):
    try:
        seed(val)
    except Exception:
        pass


class Layout:
    """Scale coordinates and pixel-art metrics from 480x320 up to 800x480."""

    def __init__(self, width, height):
        self.w = width
        self.h = height
        self.sw = width / REF_WIDTH
        self.sh = height / REF_HEIGHT
        self.s = min(self.sw, self.sh)
        self.compact = width < 600 or height < 380
        # Choose an integer pixel-art magnification factor (2x on 480x320, 3x on 800x480).
        self.px = 2 if self.compact else 3
        self.tile_px = 2 if self.compact else 3
        self.bar_h = 28 if self.compact else 36
        self.scene_y = self.bar_h
        self.scene_h = height - self.bar_h
        self.pad = 6 if self.compact else 10

    # Scale a horizontal coordinate from the 800-wide reference design.
    def x(self, val):
        return int(val * self.sw)

    # Scale a vertical coordinate inside the full screen height.
    def y(self, val):
        return int(val * self.sh)

    # Scale a vertical coordinate inside the scene area below the stage bar.
    def sy(self, frac):
        return self.scene_y + int(frac * self.scene_h)

    # Scale a dimension uniformly using the smaller axis ratio.
    def u(self, val):
        return max(1, int(val * self.s))


# Paint a vertical RGB565 gradient into a FrameBuffer over the given rectangle.
def paint_gradient(fb, x, y, w, h, rgb_top, rgb_bot, step=2):
    if w <= 0 or h <= 0:
        return
    denom = max(1, h - 1)
    r0, g0, b0 = rgb_top
    dr = rgb_bot[0] - r0
    dg = rgb_bot[1] - g0
    db = rgb_bot[2] - b0
    s = max(1, step)
    for row in range(0, h, s):
        t = row / denom
        c = rgb565(r0 + dr * t, g0 + dg * t, b0 + db * t)
        bh = s if row + s <= h else h - row
        fb.fill_rect(x, y + row, w, bh, c)


# Draw a stylized pixel-art beveled panel with a corner highlight and border.
def draw_pixel_panel(fb, x, y, w, h, bg_col, border_col, hi_col=None, shadow_col=None):
    if w < 6 or h < 6:
        return
    if shadow_col is not None:
        fb.fill_rect(x + 3, y + 3, w, h, shadow_col)
    fb.fill_rect(x + 2, y + 2, w - 4, h - 4, bg_col)
    fb.hline(x + 2, y, w - 4, border_col)
    fb.hline(x + 2, y + h - 1, w - 4, border_col)
    fb.vline(x, y + 2, h - 4, border_col)
    fb.vline(x + w - 1, y + 2, h - 4, border_col)
    fb.pixel(x + 1, y + 1, border_col)
    fb.pixel(x + w - 2, y + 1, border_col)
    fb.pixel(x + 1, y + h - 2, border_col)
    fb.pixel(x + w - 2, y + h - 2, border_col)
    if hi_col is not None and w > 8:
        fb.hline(x + 3, y + 1, w - 6, hi_col)


# Draw a Bayer-inspired pixel curtain wipe across the scene during act transitions.
def draw_pixel_wipe(fb, x, y, w, h, progress, col_main=VOID, col_edge=CYAN):
    # Progress runs 0.0 -> 0.5 (closing) and 0.5 -> 1.0 (opening).
    if progress <= 0.0 or progress >= 1.0:
        return
    coverage = 1.0 - abs(progress * 2.0 - 1.0)
    cell = 16
    cols = (w + cell - 1) // cell
    for cx in range(cols):
        # Stagger columns slightly so the wipe sweeps left-to-right like a pixel wave.
        local = coverage * 1.25 - (cx / max(1, cols)) * 0.25
        if local <= 0.0:
            continue
        if local >= 1.0:
            fb.fill_rect(x + cx * cell, y, min(cell, w - cx * cell), h, col_main)
            continue
        fill_h = int(h * local)
        bx = x + cx * cell
        bw = min(cell, w - cx * cell)
        if progress < 0.5:
            fb.fill_rect(bx, y, bw, fill_h, col_main)
            if fill_h + 3 <= h:
                fb.fill_rect(bx, y + fill_h, bw, 3, col_edge)
        else:
            top_y = y + h - fill_h
            fb.fill_rect(bx, top_y, bw, fill_h, col_main)
            if top_y >= y + 3:
                fb.fill_rect(bx, top_y - 3, bw, 3, col_edge)


# A pygraphics FrameBuffer over buf. Bit World never reads the Area a drawing call
# returns, so it asks for none: on MicroPython each one is a new object, and a frame
# of them is enough garbage to stop the picture for a collection. A pygraphics
# without areas= returns them anyway.
def gfx_frame(buf, w, h):
    try:
        return FrameBuffer(buf, w, h, RGB565, areas=False)
    except TypeError:
        return FrameBuffer(buf, w, h, RGB565)


if framebuf is None:
    Canvas = None
else:

    class Canvas(framebuf.FrameBuffer):
        """An RGB565 frame drawn with MicroPython's framebuf, which allocates nothing per call.

        A pygraphics without ``areas=False`` returns a new ``Area`` from each drawing
        call, and a frame makes a few hundred of them: enough garbage for a collection every few seconds, which
        stops the picture for a fifth of a second on a board with a large heap. The
        calls framebuf lacks, and text, whose 8x8 font differs, go to a pygraphics
        ``FrameBuffer`` on the same memory, in ``gfx``.
        """

        def __init__(self, buf, w, h):
            super().__init__(buf, w, h, framebuf.RGB565)
            self.gfx = gfx_frame(buf, w, h)

        # Draw text in pygraphics' 8x8 font, which isn't framebuf's.
        def text(self, s, x, y, c):
            self.gfx.text(s, x, y, c)

        # Draw text in the 8x16 font.
        def text16(self, s, x, y, c):
            self.gfx.text16(s, x, y, c)

        # Blend color through an 8-bit alpha mask.
        def blit_alpha(self, mask, x, y, w, h, c):
            self.gfx.blit_alpha(mask, x, y, w, h, c)


# Wrap w x h RGB565 pixels in buf for drawing: a Canvas where framebuf exists.
def make_canvas(buf, w, h):
    if Canvas is None:
        return gfx_frame(buf, w, h)
    return Canvas(buf, w, h)


# A pygraphics Draw for a frame from make_canvas.
def make_draw(fb):
    return Draw(getattr(fb, "gfx", fb))


# Build a reusable RGB565 frame tuple (bytearray, frame from make_canvas).
def make_fb(w, h, fill_color=None):
    buf = bytearray(w * h * 2)
    fb = make_canvas(buf, w, h)
    if fill_color is not None:
        fb.fill(fill_color)
    return buf, fb


class PanelState:
    """What one display buffer holds: which act, where its moving parts were, what it drew."""

    def __init__(self):
        self.act = -1
        self.rects = []
        # An act may keep its moving rectangles here instead, as x, y, w, h in an array,
        # with how many there are, so remembering them allocates nothing.
        self.moved = None
        self.moved_n = 0
        self.sig = {}
        self.bar = None

    # True, and remember it, when value differs from what this buffer last drew for key.
    def changed(self, key, value):
        if self.sig.get(key) == value:
            return False
        self.sig[key] = value
        return True


# Copy all of src, a frame from make_canvas, over fb. pygraphics copies whole rows at a
# time, where framebuf copies pixel by pixel, fifty times slower at full screen.
def copy_frame(fb, src):
    getattr(fb, "gfx", fb).blit(getattr(src, "gfx", src), 0, 0)


# Rectangles up to this many pixels are copied by framebuf, which allocates nothing.
# Larger ones go to pygraphics, whose row copies are much faster; a pygraphics without
# areas=False also makes a new Area for each.
SMALL_COPY = 2048


# Blit sources for rectangles of the background that never move: (source, x, y) for each,
# clipped like restore_rects. Build them once, and restore_sources copies them each frame.
def rect_sources(src, rects, w, h):
    view = memoryview(src)
    sources = []
    for x, y, rw, rh in rects:
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(w, x + rw)
        y1 = min(h, y + rh)
        if x1 > x0 and y1 > y0:
            sources.append(((view[(y0 * w + x0) * 2 :], x1 - x0, y1 - y0, RGB565, w), x0, y0))
    return sources


# Copy the rectangles rect_sources prepared back over a frame.
def restore_sources(fb, sources):
    gfx = getattr(fb, "gfx", fb)
    for source, x, y in sources:
        if source[1] * source[2] <= SMALL_COPY:
            fb.blit(source, x, y)
        else:
            gfx.blit(source, x, y)


# framebuf takes a list as a blit source, so restore_rect fills in this one each time.
_source = [None, 0, 0, RGB565, 0]


# Copy one (x, y, w, h) rectangle of the pre-rendered background back over a frame, from
# view, a memoryview of the background made once, clipped to the w x h frame. It's a blit
# from a (buffer, width, height, format, stride) view into the background; slicing the
# rows in Python is far slower on a board.
def restore_rect(fb, view, rect, w, h):
    x, y, rw, rh = rect
    restore_area(fb, view, x, y, rw, rh, w, h)


# restore_rect for a rectangle given as numbers, which saves making a tuple for it.
def restore_area(fb, view, x, y, rw, rh, w, h):
    x0 = max(0, x)
    y0 = max(0, y)
    x1 = min(w, x + rw)
    y1 = min(h, y + rh)
    if x1 <= x0 or y1 <= y0:
        return
    gfx = getattr(fb, "gfx", fb)
    src = _source
    src[0] = view[(y0 * w + x0) * 2 :]
    src[1] = x1 - x0
    src[2] = y1 - y0
    src[4] = w
    if gfx is not fb and src[1] * src[2] <= SMALL_COPY:
        fb.blit(src, x0, y0)
    else:
        gfx.blit((src[0], src[1], src[2], RGB565, w), x0, y0)
    src[0] = None  # don't keep the background's view alive


# Copy each rectangle in rects back with restore_rect. One listed twice, or listed in
# skip because it was copied already, is copied once.
def restore_rects(fb, view, rects, w, h, skip=None):
    for i in range(len(rects)):
        rect = rects[i]
        if rects.index(rect) < i or (skip is not None and rect in skip):
            continue
        restore_rect(fb, view, rect, w, h)
