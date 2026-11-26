# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Home: the apps on pages, one page per category, with a tab for each.

Each app says what it is in its ``app.json``: ``category`` (its page), ``icon``
(a Material Symbols name from the icons package, required), ``color`` (a "#RRGGBB" tile colour) and ``tile`` (false to
keep it off the pages). Pages come in alphabetical order by category. An app
with no category gets a page of its own, "More", last. Home knows no app by
name: the board's own apps (Info, Settings, Hidden apps, the REPL) are on the
System page because their ``app.json`` says so.

A tap on a tab switches pages at once; a swipe across the page slides to
the next one. Home comes back to the tab it was last on. The tabs are as
tall as the status bar.

An app hidden from an app's can't-run screen (``Launcher.hide``) stays off
the pages. The Hidden apps app lists them, with the reason each gave, and
puts them back.

A title too long for its tile takes a second line where the tile has room
for one, broken at a space or a hyphen; a single word too long for the tile
is cut short with dots. A small tile with room for a 48 px icon over its two
lines shows one, as large tiles do, so a 480x320 screen gets them; a smaller
tile keeps the 24 px icon.

On a round screen (see ``appkit.shell.is_round``) the pages and their tabs
fill the square inside the circle, two apps by two, so nothing falls
outside the circle.
"""

import lvgl as lv

import icons
from icons import lvgl as lvicons
from appkit.bar import height_for
from appkit.shell import ROUND_MARGIN, is_round
from touchkit import ui

DEFAULT_COLOR = "#44505E"

LARGE_PAD = 4  # least space between the large layout's icon or title and the tile's edge
BIG_ICON = 48  # the large layout's icon, and a small tile's when it has the room
SMALL_ICON = 24
SMALL_PAD = 2  # a small tile's padding
COLS, ROWS = 4, 2
GAP = 12
TOP = 56
MARGIN = 8  # around each page's card
CARD = 0x121826  # a shade lighter than the screen
LINE = 0x2A3550  # the card's border and the tab bar's top edge
TAB_ON = 0x1A2438


def _tall_enough(h):
    """Whether a tile *h* pixels tall fits the large layout: the 48 px icon, centred 22 px
    above the middle, and the title 40 px below it, each with LARGE_PAD to spare."""
    return h >= max(2 * (22 + 24 + LARGE_PAD), 2 * (40 + ui.font.line_height // 2 + LARGE_PAD))


def _grid(scope, page, cw, ch, apps, cols=COLS, rows=ROWS, small=False):
    """The app tiles on one page: a card *cw* by *ch*, *cols* by *rows* tiles.
    *small* tiles take the smaller fonts and stack the icon over the title; so do
    tiles too short for the large layout (see `_tall_enough`)."""
    launcher = scope.launcher
    if not small and not _tall_enough((ch - (rows + 1) * GAP) // rows):
        small = True
    gap = GAP // 2 if small else GAP
    card = lv.obj(page)
    card.remove_style_all()
    card.set_pos(MARGIN, MARGIN)
    card.set_size(cw, ch)
    card.set_style_bg_color(lv.color_hex(CARD), 0)
    card.set_style_bg_opa(lv.OPA.COVER, 0)
    card.set_style_radius(12 if small else 20, 0)
    card.set_style_border_width(1, 0)
    card.set_style_border_color(lv.color_hex(LINE), 0)
    card.remove_flag(lv.obj.FLAG.SCROLLABLE)
    card.add_flag(lv.obj.FLAG.EVENT_BUBBLE)  # a swipe on the card still turns the page
    w = (cw - (cols + 1) * gap) // cols
    h = (ch - (rows + 1) * gap) // rows
    if small:
        # Icon and title stacked and centred as one, the title given two lines'
        # room where the tile has it; the larger icon where there's room for
        # that too, so every icon in a row lines up whatever its title.
        lh = ui.tiny.line_height
        inner = h - 2 * SMALL_PAD
        lines = 2 if inner >= SMALL_ICON + LARGE_PAD + 2 * lh else 1
        size = BIG_ICON if lines == 2 and w >= 2 * BIG_ICON and inner >= BIG_ICON + 2 * LARGE_PAD + 2 * lh else SMALL_ICON
        top = (inner - size - LARGE_PAD - lines * lh) // 2
    else:
        lh = ui.font.line_height
        # The title's first line sits 40 px below the middle; a second goes under it.
        lines = 2 if h // 2 >= 40 + lh + LARGE_PAD else 1
    for i, (name, icon_name, color) in enumerate(apps[: cols * rows]):
        col, row = i % cols, i // cols
        b = lv.button(card)
        b.set_size(w, h)
        b.set_pos(gap + col * (w + gap), gap + row * (h + gap))
        b.set_style_bg_color(lv.color_hex(color), 0)
        title = launcher.info.get(name, {}).get("title", name)
        if small:
            b.set_style_radius(10, 0)
            b.set_style_pad_all(SMALL_PAD, 0)
            icon = lvicons.image(b, icon_name, size, ui.WHITE)
            text = wrap(title, ui.tiny, w - 2 * SMALL_PAD) if lines == 2 else title
            lbl = ui.label(b, text, ui.tiny, ui.WHITE)
            lbl.set_long_mode(lv.label.LONG_MODE.DOTS)
            # A fixed height is what lets DOTS cut a long title.
            lbl.set_size(w - 2 * SMALL_PAD, lh * (2 if "\n" in text else 1))
            lbl.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
            if lines == 1:
                icon.align(lv.ALIGN.CENTER, 0, -lh // 2)
                lbl.align(lv.ALIGN.BOTTOM_MID, 0, 0)
            else:
                icon.align(lv.ALIGN.TOP_MID, 0, top)
                lbl.align(lv.ALIGN.TOP_MID, 0, top + size + LARGE_PAD)
        else:
            b.set_style_radius(18, 0)
            icon = lvicons.image(b, icon_name, BIG_ICON, ui.WHITE)
            icon.align(lv.ALIGN.CENTER, 0, -22)
            width = w - 2 * LARGE_PAD
            text = wrap(title, ui.font, width) if lines == 2 else title
            two = "\n" in text
            lbl = ui.label(b, text, ui.font, ui.WHITE)
            lbl.set_long_mode(lv.label.LONG_MODE.DOTS)
            lbl.set_size(width, lh * (2 if two else 1))
            lbl.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
            lbl.align(lv.ALIGN.CENTER, 0, 40 + (lh // 2 if two else 0))
        b.add_event_cb((lambda n: lambda e: scope.switch(n))(name), lv.EVENT.CLICKED, None)


def text_width(text, font):
    """How wide *text* draws in *font*, in pixels."""
    n = len(text.encode())  # LVGL counts bytes
    try:
        attrs = lv.text_attributes_t()
        attrs.init()
        return lv.text_get_width(text, n, font, attrs)
    except AttributeError:  # LVGL before 9.4 takes the letter spacing itself
        return lv.text_get_width(text, n, font, 0)


def wrap(title, font, width):
    """*title* as a tile *width* pixels wide shows it in *font*: as it is when
    it fits on one line, else broken into two at the last space or hyphen
    that lets the first line fit. A title with no such break comes back as
    it is, for the label to cut short."""
    if text_width(title, font) <= width:
        return title
    best = None
    for i, ch in enumerate(title):
        if ch == " ":
            head, tail = title[:i], title[i + 1:]
        elif ch == "-":
            head, tail = title[: i + 1], title[i + 1:]
        else:
            continue
        if head.strip() and tail.strip() and text_width(head, font) <= width:
            best = head + "\n" + tail
    return title if best is None else best


def _tile(name, entry):
    icon = entry.get("icon")
    if icon is None:
        raise ValueError(
            'app %r has no "icon" in its app.json. Every app with a tile needs one: add "icon": '
            '"<Material icon name>", taken from icons.names(), or set "tile": false.' % (name,)
        )
    if not icons.has(icon):
        raise ValueError(
            "app %r names icon %r in its app.json, which the icons package hasn't. "
            "icons.names() lists the ones it has." % (name, icon)
        )
    return (name, icon, int(entry.get("color", DEFAULT_COLOR)[1:], 16))


def _pages(info, hidden=()):
    """``[(category, [(app, icon, colour), ...]), ...]``, from each app's
    ``app.json``, leaving out the apps in *hidden*."""
    by_category = {}
    more = []
    for name in sorted(info):
        entry = info[name]
        if not entry.get("tile", True) or name in hidden:
            continue
        category = entry.get("category")
        if category is None:
            more.append(_tile(name, entry))
        else:
            by_category.setdefault(category, []).append(_tile(name, entry))
    out = [(category, by_category[category]) for category in sorted(by_category)]
    if more:
        out.append(("More", more))
    return out


def _below_cap(scope, title, right):
    """How far Home's own row has to move down to clear the status bar's
    compact cap, which floats at the top middle: 0 when the cap fits between
    *title* and *right*, else the cap's height."""
    cap = getattr(scope, "bar", None)
    if cap is None or not cap.compact or not cap.is_shown():
        return 0
    cap.root.update_layout()
    title.update_layout()
    w = cap.root.get_width()
    left = (scope.size[0] - w) // 2
    if left >= title.get_x() + title.get_width() + 4 and left + w + 4 <= right:
        return 0
    return cap.root.get_y() + cap.root.get_height() + 4


