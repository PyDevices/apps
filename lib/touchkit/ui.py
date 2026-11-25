# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""touchkit.ui -- the board's look, and the few widgets its apps build from.

The colours and fonts are here so an app can use them without the shell;
`apply_theme` puts them on the display, once, at boot.
"""

import lvgl as lv

HEADER = 64  # the header an app gets with no status bar; the corner Home button is sized from it
HOME_W = 128  # the Home button, at the header's left


def _font(*sizes):
    for s in sizes:
        f = getattr(lv, "font_montserrat_%d" % s, None)
        if f is not None:
            return f
    return lv.font_get_default()


font = _font(20, 18, 16)
small = _font(16, 14)
tiny = _font(14, 12)  # captions and eyebrows over a block of controls
big = _font(28, 26, 24, 22)
huge = _font(48, 40, 36, 32, 28)

BG = lv.color_hex(0x0B0E14)
PANEL = lv.color_hex(0x1A2030)
KEY = lv.color_hex(0x2A3550)  # a secondary button: the Home button's grey
ACCENT = lv.palette_main(lv.PALETTE.TEAL)
WARN = lv.palette_main(lv.PALETTE.AMBER)
BAD = lv.palette_main(lv.PALETTE.RED)
GOOD = lv.palette_main(lv.PALETTE.GREEN)
MUTED = lv.palette_main(lv.PALETTE.GREY)
WHITE = lv.color_hex(0xFFFFFF)


def apply_theme():
    """The dark theme in the board's colours, on the default display."""
    disp = lv.display_get_default()
    try:
        disp.set_theme(lv.theme_default_init(disp, ACCENT, WARN, True, font))
    except AttributeError:
        pass
    lv.screen_active().set_style_bg_color(BG, 0)


def plain(obj):
    """*obj* with no style of its own and no scrolling: a bare area."""
    obj.remove_style_all()
    obj.remove_flag(lv.obj.FLAG.SCROLLABLE)
    return obj


def status(scope):
    """The app's status line: the one on the status bar (or in its row under
    the bar on a narrow screen, or beside the title under the compact cap),
    or a label at the top right of ``scope.root`` without one, kept clear of
    a Home button at the top left. On a narrow screen asking for it brings
    its row in and shrinks ``scope.size`` and ``scope.rect``, so ask before
    placing anything from them."""
    lbl = getattr(scope, "status", None)
    if lbl is None:
        lbl = label(scope.root, "", small, MUTED)
        lbl.set_long_mode(lv.label.LONG_MODE.DOTS)
        lbl.set_size(max(40, scope.size[0] - HOME_W - 28), small.line_height)
        lbl.set_style_text_align(lv.TEXT_ALIGN.RIGHT, 0)
        lbl.align(lv.ALIGN.TOP_RIGHT, -16, 8)
    return lbl


def missing(scope, short, text):
    """An app that can't run here: *short* on the status line and *text* in
    the middle of the screen, saying which module or hardware is lacking.
    Home and BOOT go back as usual, and `hide_button` goes under the
    message. Returns the message label."""
    status(scope).set_text(short)
    msg = label(scope.root, text, font, WHITE)
    msg.set_width(scope.size[0] - 48)
    msg.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
    msg.align(lv.ALIGN.CENTER, 0, 0)
    hide_button(scope, short, msg)
    return msg


def hide_button(scope, reason, below):
    """A "Hide from Home" button under *below*, for an app that can't run
    here and draws its own message: a tap keeps the app off Home's pages,
    with *reason* on Home's Hidden apps page, and goes home. Only a tap
    hides an app. With no home screen to go back to there's no button, and
    it returns None; else the button."""
    launcher = getattr(scope, "launcher", None)
    home = getattr(launcher, "home", None)
    if home is None or scope.name == home:
        return None

    def hide():
        launcher.hide(scope.name, reason)
        launcher.request(home)

    b, _ = button(scope.root, "Hide from Home", hide, color=PANEL)
    b.align_to(below, lv.ALIGN.OUT_BOTTOM_MID, 0, 24)
    return b


def label(parent, text="", font=None, color=None):
    lbl = lv.label(parent)
    lbl.set_text(text)
    if font is not None:
        lbl.set_style_text_font(font, 0)
    if color is not None:
        lbl.set_style_text_color(color, 0)
    return lbl


def button(parent, text, cb, w=None, h=None, font=None, color=None):
    """A button that calls ``cb()`` when tapped. Returns ``(button, label)``."""
    b = lv.button(parent)
    if w:
        b.set_width(w)
    if h:
        b.set_height(h)
    if color is not None:
        b.set_style_bg_color(color, 0)
    b.set_style_radius(14, 0)
    lbl = lv.label(b)
    lbl.set_text(text)
    lbl.set_style_text_font(font or globals()["font"], 0)
    lbl.center()

    def clicked(e):
        cb()

    b.add_event_cb(clicked, lv.EVENT.CLICKED, None)
    return b, lbl


def box(parent, x, y, w, h, color=None):
    """A plain rectangle (a card or a panel) at a fixed place."""
    o = lv.obj(parent)
    o.set_pos(x, y)
    o.set_size(w, h)
    o.set_style_bg_color(color or PANEL, 0)
    o.set_style_border_width(0, 0)
    o.set_style_radius(14, 0)
    o.set_style_pad_all(10, 0)
    o.remove_flag(lv.obj.FLAG.SCROLLABLE)
    return o


def frame(parent, x, y, w, h):
    """A thin border round a picture drawn straight into the framebuffer."""
    f = lv.obj(parent)
    f.remove_style_all()
    f.set_pos(x - 2, y - 2)
    f.set_size(w + 4, h + 4)
    f.set_style_border_width(2, 0)
    f.set_style_border_color(PANEL, 0)
    return f


def rgb565_image(img, pixels, w, h, keep):
    """Show *pixels* (RGB565, *w* x *h*) in LVGL image *img*. LVGL keeps a
    pointer, not a reference: *keep* is a dict that holds the buffer for
    as long as it shows."""
    dsc = lv.image_dsc_t()
    dsc.header.magic = lv.IMAGE_HEADER_MAGIC
    dsc.header.cf = lv.COLOR_FORMAT.RGB565
    dsc.header.w = w
    dsc.header.h = h
    dsc.header.stride = w * 2
    dsc.data_size = len(pixels)
    dsc.data = pixels
    keep[id(img)] = (dsc, pixels)
    img.set_src(dsc)


def decode_jpeg(data, max_w, max_h=None):
    """``(pixels, w, h)``: JPEG *data* decoded to RGB565 on the P4's
    decoder, scaled down by halves until it fits *max_w* x *max_h*."""
    import jpegio

    if max_h is None:
        max_h = max_w
    dec = jpegio.JpegDecoder()
    w, h = dec.open(data)
    scale = 0
    while ((w >> scale) > max_w or (h >> scale) > max_h) and scale < 3:
        scale += 1
    w, h = w >> scale, h >> scale
    px = bytearray(w * h * 2)
    dec.decode(px, scale)
    return px, w, h
