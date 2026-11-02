# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Home: the apps on tabbed pages of 4 x 2, and System behind the gear.

A tap on a tab switches pages at once; a swipe across the page slides to
the next one. Home comes back to the tab it was last on. An app the
launcher doesn't have isn't shown, so a page lists only what's installed,
and an installed app no page names gets a page of its own, "More".
"""

import lvgl as lv

from devkit import ui

PAGES = (
    (
        lv.SYMBOL.AUDIO + "  Audio",
        (
            ("card", lv.SYMBOL.USB, 0x1E6F8C),
            ("effects", lv.SYMBOL.SHUFFLE, 0x8C3B1E),
            ("mp3", lv.SYMBOL.AUDIO, 0x3B6E2A),
            ("synthstation", lv.SYMBOL.KEYBOARD, 0x6A2C8C),
            ("midiengine", lv.SYMBOL.LIST, 0x8C1E4E),
            ("spotify", lv.SYMBOL.PLAY, 0x1E8C4E),
            ("wake", lv.SYMBOL.BELL, 0x8C7A1E),
        ),
    ),
    (
        lv.SYMBOL.VIDEO + "  Video",
        (
            ("camera", lv.SYMBOL.IMAGE, 0x1E6F8C),
            ("security", lv.SYMBOL.EYE_OPEN, 0x8C3B1E),
            ("detect", lv.SYMBOL.GPS, 0x3B6E2A),
            ("cast", lv.SYMBOL.WIFI, 0x6A2C8C),
            ("roku", lv.SYMBOL.HOME, 0x4A3D8C),
        ),
    ),
    (
        lv.SYMBOL.CALL + "  Link",
        (
            ("medialink_baby_monitor", lv.SYMBOL.AUDIO, 0x1E6F8C),
            ("medialink_doorbell", lv.SYMBOL.BELL, 0x8C3B1E),
            ("medialink_hands_free", lv.SYMBOL.CALL, 0x3B6E2A),
            ("medialink_surveillance_camera", lv.SYMBOL.EYE_OPEN, 0x6A2C8C),
            ("medialink_video_doorbell", lv.SYMBOL.VIDEO, 0x4A3D8C),
            ("medialink_videophone", lv.SYMBOL.IMAGE, 0x8C1E4E),
            ("medialink_walkie_talkie", lv.SYMBOL.VOLUME_MAX, 0x1E8C4E),
        ),
    ),
)
#: Apps that have a place of their own (the gear), not a tile.
NOT_TILES = ("home", "system")

COLS, ROWS = 4, 2
GAP = 12
TOP = 56
TAB_BAR = 56
MARGIN = 8  # around each page's card
CARD = 0x121826  # a shade lighter than the screen
LINE = 0x2A3550  # the card's border and the tab bar's top edge
TAB_ON = 0x1A2438


def _grid(scope, page, W, H, apps):
    launcher = scope.launcher
    cw, ch = W - 2 * MARGIN, H - TOP - TAB_BAR - 2 * MARGIN
    card = lv.obj(page)
    card.remove_style_all()
    card.set_pos(MARGIN, MARGIN)
    card.set_size(cw, ch)
    card.set_style_bg_color(lv.color_hex(CARD), 0)
    card.set_style_bg_opa(lv.OPA.COVER, 0)
    card.set_style_radius(20, 0)
    card.set_style_border_width(1, 0)
    card.set_style_border_color(lv.color_hex(LINE), 0)
    card.remove_flag(lv.obj.FLAG.SCROLLABLE)
    card.add_flag(lv.obj.FLAG.EVENT_BUBBLE)  # a swipe on the card still turns the page
    w = (cw - (COLS + 1) * GAP) // COLS
    h = (ch - (ROWS + 1) * GAP) // ROWS
    for i, (name, sym, color) in enumerate(apps[: COLS * ROWS]):
        col, row = i % COLS, i // COLS
        b = lv.button(card)
        b.set_size(w, h)
        b.set_pos(GAP + col * (w + GAP), GAP + row * (h + GAP))
        b.set_style_bg_color(lv.color_hex(color), 0)
        b.set_style_radius(18, 0)
        icon = ui.label(b, sym, ui.huge, ui.WHITE)
        icon.align(lv.ALIGN.CENTER, 0, -22)
        title = launcher.info.get(name, {}).get("title", name)
        lbl = ui.label(b, title, ui.font, ui.WHITE)
        lbl.align(lv.ALIGN.CENTER, 0, 40)
        b.add_event_cb((lambda n: lambda e: scope.switch(n))(name), lv.EVENT.CLICKED, None)


def _pages(names):
    """``[(tab title, [(app, symbol, colour), ...]), ...]`` for the apps in *names*."""
    out = []
    placed = set(NOT_TILES)
    for title, apps in PAGES:
        shown = [a for a in apps if a[0] in names]
        placed.update(a[0] for a in apps)
        if shown:
            out.append((title, shown))
    more = [(n, lv.SYMBOL.LIST, 0x44505E) for n in names if n not in placed]
    if more:
        out.append((lv.SYMBOL.LIST + "  More", more))
    return out


def main(scope):
    scr = scope.root
    W, H = scope.size
    kept = scope.store()
    names = scope.launcher.names
    title = ui.label(scr, "DEV-KIT", ui.big, ui.ACCENT)
    title.set_pos(GAP + 4, 14)

    if "system" in names:
        gear = lv.button(scr)
        gear.set_size(64, TOP - 12)
        gear.align(lv.ALIGN.TOP_RIGHT, -GAP, 6)
        gear.set_style_bg_color(lv.color_hex(0x44505E), 0)
        gear.set_style_radius(12, 0)
        ui.label(gear, lv.SYMBOL.SETTINGS, ui.big, ui.WHITE).center()
        gear.add_event_cb(lambda e: scope.switch("system"), lv.EVENT.CLICKED, None)

    tv = lv.tabview(scr)
    tv.set_pos(0, TOP)
    tv.set_size(W, H - TOP)
    tv.set_tab_bar_position(lv.DIR.BOTTOM)
    tv.set_tab_bar_size(TAB_BAR)
    tv.set_style_bg_color(ui.BG, 0)
    tv.get_content().set_style_bg_color(ui.BG, 0)

    pages = _pages(names)
    for name, apps in pages:
        page = tv.add_tab(name)
        page.set_style_pad_all(0, 0)
        page.set_style_bg_color(ui.BG, 0)
        page.remove_flag(lv.obj.FLAG.SCROLLABLE)
        _grid(scope, page, W, H, apps)

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
        t.set_style_text_font(ui.font, 0)
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
