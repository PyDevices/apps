# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Home: the apps on pages, one page per category, and one app behind the gear.

Each app says what it is in its ``app.json``: ``category`` (its page), ``icon``
(a Material icon name from iconkit's 48 px set, required), ``color`` (a "#RRGGBB" tile colour), ``tile`` (false to
keep it off the pages) and ``gear`` (true for the app the gear button opens).
Pages come in alphabetical order by category. An app with no category gets a
page of its own, "More", last. Home knows no app by name.

A tap on a tab switches pages at once; a swipe across the page slides to
the next one. Home comes back to the tab it was last on.

On a round screen (see ``appkit.shell.is_round``) the pages and their tabs
fill the square inside the circle, two apps by two, and the gear sits
centred above them, so nothing falls outside the circle.
"""

import lvgl as lv

import iconkit
from iconkit import lvicons
from appkit.shell import ROUND_MARGIN, is_round
from touchkit import ui

DEFAULT_COLOR = "#44505E"

COLS, ROWS = 4, 2
GAP = 12
TOP = 56
TAB_BAR = 56
MARGIN = 8  # around each page's card
CARD = 0x121826  # a shade lighter than the screen
LINE = 0x2A3550  # the card's border and the tab bar's top edge
TAB_ON = 0x1A2438


def _grid(scope, page, cw, ch, apps, cols=COLS, rows=ROWS, small=False):
    """The app tiles on one page: a card *cw* by *ch*, *cols* by *rows* tiles.
    *small* tiles take the smaller fonts and stack the icon over the title."""
    launcher = scope.launcher
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
    for i, (name, icon_name, color) in enumerate(apps[: cols * rows]):
        col, row = i % cols, i // cols
        b = lv.button(card)
        b.set_size(w, h)
        b.set_pos(gap + col * (w + gap), gap + row * (h + gap))
        b.set_style_bg_color(lv.color_hex(color), 0)
        title = launcher.info.get(name, {}).get("title", name)
        if small:
            b.set_style_radius(10, 0)
            b.set_style_pad_all(2, 0)
            icon = lvicons.image(b, icon_name, 24, ui.WHITE)
            icon.align(lv.ALIGN.CENTER, 0, -ui.tiny.line_height // 2)
            lbl = ui.label(b, title, ui.tiny, ui.WHITE)
            lbl.set_long_mode(lv.label.LONG_MODE.DOTS)
            lbl.set_width(w - 4)
            lbl.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
            lbl.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        else:
            b.set_style_radius(18, 0)
            icon = lvicons.image(b, icon_name, 48, ui.WHITE)
            icon.align(lv.ALIGN.CENTER, 0, -22)
            lbl = ui.label(b, title, ui.font, ui.WHITE)
            lbl.align(lv.ALIGN.CENTER, 0, 40)
        b.add_event_cb((lambda n: lambda e: scope.switch(n))(name), lv.EVENT.CLICKED, None)


def _tile(name, entry):
    icon = entry.get("icon")
    if icon is None:
        raise ValueError(
            'app %r has no "icon" in its app.json. Every app with a tile needs one: add "icon": '
            '"<Material icon name>", taken from iconkit.names(48), or set "tile": false.' % (name,)
        )
    if icon not in iconkit.names(48):
        raise ValueError(
            'app %r names icon %r in its app.json, which iconkit has no 48 px tile icon for. '
            "Pick one of: %s." % (name, icon, ", ".join(iconkit.names(48)))
        )
    return (name, icon, int(entry.get("color", DEFAULT_COLOR)[1:], 16))


def _pages(info):
    """``[(category, [(app, icon, colour), ...]), ...]``, from each app's ``app.json``."""
    by_category = {}
    more = []
    for name in sorted(info):
        entry = info[name]
        if not entry.get("tile", True):
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