def tab_height(scope):
    """How tall Home's tabs are: as tall as the status bar, or as the bar
    would be on this screen when there's none or it's the compact cap."""
    cap = getattr(scope, "bar", None)
    if cap is not None and not cap.compact:
        return cap.height
    disp = lv.display_get_default()
    return height_for(disp.get_horizontal_resolution(), disp.get_vertical_resolution())


def main(scope):
    scr = scope.root
    W, H = scope.size
    kept = scope.store()
    info = scope.launcher.info
    # Dark whether or not the shell put a dark theme on the display.
    scr.set_style_bg_color(ui.BG, 0)
    scr.set_style_bg_opa(lv.OPA.COVER, 0)
    # A round panel gets its own layout when Home has the whole screen.
    round_ = W == H and getattr(scope, "rect", (0, 0, W, H))[:2] == (0, 0) and is_round()

    if round_:
        # The square inside the circle holds the pages and their tabs.
        inner = W // 2 - ROUND_MARGIN
        side = int(inner * 1.4142) & ~1
        x0 = (W - side) // 2
        tab_bar = ui.small.line_height + 14
    else:
        tab_bar = tab_height(scope)
    # With the status bar's header, its title is the Home icon and the pages
    # take the whole area. Without it, Home draws its own row of TOP pixels.
    header = None if round_ else getattr(scope, "header", None)
    top = 0 if header is not None else TOP
    if not round_ and header is None:
        title = lvicons.image(scr, "home", 32, ui.ACCENT)
        title.set_pos(GAP + 4, (TOP - 32) // 2)
        drop = _below_cap(scope, title, W - GAP)
        if drop:
            title.set_y((TOP - 32) // 2 + drop)
            top += drop

    tv = lv.tabview(scr)
    if round_:
        tv.set_pos(x0, x0)
        tv.set_size(side, side)
    else:
        tv.set_pos(0, top)
        tv.set_size(W, H - top)
    tv.set_tab_bar_position(lv.DIR.BOTTOM)
    tv.set_tab_bar_size(tab_bar)
    tv.set_style_bg_color(ui.BG, 0)
    tv.get_content().set_style_bg_color(ui.BG, 0)

    pages = _pages(info, scope.launcher.hidden())
    for name, apps in pages:
        page = tv.add_tab(name)
        page.set_style_pad_all(0, 0)
        page.set_style_bg_color(ui.BG, 0)
        page.remove_flag(lv.obj.FLAG.SCROLLABLE)
        if round_:
            _grid(scope, page, side - 2 * MARGIN, side - tab_bar - 2 * MARGIN, apps, 2, 2, True)
        else:
            _grid(scope, page, W - 2 * MARGIN, H - top - tab_bar - 2 * MARGIN, apps)

    bar = tv.get_tab_bar()
    if round_:
        # Four labels share the square's width: the larger font if its tab is wide enough for "Video", else the smaller.
        tab_font = ui.small if side // max(1, len(pages)) >= 4 * ui.small.line_height else ui.tiny
    else:
        # The status bar's title font, or the largest that leaves the tab room.
        tab_font = getattr(getattr(scope, "bar", None), "title_font", None)
        if tab_font is None:
            tab_font = ui.font if ui.font.line_height + 8 <= tab_bar else ui.small
    bar.set_style_bg_color(ui.PANEL, 0)
    bar.set_style_bg_opa(lv.OPA.COVER, 0)
    bar.set_style_border_side(lv.BORDER_SIDE.TOP, 0)
    bar.set_style_border_width(1, 0)
    bar.set_style_border_color(lv.color_hex(LINE), 0)
    on = lv.STATE.CHECKED
    stripe = 3 if tab_bar < 40 else 4
    for i in range(bar.get_child_count()):
        t = bar.get_child(i)
        t.set_style_radius(0, 0)
        t.set_style_pad_ver(0, 0)
        t.set_style_text_font(tab_font, 0)
        t.set_style_text_color(ui.MUTED, 0)
        t.set_style_bg_opa(lv.OPA.TRANSP, 0)
        t.set_style_border_width(0, 0)
        t.set_style_shadow_width(0, 0)
        # the active tab: a lighter fill and an accent stripe along its top edge
        t.set_style_text_color(ui.WHITE, on)
        t.set_style_bg_color(lv.color_hex(TAB_ON), on)
        t.set_style_bg_opa(lv.OPA.COVER, on)
        t.set_style_border_side(lv.BORDER_SIDE.TOP, on)
        t.set_style_border_width(stripe, on)
        t.set_style_border_color(ui.ACCENT, on)

    tab = kept.get("tab", 0)
    if 0 < tab < len(pages):
        tv.set_active(tab, False)  # no animation

    def changed(e):
        kept["tab"] = tv.get_tab_active()

    tv.add_event_cb(changed, lv.EVENT.VALUE_CHANGED, None)
