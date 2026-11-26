# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Hidden apps: the apps kept off Home's pages, and a way to put each back.

An app that can't run on this board offers "Hide from Home" on its screen
(``touchkit.ui.hide_button``). Each one hidden that way is listed here with
the reason it gave, and Unhide puts its tile back on Home. Home goes back,
as it does from any app; the list is read afresh each time the app opens.
"""

import lvgl as lv

from touchkit import ui

GAP = 12
CARD = 0x121826  # Home's card colour
NONE_HIDDEN = "No app is hidden.\nAn app that can't run on this board offers Hide from Home, and comes back from here."


def _empty(scope):
    msg = ui.label(scope.root, NONE_HIDDEN, ui.font, ui.MUTED)
    msg.set_width(scope.size[0] - 4 * GAP)
    msg.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
    msg.align(lv.ALIGN.CENTER, 0, 0)
    return msg


def main(scope):
    launcher = scope.launcher
    W, H = scope.size
    root = scope.root
    root.set_style_bg_color(ui.BG, 0)
    root.set_style_bg_opa(lv.OPA.COVER, 0)
    hidden = launcher.hidden()
    if not hidden:
        _empty(scope)
        return
    rows = lv.obj(root)
    rows.set_size(W, H)
    rows.set_style_bg_opa(lv.OPA.TRANSP, 0)
    rows.set_style_border_width(0, 0)
    rows.set_style_radius(0, 0)
    rows.set_style_pad_all(GAP, 0)
    rows.set_style_pad_gap(GAP, 0)
    rows.set_flex_flow(lv.FLEX_FLOW.COLUMN)
    small = W < 480
    button_w = 96 if small else 120
    left = [len(hidden)]
    for name in sorted(hidden):
        row = ui.plain(lv.obj(rows))
        row.set_size(lv.pct(100), lv.SIZE_CONTENT)
        row.set_style_bg_color(lv.color_hex(CARD), 0)
        row.set_style_bg_opa(lv.OPA.COVER, 0)
        row.set_style_radius(12, 0)
        row.set_style_pad_all(GAP, 0)
        text = ui.label(row, launcher.info.get(name, {}).get("title", name), ui.font, ui.WHITE)
        text.set_pos(0, 0)
        if hidden[name]:
            why = ui.label(row, hidden[name], ui.small, ui.MUTED)
            why.set_width(W - 6 * GAP - button_w)
            why.align_to(text, lv.ALIGN.OUT_BOTTOM_LEFT, 0, 4)

        def unhide(name=name, row=row):
            launcher.unhide(name)
            row.delete_async()  # from its own button's callback
            left[0] -= 1
            if not left[0]:
                _empty(scope)

        u, _ = ui.button(row, "Unhide", unhide, w=button_w, color=ui.PANEL)
        u.align(lv.ALIGN.RIGHT_MID, 0, 0)