def main(scope):
    scr = scope.root
    W, H = scope.size
    kept = scope.store()
    info = scope.launcher.info
    gear_app = None  # the app the gear opens: the one whose app.json says "gear": true
    for name in scope.launcher.names:
        if info.get(name, {}).get("gear"):
            gear_app = name
    # Dark whether or not the shell put a dark theme on the display.
    scr.set_style_bg_color(ui.BG, 0)
    scr.set_style_bg_opa(lv.OPA.COVER, 0)
    # A round panel gets its own layout when Home has the whole screen.
    round_ = W == H and getattr(scope, "rect", (0, 0, W, H))[:2] == (0, 0) and is_round()

    if round_:
        # The square inside the circle holds the pages and their tabs; the
        # gear goes in the cap of the circle above it, centred.
        inner = W // 2 - ROUND_MARGIN
        side = int(inner * 1.4142) & ~1
        x0 = (W - side) // 2
        tab_bar = ui.small.line_height + 14
        gear_w = 48
        # As high as the circle is gear_w wide there, and down to the square.
        gear_y = W // 2 - int((inner * inner - (gear_w // 2) ** 2) ** 0.5) + 1
        gear_h = max(24, min(TOP - 12, x0 - gear_y - 2))
    else:
        title = ui.label(scr, "Home", ui.big, ui.ACCENT)
        title.set_pos(GAP + 4, 14)

    if gear_app is not None:
        gear = lv.button(scr)
        gear.set_style_bg_color(lv.color_hex(0x44505E), 0)
        if round_:
            gear.set_size(gear_w, gear_h)
            gear.set_pos((W - gear_w) // 2, gear_y)
            gear.set_style_radius(gear_h // 2, 0)
            gear.set_style_pad_all(0, 0)
            lvicons.image(gear, "settings", 24, ui.WHITE).center()
        else:
            gear.set_size(64, TOP - 12)
            gear.align(lv.ALIGN.TOP_RIGHT, -GAP, 6)
            gear.set_style_radius(12, 0)
            lvicons.image(gear, "settings", 24, ui.WHITE).center()
        gear.add_event_cb(lambda e: scope.switch(gear_app), lv.EVENT.CLICKED, None)

    tv = lv.tabview(scr)
    if round_:
        tv.set_pos(x0, x0)
        tv.set_size(side, side)
    else:
        tv.set_pos(0, TOP)
        tv.set_size(W, H - TOP)
    tv.set_tab_bar_position(lv.DIR.BOTTOM)
    tv.set_tab_bar_size(tab_bar if round_ else TAB_BAR)
    tv.set_style_bg_color(ui.BG, 0)
    tv.get_content().set_style_bg_color(ui.BG, 0)

    pages = _pages(info)
    for name, apps in pages:
        page = tv.add_tab(name)
        page.set_style_pad_all(0, 0)
        page.set_style_bg_color(ui.BG, 0)
        page.remove_flag(lv.obj.FLAG.SCROLLABLE)
        if round_:
            _grid(scope, page, side - 2 * MARGIN, side - tab_bar - 2 * MARGIN, apps, 2, 2, True)
        else:
            _grid(scope, page, W - 2 * MARGIN, H - TOP - TAB_BAR - 2 * MARGIN, apps)

    bar = tv.get_tab_bar()
    bar.set_style_bg_color(ui.PANEL, 0)
    bar.set_style_bg_opa(lv.OPA.COVER, 0)
    bar.set_style_border_side(lv.BORDER_SIDE.TOP, 0)
    bar.set_style_border_width(1, 0)
    bar.set_style_border_color(lv.color_hex(LINE), 0)
    on = lv.STATE.CHECKED
    for i in range(bar.get_child_count()):
        t = bar.get_child(i)
        t.set_style_radius(0, 0)
        t.set_style_text_font(ui.small if round_ else ui.font, 0)
        t.set_style_text_color(ui.MUTED, 0)
        t.set_style_bg_opa(lv.OPA.TRANSP, 0)
        t.set_style_border_width(0, 0)
        t.set_style_shadow_width(0, 0)
        # the active tab: a lighter fill and an accent stripe along its top edge
        t.set_style_text_color(ui.WHITE, on)
        t.set_style_bg_color(lv.color_hex(TAB_ON), on)
        t.set_style_bg_opa(lv.OPA.COVER, on)
        t.set_style_border_side(lv.BORDER_SIDE.TOP, on)
        t.set_style_border_width(4, on)
        t.set_style_border_color(ui.ACCENT, on)

    tab = kept.get("tab", 0)
    if 0 < tab < len(pages):
        tv.set_active(tab, False)  # no animation

    def changed(e):
        kept["tab"] = tv.get_tab_active()

    tv.add_event_cb(changed, lv.EVENT.VALUE_CHANGED, None)
